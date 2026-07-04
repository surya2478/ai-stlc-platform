"""Tests for test_plan_service.bulk_update_test_cases.

Covers happy path, conflict detection, project scoping, dry-run behaviour,
and the empty-patch / not-found edge cases. Uses a tiny in-memory fake
AsyncSession so we don't need a real database for these unit tests.
"""
from __future__ import annotations

from typing import Any, Iterable

import anyio
import pytest

from app.models.test_case import TestCase as TestCaseModel, TestCaseHistory as TestCaseHistoryModel
from app.services import test_plan_service


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _tc(
    *, id: int, project_id: int = 1, key: str | None = None, mode: str = "manual",
    automation_status: str = "not_required", automation_eligible: str = "no",
    automation_ready: bool = False, automation_script_id: int | None = None,
    external_tool: str | None = None, title: str = "t",
) -> TestCaseModel:
    return TestCaseModel(
        id=id,
        project_id=project_id,
        created_by=1,
        test_case_id=key or f"TC-{id:04d}",
        title=title,
        execution_mode=mode,
        automation_status=automation_status,
        automation_eligible=automation_eligible,
        automation_ready=automation_ready,
        automation_script_id=automation_script_id,
        external_tool=external_tool,
    )


class _FakeDB:
    """Minimal AsyncSession stand-in.

    Stores TestCases in a dict by id. `execute(select(TestCase).where(id.in_(...)))`
    returns the matching rows. `add(...)` collects appended objects so tests can
    assert history rows were written. `flush` is a no-op counter.
    """

    def __init__(self, test_cases: Iterable[TestCaseModel]) -> None:
        self._by_id: dict[int, TestCaseModel] = {tc.id: tc for tc in test_cases}
        self.added: list[Any] = []
        self.flushed = 0
        self.mappings_deactivated = False

    async def execute(self, stmt: Any) -> "_FakeResult":
        # The service uses .in_() on TestCase.id; we just inspect the requested
        # ids by walking the where clause's right-hand side.
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql = str(compiled).lower()
        # Very loose match — production query is `WHERE test_cases.id IN (...)`.
        if "automation_test_mappings" in sql:
            # deactivate_active_mappings_if_not_automation_applicable() runs this query;
            # for these tests no mappings exist so return an empty result.
            self.mappings_deactivated = True
            return _FakeResult([])
        # Otherwise treat as TestCase fetch: extract IDs from the bound clause text.
        # As a fallback that's robust to dialect quoting, return all rows whose
        # id appears anywhere in the rendered SQL.
        rows = [tc for tc in self._by_id.values() if str(tc.id) in sql]
        return _FakeResult(rows)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed += 1


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> "_FakeScalars":
        return _FakeScalars(self._rows)


class _FakeScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)


def _run(coro):
    return anyio.run(lambda: coro)


# ──────────────────────────────────────────────────────────────────────────────
# Happy path
# ──────────────────────────────────────────────────────────────────────────────


def test_happy_path_updates_all_rows():
    async def go() -> None:
        tcs = [_tc(id=1), _tc(id=2), _tc(id=3)]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1, 2, 3], project_id=1,
            patch={"automation_status": "planned_for_automation"},
            reason="bulk triage Q2", user_id=42, dry_run=False,
        )
        assert result["requested"] == 3
        assert result["updated"] == 3
        assert result["skipped"] == 0
        assert result["conflicts"] == 0
        assert all(tc.automation_status == "planned_for_automation" for tc in tcs)
        # One history row per mutated audited field per row.
        history_rows = [a for a in db.added if isinstance(a, TestCaseHistoryModel)]
        assert len(history_rows) == 3
        assert all(h.source == "bulk_update" and h.comment == "bulk triage Q2" for h in history_rows)
        assert db.flushed >= 1
    _run(go())


def test_dry_run_does_not_mutate():
    async def go() -> None:
        # Row already in "automation" mode so the manual+automated conflict check
        # doesn't fire — we're isolating the dry-run-no-mutation invariant.
        tcs = [_tc(id=1, mode="automation", automation_eligible="yes", automation_status="planned_for_automation")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"automation_status": "automated"},
            reason="preview only", user_id=42, dry_run=True,
        )
        # Diff is reported …
        assert result["updated"] == 1
        assert result["rows"][0]["changes"]["automation_status"]["new"] == "automated"
        # … but the row itself is untouched and no history rows are written.
        assert tcs[0].automation_status == "planned_for_automation"
        assert not any(isinstance(a, TestCaseHistoryModel) for a in db.added)
        assert db.flushed == 0
    _run(go())


# ──────────────────────────────────────────────────────────────────────────────
# Conflict detection
# ──────────────────────────────────────────────────────────────────────────────


def test_conflict_when_switching_to_manual_with_linked_script():
    async def go() -> None:
        # TC 1 has an attached automation_script — flipping to manual would orphan it.
        tcs = [_tc(id=1, mode="automation", automation_script_id=99)]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"execution_mode": "manual"},
            reason="rollback", user_id=42, dry_run=False,
        )
        assert result["conflicts"] == 1
        assert result["updated"] == 0
        assert result["rows"][0]["outcome"] == "conflict"
        assert "script" in result["rows"][0]["conflict_reason"].lower()
        # Row remains unchanged.
        assert tcs[0].execution_mode == "automation"
    _run(go())


def test_conflict_when_marking_automated_with_manual_mode():
    async def go() -> None:
        tcs = [_tc(id=1, mode="manual")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"automation_status": "automated"},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["conflicts"] == 1
        assert result["rows"][0]["outcome"] == "conflict"
    _run(go())


# ──────────────────────────────────────────────────────────────────────────────
# Skip / not-found / forbidden
# ──────────────────────────────────────────────────────────────────────────────


def test_skipped_when_row_already_has_value():
    async def go() -> None:
        # Already in "automation" mode — patching status to "automated" when the
        # row's current status is also "automated" should report skipped, not
        # trigger the manual+automated conflict check.
        tcs = [_tc(id=1, mode="automation", automation_eligible="yes", automation_status="automated")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"automation_status": "automated"},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["skipped"] == 1
        assert result["updated"] == 0
        assert result["rows"][0]["outcome"] == "skipped"
    _run(go())


def test_not_found_id_marked_not_found():
    async def go() -> None:
        db = _FakeDB([])
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[999], project_id=1,
            patch={"automation_status": "planned_for_automation"},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["not_found"] == 1
        assert result["rows"][0]["outcome"] == "not_found"
    _run(go())


def test_cross_project_id_is_forbidden():
    async def go() -> None:
        # TC 1 belongs to project 2, caller claims project 1.
        tcs = [_tc(id=1, project_id=2)]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"automation_status": "planned_for_automation"},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["forbidden"] == 1
        assert result["rows"][0]["outcome"] == "forbidden"
        # Original state preserved.
        assert tcs[0].automation_status == "not_required"
    _run(go())


# ──────────────────────────────────────────────────────────────────────────────
# Patch shape edge cases
# ──────────────────────────────────────────────────────────────────────────────


def test_empty_patch_short_circuits_to_all_skipped():
    async def go() -> None:
        tcs = [_tc(id=1), _tc(id=2)]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1, 2], project_id=1,
            patch={},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["updated"] == 0
        assert result["skipped"] == 2
        assert all(row["conflict_reason"] == "patch was empty" for row in result["rows"])
        # We don't even touch the DB.
        assert db.flushed == 0
    _run(go())


def test_mode_change_auto_derives_automation_eligible():
    async def go() -> None:
        tcs = [_tc(id=1, mode="manual", automation_eligible="no")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"execution_mode": "automation"},
            reason="auto", user_id=42, dry_run=False,
        )
        assert result["updated"] == 1
        # automation_eligible flips to "yes" implicitly.
        assert tcs[0].automation_eligible == "yes"
        # Both fields show up in the diff.
        diff_fields = set(result["rows"][0]["changes"].keys())
        assert {"execution_mode", "automation_eligible"}.issubset(diff_fields)
    _run(go())


def test_mode_to_manual_clears_automation_eligible_to_no():
    async def go() -> None:
        # No linked script, so the manual switch is allowed.
        tcs = [_tc(id=1, mode="automation", automation_eligible="yes")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"execution_mode": "manual"},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["updated"] == 1
        assert tcs[0].execution_mode == "manual"
        assert tcs[0].automation_eligible == "no"
    _run(go())


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases — duplicates, explicit None, falsy booleans, large requests
# ──────────────────────────────────────────────────────────────────────────────


def test_duplicate_ids_deduped_so_counters_stay_honest():
    """[1, 1, 1] must report a single row, not three (one updated + two phantom skips)."""
    async def go() -> None:
        tcs = [_tc(id=1, mode="automation", automation_eligible="yes", automation_status="planned_for_automation")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1, 1, 1], project_id=1,
            patch={"automation_status": "automated"},
            reason="dup test", user_id=42, dry_run=False,
        )
        assert result["requested"] == 1, "duplicates should fold into one analysis"
        assert result["updated"] == 1
        assert result["skipped"] == 0
        assert len(result["rows"]) == 1, "preview must not show the same TC three times"
        # One history row, not three.
        history_rows = [a for a in db.added if isinstance(a, TestCaseHistoryModel)]
        assert len(history_rows) == 1
    _run(go())


def test_explicit_none_values_in_patch_treated_as_no_op():
    """A caller hitting the API directly with explicit nulls shouldn't mutate the row."""
    async def go() -> None:
        tcs = [_tc(id=1, mode="automation", automation_eligible="yes", automation_status="planned_for_automation")]
        db = _FakeDB(tcs)
        # All explicit Nones — service should treat this as an empty patch.
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"automation_status": None, "execution_mode": None},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["updated"] == 0
        assert result["skipped"] == 1
        assert result["rows"][0]["conflict_reason"] == "patch was empty"
        # Row stays put.
        assert tcs[0].automation_status == "planned_for_automation"
    _run(go())


def test_automation_ready_false_is_a_real_change_not_filtered_out():
    """Boolean False is falsy but is NOT `None` — it must be applied as a real update."""
    async def go() -> None:
        tcs = [_tc(id=1, mode="automation", automation_eligible="yes",
                   automation_status="automated", automation_ready=True)]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"automation_ready": False},
            reason="revert CI flag", user_id=42, dry_run=False,
        )
        assert result["updated"] == 1
        assert tcs[0].automation_ready is False
        assert result["rows"][0]["changes"]["automation_ready"]["new"] is False
    _run(go())


def test_combination_patch_applies_all_fields_in_one_pass():
    async def go() -> None:
        tcs = [_tc(id=1, mode="manual", automation_eligible="no", automation_status="not_required")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"execution_mode": "automation", "automation_status": "planned_for_automation",
                   "external_tool": "Playwright"},
            reason="onboard to automation", user_id=42, dry_run=False,
        )
        assert result["updated"] == 1
        assert tcs[0].execution_mode == "automation"
        assert tcs[0].automation_status == "planned_for_automation"
        assert tcs[0].external_tool == "Playwright"
        # automation_eligible is auto-derived as "yes" alongside the mode flip.
        assert tcs[0].automation_eligible == "yes"
        # All four changes show up in the diff payload.
        diff = result["rows"][0]["changes"]
        assert set(diff.keys()) == {"execution_mode", "automation_status", "external_tool", "automation_eligible"}
    _run(go())


def test_mode_change_with_eligibility_already_matching_no_phantom_diff():
    """If the auto-derived eligibility already matches the stored value,
    it must not appear as a spurious diff entry."""
    async def go() -> None:
        tcs = [_tc(id=1, mode="automation", automation_eligible="yes",
                   automation_status="planned_for_automation")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            # Mode is already "automation" so this is genuinely a no-op on mode.
            patch={"execution_mode": "automation"},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["skipped"] == 1
        assert "automation_eligible" not in result["rows"][0]["changes"]
    _run(go())


# ──────────────────────────────────────────────────────────────────────────────
# Negative cases — Pydantic validation
# ──────────────────────────────────────────────────────────────────────────────


def test_whitespace_only_reason_rejected_by_schema():
    from app.schemas.test_plan import TestCaseBulkPatch, TestCaseBulkUpdateRequest
    from pydantic import ValidationError as PydanticValidationError
    with pytest.raises(PydanticValidationError, match="whitespace"):
        TestCaseBulkUpdateRequest(
            test_case_ids=[1], patch=TestCaseBulkPatch(),
            reason="   ", dry_run=False,
        )


def test_empty_id_list_rejected_by_schema():
    from app.schemas.test_plan import TestCaseBulkPatch, TestCaseBulkUpdateRequest
    from pydantic import ValidationError as PydanticValidationError
    with pytest.raises(PydanticValidationError):
        TestCaseBulkUpdateRequest(
            test_case_ids=[], patch=TestCaseBulkPatch(),
            reason="x", dry_run=False,
        )


def test_request_over_max_length_rejected_by_schema():
    from app.schemas.test_plan import TestCaseBulkPatch, TestCaseBulkUpdateRequest
    from pydantic import ValidationError as PydanticValidationError
    with pytest.raises(PydanticValidationError):
        TestCaseBulkUpdateRequest(
            test_case_ids=list(range(501)), patch=TestCaseBulkPatch(),
            reason="x", dry_run=False,
        )


def test_reason_is_stripped_before_storage():
    """Leading/trailing whitespace on a valid reason is trimmed so the audit
    trail isn't littered with formatting artifacts."""
    from app.schemas.test_plan import TestCaseBulkPatch, TestCaseBulkUpdateRequest
    req = TestCaseBulkUpdateRequest(
        test_case_ids=[1], patch=TestCaseBulkPatch(execution_mode="manual"),
        reason="  legitimate reason  ", dry_run=False,
    )
    assert req.reason == "legitimate reason"


# ──────────────────────────────────────────────────────────────────────────────
# Negative cases — mass-not-found / mass-forbidden
# ──────────────────────────────────────────────────────────────────────────────


def test_all_rows_not_found_yields_zero_updates():
    async def go() -> None:
        db = _FakeDB([])
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[999, 1000, 1001], project_id=1,
            patch={"automation_status": "planned_for_automation"},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["updated"] == 0
        assert result["not_found"] == 3
        assert db.flushed == 1  # flush still called once at the end (no-op on empty changeset)
    _run(go())


def test_invalid_enum_value_for_execution_mode_returns_422():
    from fastapi import HTTPException
    async def go() -> None:
        tcs = [_tc(id=1, mode="manual")]
        db = _FakeDB(tcs)
        with pytest.raises(HTTPException) as ei:
            await test_plan_service.bulk_update_test_cases(
                db, test_case_ids=[1], project_id=1,
                patch={"execution_mode": "garbage_value"},
                reason="x", user_id=42, dry_run=False,
            )
        assert ei.value.status_code == 422
        # Row must remain untouched when validation fails up front.
        assert tcs[0].execution_mode == "manual"
    _run(go())


def test_invalid_enum_value_for_automation_status_returns_422():
    from fastapi import HTTPException
    async def go() -> None:
        db = _FakeDB([_tc(id=1)])
        with pytest.raises(HTTPException) as ei:
            await test_plan_service.bulk_update_test_cases(
                db, test_case_ids=[1], project_id=1,
                patch={"automation_status": "no_such_status"},
                reason="x", user_id=42, dry_run=False,
            )
        assert ei.value.status_code == 422
    _run(go())


def test_external_tool_empty_string_allowed_as_clear():
    """Setting external_tool to '' is a legitimate 'clear it' intent, not garbage."""
    async def go() -> None:
        tcs = [_tc(id=1, mode="automation", automation_eligible="yes", external_tool="Katalon")]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1], project_id=1,
            patch={"external_tool": ""},
            reason="detach", user_id=42, dry_run=False,
        )
        assert result["updated"] == 1
        assert tcs[0].external_tool == ""
    _run(go())


def test_mixed_projects_only_caller_project_updates():
    """A bulk call to project 1 with IDs that span projects 1, 2, 2 must update
    only the project-1 row and report the others as forbidden."""
    async def go() -> None:
        tcs = [
            _tc(id=1, project_id=1, mode="automation", automation_eligible="yes"),
            _tc(id=2, project_id=2, mode="automation", automation_eligible="yes"),
            _tc(id=3, project_id=2, mode="automation", automation_eligible="yes"),
        ]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1, 2, 3], project_id=1,
            patch={"automation_status": "planned_for_automation"},
            reason="x", user_id=42, dry_run=False,
        )
        assert result["updated"] == 1
        assert result["forbidden"] == 2
        # Project-2 rows must not have been touched.
        assert tcs[1].automation_status == "not_required"
        assert tcs[2].automation_status == "not_required"
    _run(go())


def test_outcomes_summary_counts_match_per_row_breakdown():
    """The aggregate counters must always equal the sum of per-row outcomes."""
    async def go() -> None:
        tcs = [
            _tc(id=1),                                                       # updated
            _tc(id=2, automation_status="planned_for_automation"),           # skipped
            _tc(id=3, mode="automation", automation_script_id=10),           # ignored by this patch
        ]
        db = _FakeDB(tcs)
        result = await test_plan_service.bulk_update_test_cases(
            db, test_case_ids=[1, 2, 3, 999], project_id=1,                  # 999 → not_found
            patch={"automation_status": "planned_for_automation"},
            reason="x", user_id=42, dry_run=True,
        )
        breakdown = {"updated": 0, "skipped": 0, "conflicts": 0, "not_found": 0, "forbidden": 0}
        for row in result["rows"]:
            key = "conflicts" if row["outcome"] == "conflict" else row["outcome"]
            breakdown[key] += 1
        for key in ("updated", "skipped", "conflicts", "not_found", "forbidden"):
            assert result[key] == breakdown[key], f"{key} mismatch: {result[key]} vs {breakdown[key]}"
        assert sum(breakdown.values()) == result["requested"]
    _run(go())
