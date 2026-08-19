"""email-verification auth: wipe users/jobs, users.email + is_verified, drop username

Revision ID: b2c5e7a9f3d1
Revises: a1f4c9d2e7b3
Create Date: 2026-08-19

清库重建（Plan B）：按 FK 顺序 DELETE job_steps → jobs → users（llm_providers 保留）。
users 加 email(unique)/is_verified，drop username。Downgrade 反向操作，
但被清数据不可恢复（本迁移即明确弃数据）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c5e7a9f3d1'
down_revision: Union[str, Sequence[str], None] = 'a1f4c9d2e7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # FK 顺序：先子后父（sqlite PRAGMA foreign_keys=ON / PG 均强制）
    op.execute("DELETE FROM job_steps;")
    op.execute("DELETE FROM jobs;")
    op.execute("DELETE FROM users;")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_username")  # 旧 username 唯一索引：batch 重建时必须先删
        batch.add_column(sa.Column("email", sa.String(length=255), nullable=False))
        batch.add_column(sa.Column("is_verified", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.drop_column("username")
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    """Downgrade schema. 数据不可恢复（upgrade 已清库）。"""
    op.drop_index("ix_users_email", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_verified")
        batch.drop_column("email")
        batch.add_column(sa.Column("username", sa.String(length=64), nullable=True))
    # username 原 NOT NULL unique，但用户行已被 upgrade 清空 → 空表可直接置 NOT NULL
    with op.batch_alter_table("users") as batch:
        batch.alter_column("username", existing_type=sa.String(length=64),
                           nullable=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
