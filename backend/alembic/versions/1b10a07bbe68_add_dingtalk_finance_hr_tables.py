"""add dingtalk finance hr tables

Revision ID: 1b10a07bbe68
Revises: 8fb17272a066
Create Date: 2026-06-22

仅新增 5 张表（员工/部门/审批实例/财务费用/人事考勤日汇总）及索引，不触碰任何现有表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '1b10a07bbe68'
down_revision: Union[str, None] = '8fb17272a066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # dingtalk_employees
    op.create_table(
        'dingtalk_employees',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('dingtalk_user_id', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=True),
        sa.Column('mobile', sa.String(length=32), nullable=True),
        sa.Column('department_ids', JSONB, nullable=True),
        sa.Column('department_names', JSONB, nullable=True),
        sa.Column('position', sa.String(length=128), nullable=True),
        sa.Column('job_number', sa.String(length=64), nullable=True),
        sa.Column('email', sa.String(length=128), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dingtalk_user_id'),
    )
    # dingtalk_departments
    op.create_table(
        'dingtalk_departments',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('dingtalk_dept_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=True),
        sa.Column('parent_id', sa.String(length=64), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dingtalk_dept_id'),
    )
    # dingtalk_approval_instances
    op.create_table(
        'dingtalk_approval_instances',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('process_instance_id', sa.String(length=128), nullable=False),
        sa.Column('process_code', sa.String(length=128), nullable=True),
        sa.Column('process_name', sa.String(length=256), nullable=True),
        sa.Column('business_id', sa.String(length=128), nullable=True),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('originator_user_id', sa.String(length=128), nullable=True),
        sa.Column('originator_name', sa.String(length=128), nullable=True),
        sa.Column('originator_dept_id', sa.String(length=64), nullable=True),
        sa.Column('originator_dept_name', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('result', sa.String(length=32), nullable=True),
        sa.Column('create_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finish_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('category', sa.String(length=32), nullable=True),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('process_instance_id'),
    )
    op.create_index('ix_dt_approval_process_code', 'dingtalk_approval_instances', ['process_code'])
    op.create_index('ix_dt_approval_originator', 'dingtalk_approval_instances', ['originator_user_id'])
    op.create_index('ix_dt_approval_category', 'dingtalk_approval_instances', ['category'])
    op.create_index('ix_dt_approval_created_at', 'dingtalk_approval_instances', ['created_at'])
    # finance_expense_records
    op.create_table(
        'finance_expense_records',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False, server_default='dingtalk'),
        sa.Column('source_instance_id', sa.String(length=128), nullable=True),
        sa.Column('applicant_user_id', sa.String(length=128), nullable=True),
        sa.Column('applicant_name', sa.String(length=128), nullable=True),
        sa.Column('department_name', sa.String(length=128), nullable=True),
        sa.Column('expense_type', sa.String(length=128), nullable=True),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('expense_date', sa.Date(), nullable=True),
        sa.Column('approval_status', sa.String(length=32), nullable=True),
        sa.Column('payment_status', sa.String(length=32), nullable=True),
        sa.Column('category', sa.String(length=32), nullable=True),
        sa.Column('raw_payload', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_instance_id', name='uq_finance_expense_source'),
    )
    op.create_index('ix_finance_expense_applicant', 'finance_expense_records', ['applicant_user_id'])
    op.create_index('ix_finance_expense_date', 'finance_expense_records', ['expense_date'])
    op.create_index('ix_finance_expense_category', 'finance_expense_records', ['category'])
    op.create_index('ix_finance_expense_created_at', 'finance_expense_records', ['created_at'])
    # hr_attendance_daily
    op.create_table(
        'hr_attendance_daily',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('dingtalk_user_id', sa.String(length=128), nullable=False),
        sa.Column('employee_name', sa.String(length=128), nullable=True),
        sa.Column('department_name', sa.String(length=128), nullable=True),
        sa.Column('normal_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('late_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('early_leave_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('missing_check_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('leave_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attendance_status', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('work_date', 'dingtalk_user_id', name='uq_hr_attendance_daily'),
    )
    op.create_index('ix_hr_att_daily_work_date', 'hr_attendance_daily', ['work_date'])
    op.create_index('ix_hr_att_daily_user', 'hr_attendance_daily', ['dingtalk_user_id'])


def downgrade() -> None:
    op.drop_table('hr_attendance_daily')
    op.drop_table('finance_expense_records')
    op.drop_table('dingtalk_approval_instances')
    op.drop_table('dingtalk_departments')
    op.drop_table('dingtalk_employees')
