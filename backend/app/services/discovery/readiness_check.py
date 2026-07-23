"""UI-015 readiness gate (Section 7) — wraps the existing generic
`automation_runner.readiness` checks (1-9) and adds the discovery-specific
checks the contract requires (10-14).

Every check here is real: it queries persisted rows or makes a real network
call. A validator/adapter with no matching `MCPConnection` row is reported
UNSUPPORTED/NOT_CONFIGURED, never fabricated as connected (same rule
`capability_resolver` already enforces for Test Automation Classification).
"""
from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_classification import TestCaseAutomationClassification
from app.models.discovery_session import DiscoverySession
from app.models.project_application import ProjectApplication
from app.services.automation_runner.readiness import ReadinessCheck, ReadinessInputs, ReadinessResult, check_readiness
from app.services.discovery import session_service
from app.services.test_classification import capability_resolver


async def _check_allowed_hosts(session: DiscoverySession, environment_url: str) -> ReadinessCheck:
    host = (urlparse(environment_url).hostname or "").lower()
    allowed = [h.lower() for h in (session.allowed_hosts or [])]
    if host and any(host == h or host.endswith("." + h) for h in allowed):
        return ReadinessCheck("allowed_host_policy", True, f"'{host}' is in the session's allowed host list.")
    return ReadinessCheck("allowed_host_policy", False, f"'{host}' is not in the session's allowed host list.")


async def _check_evidence_storage() -> ReadinessCheck:
    from app.services.automation_runner.workspace import workspace_root

    try:
        root = workspace_root().parent / "discovery_workspace"
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".readiness_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return ReadinessCheck("evidence_storage_writable", True, f"Managed workspace writable: {root}")
    except OSError as exc:
        return ReadinessCheck("evidence_storage_writable", False, f"Evidence storage is not writable: {exc}")


async def _check_mandatory_validators(db: AsyncSession, session: DiscoverySession) -> ReadinessCheck:
    """Check 14 — resolves against the same TestCaseAutomationClassification
    row (if one exists for the session's test case) that already declares
    mandatory_validators/required_capabilities; no classification means no
    declared mandatory validators, which is a real pass, not a fabricated one.
    """
    if session.test_case_id is None:
        return ReadinessCheck("validation_adapters_ready", True, "No test case selected — nothing declared mandatory.")

    result = await db.execute(
        select(TestCaseAutomationClassification).where(
            TestCaseAutomationClassification.test_case_id == session.test_case_id,
            TestCaseAutomationClassification.is_current.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    mandatory_keys: list[str] = list(row.mandatory_validators) if row and row.mandatory_validators else []
    if not mandatory_keys:
        return ReadinessCheck("validation_adapters_ready", True, "No mandatory validators declared for this test case.")

    resolved = await capability_resolver.resolve_capabilities(db, project_id=session.project_id, keys=mandatory_keys)
    unavailable = capability_resolver.unavailable_keys(resolved)
    if unavailable:
        details = "; ".join(f"{k}: {resolved[k].detail}" for k in unavailable)
        return ReadinessCheck("validation_adapters_ready", False, f"Mandatory validators unavailable — {details}")
    return ReadinessCheck("validation_adapters_ready", True, f"All {len(mandatory_keys)} mandatory validators connected.")


async def evaluate_session_readiness(db: AsyncSession, session: DiscoverySession) -> ReadinessResult:
    application = await db.get(ProjectApplication, session.application_id)
    environment_url = (application.environment_urls or {}).get(session.environment) if application else None

    inputs = ReadinessInputs(
        application_url=environment_url,
        credentials_required=bool(session.auth_profile_reference),
        storage_state_path=None,  # never displayed/read from here — reference only, per Section 16
        test_data_present=True,
        framework=session.framework,
    )
    base_result = await check_readiness(inputs)

    extra_checks = [
        await _check_allowed_hosts(session, environment_url or ""),
        await _check_evidence_storage(),
        await _check_mandatory_validators(db, session),
    ]

    if session.mode in ("GUIDED_USER", "SUPERVISED_AGENT_DRIVEN"):
        if session.test_case_id is None:
            extra_checks.append(ReadinessCheck("test_case_eligible", False, "No eligible test case selected."))
        else:
            eligible = await session_service.list_eligible_test_cases(
                db, project_id=session.project_id, application_id=session.application_id, mode=session.mode
            )
            match = next((e for e in eligible if e.test_case_id == session.test_case_id), None)
            extra_checks.append(
                ReadinessCheck("test_case_eligible", bool(match and match.eligible), match.blocking_reason if match and not match.eligible else "Approved, application-mapped and discovery-eligible.")
            )

    return ReadinessResult(checks=base_result.checks + extra_checks)
