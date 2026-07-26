"""
ORM model registry.  Import all models here so Alembic autogenerate picks them up.
"""
from app.models.base import TimestampMixin  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.project_membership import ProjectMembership  # noqa: F401
from app.models.llm_settings import ProjectLLMSetting, ProjectSettingAuditLog  # noqa: F401
from app.models.project_application import ProjectApplication, ProjectExternalDependency  # noqa: F401
from app.models.jira_connection import JiraConnection  # noqa: F401
from app.models.document import UploadedDocument  # noqa: F401
from app.models.requirement import Requirement, RequirementChunk  # noqa: F401
from app.models.requirement_review import RequirementQualityReview  # noqa: F401
from app.models.test_plan import TestPlan, PlanTestCase  # noqa: F401
from app.models.test_scenario import TestScenario  # noqa: F401
from app.models.test_case import TestCase, TestCaseHistory, TestCaseImportPreview  # noqa: F401
from app.models.test_suite import TestSuite  # noqa: F401
from app.models.test_data import TestData, TestDataImportPreview, TestDataRecord, TestDataTemplate  # noqa: F401
from app.models.automation_mapping import AutomationTestMapping  # noqa: F401
from app.models.automation_script import AutomationScript  # noqa: F401
from app.models.execution import ExecutionRun, ExecutionResult, ManualStepResult  # noqa: F401
from app.models.defect import DefectDraft, JiraDefect  # noqa: F401
from app.models.report import Report  # noqa: F401
from app.models.agent import AgentRun, AgentLog  # noqa: F401
from app.models.approval import ApprovalAction  # noqa: F401
from app.models.artifact import Artifact  # noqa: F401
from app.models.rag import KnowledgeChunk, ArtifactCitation, RagRetrievalEvent  # noqa: F401
from app.models.taxonomy import (  # noqa: F401
    QADomain,
    ProductGroup,
    Product,
    System,
    SubRequestType,
    TestCaseType,
    TestCaseComplexity,
    Environment,
    TaxonomyRelationship,
)
from app.models.assistant import (  # noqa: F401
    AssistantConversation,
    AssistantMessage,
    AssistantAuditEvent,
    AssistantFeedback,
    AssistantKnowledgeSource,
    AssistantRetrievalEvent,
)
from app.models.resource_ops import (  # noqa: F401
    Resource,
    ResourceIdentityMapping,
    IntegrationConnection,
    DailyWorkPlan,
    WorkEvidenceEvent,
    AIEstimate,
)
from app.models.artifact_review import ArtifactReview  # noqa: F401
from app.models.coverage_matrix import CoverageMatrixEntry  # noqa: F401
from app.models.locator_map import LocatorMapEntry  # noqa: F401
from app.models.studio_run import StudioRun  # noqa: F401
from app.models.mcp_connection import MCPConnection  # noqa: F401
from app.models.grounded_poc import PocGroundingRun, PocStateEvidence  # noqa: F401
from app.models.automation_classification import (  # noqa: F401
    AutomationClassificationPolicy,
    TestCaseAutomationClassification,
    ClassificationFieldCorrection,
    ClassificationAuditEvent,
)
from app.models.discovery_session import (  # noqa: F401
    DiscoverySession,
    DiscoveryAction,
    DiscoveryCheckpoint,
    DiscoveryCapture,
    DiscoverySessionEvent,
)
from app.models.application_model import (  # noqa: F401
    ApplicationModel,
    ApplicationModelNode,
    ApplicationModelEdge,
    ApplicationModelLocatorEvidence,
    ApplicationModelGap,
    ApplicationModelActivity,
)
from app.models.network_event import NetworkEvent, NetworkEventActivity  # noqa: F401
from app.models.automation_suite import (  # noqa: F401
    AutomationSuite,
    AutomationSuiteTestCase,
    AutomationSuiteGap,
    AutomationSuiteActivity,
    AutomationSuiteExecutionGroup,
    AutomationSuiteSnapshot,
)


