"""V2: add generation_status to courses (F-016 Progressive Course Delivery)

Revision ID: 20250311_v2
Revises: 20250309_v1
Create Date: 2025-03-11

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20250311_v2"
down_revision: Union[str, None] = "20250309_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("generation_status", sa.Text(), nullable=False, server_default="complete"),
    )


def downgrade() -> None:
    op.drop_column("courses", "generation_status")
