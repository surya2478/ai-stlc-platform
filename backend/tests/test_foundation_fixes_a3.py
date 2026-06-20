import pytest
from app.config import Settings
from app.core.startup_checks import validate_production_config
from app.models.execution import ExecutionRun


def test_validate_production_config_non_production():
    # In non-production, no checks should cause RuntimeError even if secret is default or debug is True
    settings = Settings(
        app_env="local",
        app_secret_key="change-me",
        app_debug=True,
        demo_mode=True
    )
    # This should not raise any error
    validate_production_config(settings)


def test_validate_production_config_production_valid():
    # Valid production settings
    settings = Settings(
        app_env="production",
        app_secret_key="a-very-secure-secret-key-1234567",
        app_debug=False,
        demo_mode=False
    )
    # This should pass without raising RuntimeError
    validate_production_config(settings)


def test_validate_production_config_production_invalid_secret():
    settings = Settings(
        app_env="local",
        app_secret_key="change-me",
        app_debug=False,
        demo_mode=False
    )
    settings.app_env = "production"
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_config(settings)
    assert "APP_SECRET_KEY is set to 'change-me'" in str(exc_info.value) or "forbidden placeholder value" in str(exc_info.value)


def test_validate_production_config_production_invalid_debug():
    settings = Settings(
        app_env="local",
        app_secret_key="a-very-secure-secret-key-1234567",
        app_debug=True,
        demo_mode=False
    )
    settings.app_env = "production"
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_config(settings)
    assert "APP_DEBUG is set to True" in str(exc_info.value)


def test_validate_production_config_production_invalid_demo():
    settings = Settings(
        app_env="local",
        app_secret_key="a-very-secure-secret-key-1234567",
        app_debug=False,
        demo_mode=True
    )
    settings.app_env = "production"
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_config(settings)
    assert "DEMO_MODE is set to True" in str(exc_info.value)



def test_execution_run_simulated_field():
    run = ExecutionRun(
        project_id=1,
        created_by=1,
        execution_id="EXEC-0001",
        simulated=True
    )
    assert run.simulated is True

    run_default = ExecutionRun(
        project_id=1,
        created_by=1,
        execution_id="EXEC-0002",
        simulated=False
    )
    assert run_default.simulated is False


def test_test_case_telecom_fields():
    from app.models.test_case import TestCase

    tc = TestCase(
        project_id=1,
        created_by=1,
        test_case_id="TC-0001",
        title="Check case classification",
        product_group="BusinessLite",
        product="GSM Prepaid",
        sub_request_type="Add Service"
    )
    assert tc.product_group == "BusinessLite"
    assert tc.product == "GSM Prepaid"
    assert tc.sub_request_type == "Add Service"


def test_test_data_telecom_fields():
    from app.models.test_data import TestData

    td = TestData(
        project_id=1,
        created_by=1,
        data_id="TD-0001",
        name="Synthetic eSIM profile",
        product_group="Figital Services",
        product="Global IPVPN",
        sub_request_type="New Account"
    )
    assert td.product_group == "Figital Services"
    assert td.product == "Global IPVPN"
    assert td.sub_request_type == "New Account"
