from app.agents.automation.automation_agent import _parse_script_response


def test_parse_script_response_recovers_raw_multiline_code_json():
    raw = '''```json
{
  "test_case_id": "TC-0001",
  "framework": "pytest",
  "file_path": "tests/test_missing_dashboard.py",
  "code": "
import pytest
from loguru import logger

def test_missing_dashboard():
    logger.info("dashboard is missing")
    assert True
",
  "setup_required": ["pytest", "loguru"],
  "execution_command": "pytest tests/test_missing_dashboard.py -v"
}
```'''

    script, error = _parse_script_response(raw, "pytest")

    assert error is None
    assert script is not None
    assert script["test_case_id"] == "TC-0001"
    assert script["setup_required"] == ["pytest", "loguru"]
    assert 'logger.info("dashboard is missing")' in script["code"]
