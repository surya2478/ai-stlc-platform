"""Shared context object threaded through policy resolution, deterministic
rules, capability resolution and scoring — avoids each module re-querying
the same rows."""
from __future__ import annotations

from dataclasses import dataclass

from app.models.automation_classification import AutomationClassificationPolicy
from app.models.project_application import ProjectApplication
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_scenario import TestScenario


@dataclass
class ClassificationContext:
    test_case: TestCase
    requirement: Requirement | None
    scenario: TestScenario | None
    application: ProjectApplication | None
    policy: AutomationClassificationPolicy
