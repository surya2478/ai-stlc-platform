from __future__ import annotations

from app.integrations.automation.base_connector import AutomationConnector
from app.integrations.automation.mock_connector import MockAutomationConnector


def get_automation_connector(tool_name: str | None) -> AutomationConnector:
    # Phase 1 ships with a mock connector. Real connectors can be registered here
    # without changing the endpoint/service contract.
    return MockAutomationConnector()
