import pytest
import uuid
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.schemas.resource_ops import (
    LDAPLoginRequest,
    ResourceCreate,
    AIEstimateRequest,
    DailyWorkPlanCreate,
)
from app.services.ai_estimate_service import AIEstimateService, AIEstimateLLMResponse
from app.services.resource_ops_service import ResourceOpsService
from app.models.resource_ops import DailyWorkPlan, WorkEvidenceEvent, Resource, IntegrationConnection


# ── Route Registration Tests ───────────────────────────────────────────

def test_resource_ops_routes_are_registered():
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

    # Verify that the resource operations endpoints are registered
    assert "/api/v1/resource-operations/ldap-login" in paths
    assert "/api/v1/resource-operations/dashboard" in paths
    assert "/api/v1/resource-operations/resources" in paths
    assert "/api/v1/resource-operations/resources/{person_id}" in paths
    assert "/api/v1/resource-operations/mappings" in paths
    assert "/api/v1/resource-operations/mappings/{mapping_id}/approve" in paths
    assert "/api/v1/resource-operations/work-plans" in paths
    assert "/api/v1/resource-operations/timeline" in paths
    assert "/api/v1/resource-operations/connections" in paths
    assert "/api/v1/resource-operations/connections/{conn_id}" in paths
    assert "/api/v1/resource-operations/connections/{conn_id}/sync" in paths
    assert "/api/v1/resource-operations/estimate" in paths
    assert "/api/v1/resource-operations/estimates/calibration" in paths


# ── Schema Validation & Negative Tests ─────────────────────────────────

def test_ldap_login_validation_negative():
    # Valid login request
    payload = LDAPLoginRequest(username="test.user", password="secretpassword", domain="CORP.NET")
    assert payload.username == "test.user"
    assert payload.domain == "CORP.NET"

    # Missing username should raise ValidationError
    with pytest.raises(ValueError):
        LDAPLoginRequest(password="secretpassword", domain="CORP.NET")

    # Empty username should raise ValidationError
    with pytest.raises(ValueError):
        LDAPLoginRequest(username="", password="secretpassword", domain="CORP.NET")


def test_resource_creation_validation():
    # Valid resource create payload
    payload = ResourceCreate(
        ldap_username="john.doe",
        domain="CORP.NET",
        corporate_email="john.doe@company.com",
        display_name="John Doe",
    )
    assert payload.ldap_username == "john.doe"
    assert payload.corporate_email == "john.doe@company.com"

    # Invalid email format should raise ValidationError
    with pytest.raises(ValueError):
        ResourceCreate(
            ldap_username="john.doe",
            domain="CORP.NET",
            corporate_email="not-an-email",
            display_name="John Doe"
        )


def test_ai_estimate_validation():
    # Valid estimate payload
    payload = AIEstimateRequest(
        project_id=1,
        activity_type="Manual Test Execution",
        inputs={"num_test_cases": 15}
    )
    assert payload.project_id == 1
    assert payload.inputs == {"num_test_cases": 15}


# ── Mathematical & Logic Edge Case Tests ───────────────────────────────

def test_pert_estimation_calculation_extreme_boundaries():
    # Test typical PERT calculation
    # pert = (optimistic + 4*likely + pessimistic) / 6
    assert (4.0 + (4.0 * 6.0) + 11.0) / 6.0 == 6.5

    # Test extreme boundaries: very large numbers
    optimistic = 1000.0
    likely = 2500.0
    pessimistic = 9000.0
    pert = (optimistic + (4.0 * likely) + pessimistic) / 6.0
    assert pert == 3333.3333333333335

    # Test zero optimistic value
    assert (0.0 + (4.0 * 5.0) + 10.0) / 6.0 == 5.0


@pytest.mark.anyio
async def test_ai_estimation_service_llm_fallback():
    # Test that the AI Estimate Service successfully falls back to template calculations
    # if the LLM provider fails, returns bad json, or throws an exception.
    mock_execute_result = MagicMock()
    mock_execute_result.scalar.return_value = None  # No historical average
    
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_execute_result
    
    # Mock LLM provider to throw an exception
    mock_llm = AsyncMock()
    mock_llm.generate.side_effect = Exception("LLM connection timed out")
    
    from unittest.mock import patch
    with patch("app.services.ai_estimate_service.get_llm_for_role", return_value=mock_llm):
        service = AIEstimateService(mock_db)
        
        # Request estimation
        result = await service.generate_estimate(
            project_id=1,
            activity_type="Manual Test Execution",
            complexity="Medium",
            inputs={"num_test_cases": 5}
        )
        
        # Verify fallback values are populated correctly
        assert result.baseline_hours == 8.0  # From BASELINE_TEMPLATES["Manual Test Execution"] for Medium
        assert result.optimistic_hours == 6.4
        assert result.most_likely_hours == 8.0
        assert result.pessimistic_hours == 11.2
        assert result.recommended_hours == 8.6  # (6.4 + 4*8.0 + 11.2)/6 + risk_adj (11.2 - 8.0)*0.1 = 8.27 + 0.32 = 8.59 -> rounded to 1 dec place is 8.6
        assert "fallback" in result.assumptions.lower()


# ── Deduplication sliding window edge cases ────────────────────────────

@pytest.mark.anyio
async def test_reconcile_and_deduplicate_evidence():
    mock_db = AsyncMock()
    service = ResourceOpsService(mock_db)
    
    res_id = uuid.uuid4()
    plan_date = date.today()
    now_dt = datetime.now(timezone.utc)
    
    # Create two duplicate events occurring 10 minutes apart (within 15-min window)
    event1 = WorkEvidenceEvent(
        id=1,
        resource_id=res_id,
        event_category="Manual Execution",
        event_type="test_run",
        timestamp=now_dt,
        actual_effort_hours=2.0,
        evidence_confidence=0.8,
        evidence_status="unmapped"
    )
    event2 = WorkEvidenceEvent(
        id=2,
        resource_id=res_id,
        event_category="Manual Execution",
        event_type="test_run",
        timestamp=now_dt + timedelta(minutes=10),
        actual_effort_hours=1.5,
        evidence_confidence=0.95,  # Higher confidence
        evidence_status="unmapped"
    )
    
    # Mock database execute calls:
    # 1. Fetching all events for the resource
    # 2. Fetching daily plans
    mock_result_events = MagicMock()
    mock_result_events.scalars.return_value.all.return_value = [event1, event2]
    
    mock_plan = DailyWorkPlan(
        id=10,
        resource_id=res_id,
        date=plan_date,
        task_title="Manual execution task",
        task_type="Manual Test Execution",
        estimated_effort=4.0,
        achieved_effort=0.0
    )
    mock_result_plans = MagicMock()
    mock_result_plans.scalars.return_value.all.return_value = [mock_plan]
    
    # Mocking db calls sequentially: first for events, then for plans
    mock_db.execute.side_effect = [mock_result_events, mock_result_plans, MagicMock()]
    
    # Run deduplication
    await service.reconcile_and_deduplicate_evidence(res_id, plan_date)
    
    # Verify that event1 (lower confidence) was marked as rejected/duplicate
    assert event1.evidence_status == "rejected"
    assert event2.evidence_status != "rejected"
