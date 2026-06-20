"""Add product_group, product, and sub_request_type to test_cases and test_data.

Revision ID: 013_tc_td_telecom_fields
Revises: 012_execution_simulated_field
Create Date: 2026-06-12 16:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_tc_td_telecom_fields"
down_revision: Union[str, None] = "012_execution_simulated_field"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to test_cases
    op.add_column("test_cases", sa.Column("product_group", sa.String(length=60), nullable=True))
    op.add_column("test_cases", sa.Column("product", sa.String(length=50), nullable=True))
    op.add_column("test_cases", sa.Column("sub_request_type", sa.String(length=50), nullable=True))

    # 2. Create Indexes for test_cases
    op.create_index("ix_test_cases_product_group", "test_cases", ["product_group"], unique=False)
    op.create_index("ix_test_cases_product", "test_cases", ["product"], unique=False)
    op.create_index("ix_test_cases_sub_request_type", "test_cases", ["sub_request_type"], unique=False)

    # 3. Add columns to test_data
    op.add_column("test_data", sa.Column("product_group", sa.String(length=60), nullable=True))
    op.add_column("test_data", sa.Column("product", sa.String(length=50), nullable=True))
    op.add_column("test_data", sa.Column("sub_request_type", sa.String(length=50), nullable=True))

    # 4. Create Indexes for test_data
    op.create_index("ix_test_data_product_group", "test_data", ["product_group"], unique=False)
    op.create_index("ix_test_data_product", "test_data", ["product"], unique=False)
    op.create_index("ix_test_data_sub_request_type", "test_data", ["sub_request_type"], unique=False)


def downgrade() -> None:
    # Drop Indexes for test_data
    op.drop_index("ix_test_data_sub_request_type", table_name="test_data")
    op.drop_index("ix_test_data_product", table_name="test_data")
    op.drop_index("ix_test_data_product_group", table_name="test_data")

    # Drop columns from test_data
    op.drop_column("test_data", "sub_request_type")
    op.drop_column("test_data", "product")
    op.drop_column("test_data", "product_group")

    # Drop Indexes for test_cases
    op.drop_index("ix_test_cases_sub_request_type", table_name="test_cases")
    op.drop_index("ix_test_cases_product", table_name="test_cases")
    op.drop_index("ix_test_cases_product_group", table_name="test_cases")

    # Drop columns from test_cases
    op.drop_column("test_cases", "sub_request_type")
    op.drop_column("test_cases", "product")
    op.drop_column("test_cases", "product_group")
