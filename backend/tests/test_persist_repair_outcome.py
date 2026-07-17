"""automation_service.persist_repair_outcome: extracted from what used to
be inline-only logic in agent_tasks.py's automation_repair_loop
persistence, so it can be shared with the on-demand "Repair script"
trigger for real (non-dry-run) execution failures — which doesn't have an
AgentRun to hang project_id/triggered_by/agent_run_id off of, unlike the
automatic dry-run chain. test_repair_loop_persistence.py already covers
the behavior through _persist_agent_artifacts; these tests call the
extracted function directly."""
import anyio

from app.models.automation_script import AutomationScript
from app.services.automation_service import persist_repair_outcome


class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 100
        self.added.append(obj)

    async def flush(self):
        return None


def _parent(**overrides) -> AutomationScript:
    data = {
        "id": 1, "project_id": 8, "test_case_id": 10, "created_by": 1,
        "script_id": "AS-0001", "framework": "playwright", "code": "old", "version": 1,
        "status": "static_passed",
    }
    data.update(overrides)
    return AutomationScript(**data)


def test_new_version_uses_the_attempts_own_file_path_and_execution_command():
    # The compiler derives the spec file name from contract.business_flow, so
    # a repair patch that rewords business_flow produces a different
    # compiled_files key than the parent's file_path. If create_new_version
    # blindly inherited the parent's file_path/execution_command, the
    # persisted version would reference a spec file that was never written
    # (Playwright: "No tests found" at execution time) — see the real
    # tc_0008 incident this regression test is modeled on.
    db = _FakeDB()
    parent = _parent(
        file_path="specs/tc_0008_old_business_flow_wording.spec.ts",
        execution_command="npx playwright test specs/tc_0008_old_business_flow_wording.spec.ts",
    )
    repair = {
        "resolved": True,
        "attempts": [{
            "attempt": 1,
            "contract": {"testCaseId": "TC-8"},
            "compiled_files": {"specs/tc_0008_new_business_flow_wording.spec.ts": "attempt code"},
            "file_path": "specs/tc_0008_new_business_flow_wording.spec.ts",
            "execution_command": "npx playwright test specs/tc_0008_new_business_flow_wording.spec.ts",
            "static_gate_passed": True,
            "dry_run_passed": True,
            "dry_run_result": {"run_status": "completed", "results": [{"name": "t1", "status": "pass"}]},
            "outcome": "passed",
        }],
    }

    async def run():
        return await persist_repair_outcome(
            db, project_id=8, triggered_by=1, agent_run_id=None,
            parent_script=parent, repair=repair,
        )

    version = anyio.run(run)

    assert version.file_path == "specs/tc_0008_new_business_flow_wording.spec.ts"
    assert version.execution_command == "npx playwright test specs/tc_0008_new_business_flow_wording.spec.ts"
    # The persisted file_path must actually be a key in compiled_files —
    # that's the invariant the runner depends on.
    assert version.file_path in version.compiled_files


def test_returns_none_when_no_attempt_ever_compiled():
    # Real incident this is modeled on (TC-0009): a static-gate "missing
    # assertion" violation chained into the repair loop, the LLM was
    # reachable and responded three times, but every attempt failed before
    # producing anything compilable. persist_repair_outcome silently
    # discarded the entire attempt history — the script sat at its original
    # "generated" status with zero trace that self-heal had even run,
    # indistinguishable from never having been attempted at all.
    db = _FakeDB()
    parent = _parent()
    repair = {
        "resolved": False,
        "attempts": [
            {"attempt": 1, "outcome": "llm_patch_failed", "detail": "APIConnectionError: Connection error."},
            {"attempt": 2, "outcome": "compile_failed", "detail": "1 validation error for AutomationGenerationContract"},
            {"attempt": 3, "outcome": "compile_failed", "detail": "1 validation error for AutomationGenerationContract"},
        ],
    }

    async def run():
        return await persist_repair_outcome(
            db, project_id=8, triggered_by=1, agent_run_id=None,
            parent_script=parent, repair=repair,
        )

    version = anyio.run(run)

    assert version is None  # no new AutomationScript row — nothing compiled, nothing to version
    assert parent.metadata_["repair_loop_exhausted"] is True
    assert parent.metadata_["repair_attempts"] == [
        {"attempt": 1, "outcome": "llm_patch_failed", "detail": "APIConnectionError: Connection error."},
        {"attempt": 2, "outcome": "compile_failed", "detail": "1 validation error for AutomationGenerationContract"},
        {"attempt": 3, "outcome": "compile_failed", "detail": "1 validation error for AutomationGenerationContract"},
    ]


def test_returns_none_when_no_attempt_ever_compiled_legacy_shape():
    db = _FakeDB()
    repair = {"resolved": False, "attempts": [{"attempt": 1, "outcome": "llm_patch_failed"}]}

    async def run():
        return await persist_repair_outcome(
            db, project_id=8, triggered_by=1, agent_run_id=None,
            parent_script=_parent(), repair=repair,
        )

    result = anyio.run(run)
    assert result is None
    assert not any(isinstance(o, AutomationScript) for o in db.added)


def test_creates_a_version_and_marks_exhausted_without_agent_run_id():
    # On-demand repair (no AgentRun behind it) must still persist cleanly —
    # agent_run_id=None is the whole point of this being decoupled from the
    # automatic chain.
    db = _FakeDB()
    parent = _parent()
    repair = {
        "resolved": False,
        "attempts": [{
            "attempt": 1,
            "contract": {"testCaseId": "TC-1"},
            "compiled_files": {"specs/x.spec.ts": "attempt code"},
            "file_path": "specs/x.spec.ts",
            "static_gate_passed": True,
            "static_gate_result": {"passed": True},
            "dry_run_passed": False,
            "dry_run_result": {"run_status": "completed", "results": [{"name": "t1", "status": "fail"}]},
            "outcome": "failed",
        }],
    }

    async def run():
        return await persist_repair_outcome(
            db, project_id=8, triggered_by=2, agent_run_id=None,
            parent_script=parent, repair=repair,
        )

    version = anyio.run(run)
    assert version is not None
    assert version.parent_script_id == 1
    assert version.metadata_["repair_loop_exhausted"] is True
    assert parent.code == "old"  # parent never mutated

    from app.models.execution import ExecutionRun
    exec_run = next(o for o in db.added if isinstance(o, ExecutionRun))
    assert exec_run.agent_run_id is None
    assert exec_run.source_type == "repair_dry_run"
    assert exec_run.created_by == 2


def test_chains_multiple_attempts_and_does_not_mark_exhausted_when_resolved():
    db = _FakeDB()
    repair = {
        "resolved": True,
        "attempts": [
            {
                "attempt": 1,
                "contract": {"testCaseId": "TC-1"},
                "compiled_files": {"specs/x.spec.ts": "attempt 1 code"},
                "file_path": "specs/x.spec.ts",
                "static_gate_passed": True,
                "dry_run_passed": False,
                "dry_run_result": {"run_status": "completed", "results": [{"name": "t1", "status": "fail"}]},
                "outcome": "failed",
            },
            {
                "attempt": 2,
                "contract": {"testCaseId": "TC-1"},
                "compiled_files": {"specs/x.spec.ts": "attempt 2 code"},
                "file_path": "specs/x.spec.ts",
                "static_gate_passed": True,
                "dry_run_passed": True,
                "dry_run_result": {"run_status": "completed", "results": [{"name": "t1", "status": "pass"}]},
                "outcome": "passed",
            },
        ],
    }

    async def run():
        return await persist_repair_outcome(
            db, project_id=8, triggered_by=1, agent_run_id=55,
            parent_script=_parent(), repair=repair,
        )

    version = anyio.run(run)
    versions = [o for o in db.added if isinstance(o, AutomationScript)]
    assert len(versions) == 2
    assert versions[1].parent_script_id == versions[0].id  # second attempt chains off the first, not the original parent
    assert version is versions[1]
    assert version.status == "dry_run_passed"
    assert "repair_loop_exhausted" not in (version.metadata_ or {})
