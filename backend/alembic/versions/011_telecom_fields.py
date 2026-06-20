"""Add telecom fields and quality review dimension scores.

Revision ID: 011_telecom_fields
Revises: 010_test_data_generation_import
Create Date: 2026-06-12 15:20:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011_telecom_fields"
down_revision: Union[str, None] = "010_test_data_generation_import"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add QA Domain & Classification fields to requirements
    op.add_column("requirements", sa.Column("qa_domain", sa.String(length=50), nullable=True))
    op.add_column("requirements", sa.Column("product_group", sa.String(length=60), nullable=True))
    op.add_column("requirements", sa.Column("product", sa.String(length=50), nullable=True))
    op.add_column("requirements", sa.Column("sub_request_type", sa.String(length=50), nullable=True))
    op.add_column("requirements", sa.Column("test_phase", sa.String(length=50), nullable=True))

    # 2. Add Telecom infrastructure fields to requirements
    op.add_column("requirements", sa.Column("impacted_systems", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("impacted_interfaces", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("impacted_products", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("impacted_channels", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("customer_segment", sa.String(length=200), nullable=True))
    op.add_column("requirements", sa.Column("business_process", sa.String(length=200), nullable=True))
    op.add_column("requirements", sa.Column("release_train", sa.String(length=100), nullable=True))
    op.add_column("requirements", sa.Column("release_version", sa.String(length=100), nullable=True))
    op.add_column("requirements", sa.Column("risk_level", sa.String(length=20), nullable=True))
    op.add_column("requirements", sa.Column("regulatory_impact", sa.Boolean(), nullable=True, server_default=sa.text("false")))
    op.add_column("requirements", sa.Column("revenue_impact", sa.Boolean(), nullable=True, server_default=sa.text("false")))
    op.add_column("requirements", sa.Column("customer_impact", sa.Boolean(), nullable=True, server_default=sa.text("false")))
    op.add_column("requirements", sa.Column("dependency_systems", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("upstream_systems", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("downstream_systems", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("api_interface_refs", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("environment_needs", sa.Text(), nullable=True))
    op.add_column("requirements", sa.Column("test_data_needs", sa.Text(), nullable=True))
    op.add_column("requirements", sa.Column("nfr_requirements", sa.Text(), nullable=True))
    op.add_column("requirements", sa.Column("readiness_status", sa.String(length=50), nullable=True))

    # 3. Add Jira enrichment fields to requirements
    op.add_column("requirements", sa.Column("jira_issue_id", sa.String(length=100), nullable=True))
    op.add_column("requirements", sa.Column("jira_status", sa.String(length=100), nullable=True))
    op.add_column("requirements", sa.Column("jira_assignee", sa.String(length=100), nullable=True))
    op.add_column("requirements", sa.Column("jira_reporter", sa.String(length=100), nullable=True))
    op.add_column("requirements", sa.Column("jira_labels", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("jira_components", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("jira_fix_versions", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("requirements", sa.Column("jira_sprint", sa.String(length=100), nullable=True))
    op.add_column("requirements", sa.Column("jira_epic_key", sa.String(length=100), nullable=True))
    op.add_column("requirements", sa.Column("sync_status", sa.String(length=20), nullable=True))
    op.add_column("requirements", sa.Column("sync_error", sa.Text(), nullable=True))

    # 4. Add Quality denormalization fields to requirements
    op.add_column("requirements", sa.Column("quality_score", sa.Float(), nullable=True))
    op.add_column("requirements", sa.Column("quality_feedback", sa.Text(), nullable=True))
    op.add_column("requirements", sa.Column("quality_verdict", sa.String(length=30), nullable=True))

    # 5. Add per-dimension scores to requirement_quality_reviews
    op.add_column("requirement_quality_reviews", sa.Column("completeness_score", sa.Float(), nullable=True))
    op.add_column("requirement_quality_reviews", sa.Column("clarity_score", sa.Float(), nullable=True))
    op.add_column("requirement_quality_reviews", sa.Column("testability_score", sa.Float(), nullable=True))
    op.add_column("requirement_quality_reviews", sa.Column("ambiguity_score", sa.Float(), nullable=True))
    op.add_column("requirement_quality_reviews", sa.Column("acceptance_criteria_score", sa.Float(), nullable=True))
    op.add_column("requirement_quality_reviews", sa.Column("interface_readiness_score", sa.Float(), nullable=True))
    op.add_column("requirement_quality_reviews", sa.Column("scenario_generation_readiness", sa.Float(), nullable=True))
    op.add_column("requirement_quality_reviews", sa.Column("qa_domain_completeness", sa.Float(), nullable=True))

    # 6. Create Indexes
    op.create_index("ix_requirements_qa_domain", "requirements", ["qa_domain"], unique=False)
    op.create_index("ix_requirements_product_group", "requirements", ["product_group"], unique=False)
    op.create_index("ix_requirements_product", "requirements", ["product"], unique=False)
    op.create_index("ix_requirements_sub_request_type", "requirements", ["sub_request_type"], unique=False)
    op.create_index("ix_requirements_risk_level", "requirements", ["risk_level"], unique=False)
    op.create_index("ix_requirements_test_phase", "requirements", ["test_phase"], unique=False)
    op.create_index("ix_requirements_readiness_status", "requirements", ["readiness_status"], unique=False)
    op.create_index("ix_requirements_sync_status", "requirements", ["sync_status"], unique=False)
    op.create_index("ix_requirements_release_version", "requirements", ["release_version"], unique=False)
    op.create_index("uq_requirements_jira_issue_id", "requirements", ["jira_issue_id"], unique=True)

    op.create_index("ix_requirements_impacted_systems", "requirements", ["impacted_systems"], postgresql_using="gin")
    op.create_index("ix_requirements_impacted_interfaces", "requirements", ["impacted_interfaces"], postgresql_using="gin")
    op.create_index("ix_requirements_impacted_products", "requirements", ["impacted_products"], postgresql_using="gin")
    op.create_index("ix_requirements_impacted_channels", "requirements", ["impacted_channels"], postgresql_using="gin")


def downgrade() -> None:
    # Drop Indexes
    op.drop_index("ix_requirements_impacted_channels", table_name="requirements")
    op.drop_index("ix_requirements_impacted_products", table_name="requirements")
    op.drop_index("ix_requirements_impacted_interfaces", table_name="requirements")
    op.drop_index("ix_requirements_impacted_systems", table_name="requirements")
    op.drop_index("uq_requirements_jira_issue_id", table_name="requirements")
    op.drop_index("ix_requirements_release_version", table_name="requirements")
    op.drop_index("ix_requirements_sync_status", table_name="requirements")
    op.drop_index("ix_requirements_readiness_status", table_name="requirements")
    op.drop_index("ix_requirements_test_phase", table_name="requirements")
    op.drop_index("ix_requirements_risk_level", table_name="requirements")
    op.drop_index("ix_requirements_sub_request_type", table_name="requirements")
    op.drop_index("ix_requirements_product", table_name="requirements")
    op.drop_index("ix_requirements_product_group", table_name="requirements")
    op.drop_index("ix_requirements_qa_domain", table_name="requirements")

    # Drop columns from requirement_quality_reviews
    op.drop_column("requirement_quality_reviews", "qa_domain_completeness")
    op.drop_column("requirement_quality_reviews", "scenario_generation_readiness")
    op.drop_column("requirement_quality_reviews", "interface_readiness_score")
    op.drop_column("requirement_quality_reviews", "acceptance_criteria_score")
    op.drop_column("requirement_quality_reviews", "ambiguity_score")
    op.drop_column("requirement_quality_reviews", "testability_score")
    op.drop_column("requirement_quality_reviews", "clarity_score")
    op.drop_column("requirement_quality_reviews", "completeness_score")

    # Drop columns from requirements
    columns_to_drop = [
        "qa_domain", "product_group", "product", "sub_request_type", "test_phase",
        "impacted_systems", "impacted_interfaces", "impacted_products", "impacted_channels",
        "customer_segment", "business_process", "release_train", "release_version", "risk_level",
        "regulatory_impact", "revenue_impact", "customer_impact", "dependency_systems",
        "upstream_systems", "downstream_systems", "api_interface_refs", "environment_needs",
        "test_data_needs", "nfr_requirements", "readiness_status", "jira_issue_id",
        "jira_status", "jira_assignee", "jira_reporter", "jira_labels", "jira_components",
        "jira_fix_versions", "jira_sprint", "jira_epic_key", "sync_status", "sync_error",
        "quality_score", "quality_feedback", "quality_verdict"
    ]
    for col in columns_to_drop:
        op.drop_column("requirements", col)
