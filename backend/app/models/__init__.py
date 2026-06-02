"""
ORM model registry.  Import all models here so Alembic autogenerate picks them up.
"""
from app.models.base import TimestampMixin  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.jira_connection import JiraConnection  # noqa: F401
from app.models.document import UploadedDocument  # noqa: F401
from app.models.requirement import Requirement, RequirementChunk  # noqa: F401
from app.models.requirement_review import RequirementQualityReview  # noqa: F401
from app.models.test_plan import TestPlan  # noqa: F401
from app.models.test_scenario import TestScenario  # noqa: F401
from app.models.test_case import TestCase  # noqa: F401
from app.models.test_data import TestData  # noqa: F401
from app.models.automation_script import AutomationScript  # noqa: F401
from app.models.execution import ExecutionRun, ExecutionResult  # noqa: F401
from app.models.defect import DefectDraft, JiraDefect  # noqa: F401
from app.models.report import Report  # noqa: F401
from app.models.agent import AgentRun, AgentLog  # noqa: F401
from app.models.approval import ApprovalAction  # noqa: F401
from app.models.artifact import Artifact  # noqa: F401
