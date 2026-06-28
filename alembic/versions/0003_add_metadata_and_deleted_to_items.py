"""add metadata and deleted columns to items

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("metadata", sa.JSON(), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.alter_column("items", "deleted", server_default=None)


def downgrade() -> None:
    op.drop_column("items", "deleted")
    op.drop_column("items", "metadata")
