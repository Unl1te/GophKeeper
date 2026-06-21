"""add type column to items

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

datatype_enum = sa.Enum(
    "password", "card", "text", "binary", name="datatype"
)


def upgrade() -> None:
    datatype_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "items",
        sa.Column("type", datatype_enum, nullable=False, server_default="text"),
    )
    op.alter_column("items", "type", server_default=None)


def downgrade() -> None:
    op.drop_column("items", "type")
    datatype_enum.drop(op.get_bind(), checkfirst=True)