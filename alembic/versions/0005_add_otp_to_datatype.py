"""add otp value to datatype enum

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE datatype ADD VALUE IF NOT EXISTS 'otp'")


def downgrade() -> None:
    op.execute("""
        ALTER TYPE datatype RENAME TO datatype_old;
        CREATE TYPE datatype AS ENUM ('password', 'card', 'text', 'binary');
        ALTER TABLE items
            ALTER COLUMN type TYPE datatype
            USING type::text::datatype;
        DROP TYPE datatype_old;
    """)
    