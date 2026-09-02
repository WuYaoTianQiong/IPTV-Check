"""add check_history.last_updated

Revision ID: a1b2c3d4e5f6
Revises: 02e36ff89761
Create Date: 2026-09-01 00:00:00.000000

last_updated 用于前端"最后更新"展示。旧库可能已通过 event_store 的手写
ALTER 加过该列，因此 upgrade 前先查 PRAGMA table_info 做容错。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '02e36ff89761'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(check_history)")).fetchall()]
    if "last_updated" not in cols:
        op.add_column("check_history", sa.Column("last_updated", sa.DateTime(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(check_history)")).fetchall()]
    if "last_updated" in cols:
        op.drop_column("check_history", "last_updated")
