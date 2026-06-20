from app.main import app
from app.models.automation_script import AutomationScript


def test_core_routes_are_registered():
    def get_all_paths(router_or_app, current_prefix=""):
        paths = set()
        routes = getattr(router_or_app, "routes", [])
        for route in routes:
            if hasattr(route, "path"):
                paths.add(current_prefix + route.path)
            if hasattr(route, "original_router"):
                sub_prefix = ""
                if hasattr(route, "include_context") and hasattr(route.include_context, "prefix"):
                    sub_prefix = route.include_context.prefix or ""
                paths.update(get_all_paths(route.original_router, current_prefix + sub_prefix))
        return paths

    paths = get_all_paths(app)

    assert "/" in paths

    assert "/api/v1/health/" in paths
    assert "/api/v1/projects/" in paths
    assert "/api/v1/agent-runs/project/{project_id}" in paths
    assert "/api/v1/agents/project/{project_id}" in paths
    assert "/api/v1/test-data/projects/{project_id}" in paths
    assert "/api/v1/test-data/projects/{project_id}/generate" in paths
    assert "/api/v1/test-data/projects/{project_id}/import/preview" in paths
    assert "/api/v1/test-data/projects/{project_id}/import/confirm" in paths


def test_automation_script_uses_current_model_fields():
    script = AutomationScript(
        project_id=1,
        test_case_id=2,
        created_by=1,
        script_id="AS-0001",
        framework="playwright",
        file_path="tests/example.spec.ts",
        code="import { test } from '@playwright/test';",
        setup_required=["npm install @playwright/test"],
        execution_command="npx playwright test tests/example.spec.ts",
        status="draft",
    )

    assert script.code.startswith("import")
    assert script.setup_required == ["npm install @playwright/test"]


def test_generated_test_case_uses_current_model_fields():
    from app.models.test_case import TestCase as TestCaseModel

    test_case = TestCaseModel(
        project_id=1,
        scenario_id=2,
        requirement_id=3,
        created_by=1,
        test_case_id="TC-0001",
        title="Validate generated case persistence",
        preconditions=["User is logged in"],
        test_data={"role": "qa"},
        steps=[{"step_number": 1, "action": "Open page", "expected_result": "Page loads"}],
        expected_result="The workflow succeeds",
        bdd_scenario="Given a user When they open the page Then it loads",
        priority="Medium",
        severity="Medium",
        test_type="functional",
        automation_candidate=True,
        metadata_={"tags": ["smoke"]},
        status="draft",
    )

    assert test_case.metadata_ == {"tags": ["smoke"]}
    assert test_case.automation_candidate is True
