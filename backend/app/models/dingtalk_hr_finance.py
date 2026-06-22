"""钉钉 人事/财务 业务表（员工/部门/审批实例/财务费用/人事考勤日汇总）。

分层：dingtalk_* 偏 ODS/DWD（原始+清洗），finance_*/hr_* 偏 ADS（业务汇总）。
"""
from sqlalchemy import Column, String, BigInteger, Integer, Boolean, Date, DateTime, Text, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class DingtalkEmployee(Base):
    """钉钉员工档案。"""
    __tablename__ = "dingtalk_employees"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dingtalk_user_id = Column(String(128), unique=True, nullable=False, comment="钉钉 userId")
    name = Column(String(128), nullable=True)
    mobile = Column(String(32), nullable=True)
    department_ids = Column(JSONB, nullable=True)
    department_names = Column(JSONB, nullable=True)
    position = Column(String(128), nullable=True)
    job_number = Column(String(64), nullable=True)
    email = Column(String(128), nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DingtalkDepartment(Base):
    """钉钉部门。"""
    __tablename__ = "dingtalk_departments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dingtalk_dept_id = Column(String(64), unique=True, nullable=False, comment="钉钉部门ID")
    name = Column(String(128), nullable=True)
    parent_id = Column(String(64), nullable=True)
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DingtalkApprovalInstance(Base):
    """钉钉审批实例（报销/付款/请假/出差/考勤等）。"""
    __tablename__ = "dingtalk_approval_instances"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    process_instance_id = Column(String(128), unique=True, nullable=False)
    process_code = Column(String(128), index=True, nullable=True)
    process_name = Column(String(256), nullable=True)
    business_id = Column(String(128), nullable=True)
    title = Column(String(512), nullable=True)
    originator_user_id = Column(String(128), index=True, nullable=True)
    originator_name = Column(String(128), nullable=True)
    originator_dept_id = Column(String(64), nullable=True)
    originator_dept_name = Column(String(128), nullable=True)
    status = Column(String(32), nullable=True, comment="NEW/RUNNING/COMPLETED/TERMINATED/CANCELED")
    result = Column(String(32), nullable=True, comment="agree/refuse")
    create_time = Column(DateTime(timezone=True), nullable=True)
    finish_time = Column(DateTime(timezone=True), nullable=True)
    category = Column(String(32), index=True, nullable=True, comment="reimbursement/payment/leave/business_trip/attendance/other")
    amount = Column(Numeric(18, 2), nullable=True)
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class FinanceExpenseRecord(Base):
    """财务费用明细（报销/付款，来自钉钉审批解析）。"""
    __tablename__ = "finance_expense_records"
    __table_args__ = (
        UniqueConstraint("source", "source_instance_id", name="uq_finance_expense_source"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(32), default="dingtalk", nullable=False)
    source_instance_id = Column(String(128), nullable=True, comment="钉钉审批 process_instance_id")
    applicant_user_id = Column(String(128), index=True, nullable=True)
    applicant_name = Column(String(128), nullable=True)
    department_name = Column(String(128), nullable=True)
    expense_type = Column(String(128), nullable=True)
    amount = Column(Numeric(18, 2), nullable=True)
    expense_date = Column(Date, index=True, nullable=True)
    approval_status = Column(String(32), nullable=True)
    payment_status = Column(String(32), nullable=True, comment="unpaid/paid/unknown")
    category = Column(String(32), index=True, nullable=True, comment="reimbursement/payment")
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HrAttendanceDaily(Base):
    """人事考勤日汇总（按 员工 x 日 聚合）。"""
    __tablename__ = "hr_attendance_daily"
    __table_args__ = (
        UniqueConstraint("work_date", "dingtalk_user_id", name="uq_hr_attendance_daily"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    work_date = Column(Date, index=True, nullable=False)
    dingtalk_user_id = Column(String(128), index=True, nullable=False)
    employee_name = Column(String(128), nullable=True)
    department_name = Column(String(128), nullable=True)
    normal_count = Column(Integer, default=0, nullable=False)
    late_count = Column(Integer, default=0, nullable=False)
    early_leave_count = Column(Integer, default=0, nullable=False)
    missing_check_count = Column(Integer, default=0, nullable=False)
    leave_count = Column(Integer, default=0, nullable=False)
    attendance_status = Column(String(32), nullable=True, comment="normal/abnormal/leave")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
