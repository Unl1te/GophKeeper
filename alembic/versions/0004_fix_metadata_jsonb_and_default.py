
"""alter metadata column to JSONB with default {}

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Convert JSON → JSONB and set server default to empty object.
        op.alter_column(
            "items",
            "metadata",
            type_=postgresql.JSONB(),
            server_default="{}",
            existing_nullable=True,
        )
    else:
        # SQLite (used in tests) does not support JSONB — just add the default.
        op.alter_column(
            "items",
            "metadata",
            server_default="{}",
            existing_nullable=True,
            existing_type=sa.JSON(),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "items",
            "metadata",
            type_=sa.JSON(),
            server_default=None,
            existing_nullable=True,
        )
    else:
        op.alter_column(
            "items",
            "metadata",
            server_default=None,
            existing_nullable=True,
            existing_type=sa.JSON(),
        )
        