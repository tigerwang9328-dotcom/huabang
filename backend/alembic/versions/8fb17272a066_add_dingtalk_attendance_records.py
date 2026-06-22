"""add dingtalk attendance records

Revision ID: 8fb17272a066
Revises: ac7a05414061
Create Date: 2026-06-21 19:00:28.793515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8fb17272a066'
down_revision: Union[str, None] = 'ac7a05414061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dingtalk_attendance_records',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('dingtalk_user_id', sa.String(length=128), nullable=True),
        sa.Column('user_name', sa.String(length=128), nullable=True),
        sa.Column('department_id', sa.String(length=64), nullable=True),
        sa.Column('department_name', sa.String(length=128), nullable=True),
        sa.Column('work_date', sa.Date(), nullable=True),
        sa.Column('check_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('check_type', sa.String(length=32), nullable=True),
        sa.Column('time_result', sa.String(length=32), nullable=True),
        sa.Column('location_result', sa.String(length=32), nullable=True),
        sa.Column('source_type', sa.String(length=32), nullable=True),
        sa.Column('approve_id', sa.String(length=128), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dingtalk_user_id', 'work_date', 'check_time', 'check_type', name='uq_dt_attendance'),
    )
    op.create_index('ix_dingtalk_attendance_records_dingtalk_user_id', 'dingtalk_attendance_records', ['dingtalk_user_id'])
    op.create_index('ix_dingtalk_attendance_records_work_date', 'dingtalk_attendance_records', ['work_date'])
    op.create_index('ix_dingtalk_attendance_records_time_result', 'dingtalk_attendance_records', ['time_result'])
    op.create_index('ix_dingtalk_attendance_records_created_at', 'dingtalk_attendance_records', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_dingtalk_attendance_records_created_at', table_name='dingtalk_attendance_records')
    op.drop_index('ix_dingtalk_attendance_records_time_result', table_name='dingtalk_attendance_records')
    op.drop_index('ix_dingtalk_attendance_records_work_date', table_name='dingtalk_attendance_records')
    op.drop_index('ix_dingtalk_attendance_records_dingtalk_user_id', table_name='dingtalk_attendance_records')
    op.drop_table('dingtalk_attendance_records')
