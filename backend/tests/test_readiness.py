import anyio

from app.services.automation_runner.readiness import ReadinessInputs, check_readiness


def test_missing_application_url_blocks_readiness():
    async def run():
        return await check_readiness(ReadinessInputs(application_url=None))
    result = anyio.run(run)
    assert result.ready is False
    names = {c.name for c in result.blockers}
    assert "application_url_reachable" in names


def test_unreachable_application_url_blocks_readiness():
    async def run():
        return await check_readiness(ReadinessInputs(application_url="http://127.0.0.1:1/not-listening"))
    result = anyio.run(run)
    assert result.ready is False
    assert any(c.name == "application_url_reachable" and not c.passed for c in result.checks)


def test_credentials_not_required_by_default():
    async def run():
        return await check_readiness(ReadinessInputs(application_url=None, credentials_required=False))
    result = anyio.run(run)
    cred_check = next(c for c in result.checks if c.name == "credentials_configured")
    assert cred_check.passed is True


def test_credentials_required_and_missing_blocks_readiness():
    async def run():
        return await check_readiness(ReadinessInputs(application_url=None, credentials_required=True))
    result = anyio.run(run)
    cred_check = next(c for c in result.checks if c.name == "credentials_configured")
    assert cred_check.passed is False


def test_credentials_required_and_present_but_empty_file_blocks(tmp_path):
    empty_file = tmp_path / "storage_state.json"
    empty_file.write_text("")

    async def run():
        return await check_readiness(ReadinessInputs(
            application_url=None, credentials_required=True, storage_state_path=str(empty_file),
        ))
    result = anyio.run(run)
    cred_check = next(c for c in result.checks if c.name == "credentials_configured")
    assert cred_check.passed is False
    assert "empty" in cred_check.detail.lower()


def test_credentials_required_and_present_and_populated_passes(tmp_path):
    state_file = tmp_path / "storage_state.json"
    state_file.write_text("{}")

    async def run():
        return await check_readiness(ReadinessInputs(
            application_url=None, credentials_required=True, storage_state_path=str(state_file),
        ))
    result = anyio.run(run)
    cred_check = next(c for c in result.checks if c.name == "credentials_configured")
    assert cred_check.passed is True


def test_optional_dependencies_skip_cleanly_when_unconfigured():
    async def run():
        return await check_readiness(ReadinessInputs(application_url=None))
    result = anyio.run(run)
    api_check = next(c for c in result.checks if c.name == "api_dependency_healthy")
    db_check = next(c for c in result.checks if c.name == "db_validation_endpoint_reachable")
    assert api_check.passed is True
    assert db_check.passed is True


def test_maintenance_flag_blocks_readiness():
    async def run():
        return await check_readiness(ReadinessInputs(
            application_url=None, environment_under_maintenance=True, maintenance_detail="Down for upgrade until 5pm",
        ))
    result = anyio.run(run)
    maint_check = next(c for c in result.checks if c.name == "environment_not_under_maintenance")
    assert maint_check.passed is False
    assert "5pm" in maint_check.detail
