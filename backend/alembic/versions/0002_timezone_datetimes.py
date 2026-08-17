"""datetime columns -> timezone-aware (timestamptz on PG; no-op on sqlite)

Revision ID: a1f4c9d2e7b3
Revises: 0bbc71283019
Create Date: 2026-08-17

SQLite ignores the timezone flag, so alter_column is safe on both dialects.
On PostgreSQL the column type becomes TIMESTAMP WITH TIME ZONE; existing
naive timestamps are interpreted in the session timezone (UTC on our server).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1f4c9d2e7b3'
down_revision: Union[str, Sequence[str], None] = '0bbc71283019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TZ_COLUMNS = [
    ("users", "created_at"),
    ("jobs", "created_at"),
    ("jobs", "started_at"),
    ("jobs", "finished_at"),
    ("job_steps", "created_at"),
    ("llm_providers", "created_at"),
]


def upgrade() -> None:
    """Upgrade schema."""
    for table, column in TZ_COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.DateTime(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=False,
            )


def downgrade() -> None:
    """Downgrade schema."""
    for table, column in TZ_COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(),
                existing_nullable=False,
            )
