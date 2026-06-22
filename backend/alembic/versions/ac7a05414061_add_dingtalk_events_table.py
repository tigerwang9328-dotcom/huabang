"""add dingtalk events table

Revision ID: ac7a05414061
Revises:
Create Date: 2026-06-21 17:46:36.634634

注意：autogenerate 因本库历史未走 alembic、且 include_schemas=True，
产生了大量对其它 schema 表的 alter/drop 无关改动。已按要求全部手工剔除，
本迁移仅新增 dingtalk_events 一张表，不触碰任何现有表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ac7a05414061'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dingtalk_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=128), nullable=True, comment='钉钉 eventId，幂等去重键（可空）'),
        sa.Column('event_type', sa.String(length=128), nullable=True, comment='事件类型，如 bpms_instance_change'),
        sa.Column('corp_id', sa.String(length=128), nullable=True, comment='企业 corpId'),
        sa.Column('event_born_time', sa.BigInteger(), nullable=True, comment='事件产生时间(ms)'),
        sa.Column('topic', sa.String(length=128), nullable=True, comment='Stream topic'),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='完整原始事件数据'),
        sa.Column('status', sa.String(length=32), nullable=False, comment='received/processed/failed'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='处理失败原因'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True, comment='业务处理完成时间'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id'),
    )
    op.create_index('ix_dingtalk_events_event_type', 'dingtalk_events', ['event_type'], unique=False)
    op.create_index('ix_dingtalk_events_status', 'dingtalk_events', ['status'], unique=False)
    op.create_index('ix_dingtalk_events_created_at', 'dingtalk_events', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_dingtalk_events_created_at', table_name='dingtalk_events')
    op.drop_index('ix_dingtalk_events_status', table_name='dingtalk_events')
    op.drop_index('ix_dingtalk_events_event_type', table_name='dingtalk_events')
    op.drop_table('dingtalk_events')
