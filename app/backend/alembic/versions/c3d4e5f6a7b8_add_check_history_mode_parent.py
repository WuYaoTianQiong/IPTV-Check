"""add check_history.check_mode / parent_session_id

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-02 00:00:00.000000

check_mode 记录会话使用的检测方案（quick/standard/deep）；
parent_session_id 记录"细筛"会话的来源粗筛会话，用于前端展示关联。
旧库可能已手写 ALTER 加过列，因此 upgrade 前先查 PRAGMA table_info 做容错。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(check_history)")).fetchall()]
    if "check_mode" not in cols:
        op.add_column("check_history", sa.Column("check_mode", sa.String(), nullable=True))
    if "parent_session_id" not in cols:
        op.add_column("check_history", sa.Column("parent_session_id", sa.String(), nullable=True))
        op.create_index("ix_check_history_parent_session_id", "check_history", ["parent_session_id"])


def downgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(check_history)")).fetchall()]
    if "parent_session_id" in cols:
        op.drop_index("ix_check_history_parent_session_id", table_name="check_history")
        op.drop_column("check_history", "parent_session_id")
    if "check_mode" in cols:
        op.drop_column("check_history", "check_mode")
