"""钉钉考勤打卡记录表（主动同步钉钉已有考勤数据）。"""
from sqlalchemy import Column, String, BigInteger, Date, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class DingtalkAttendanceRecord(Base):
    """钉钉考勤打卡结果（一条 = 一次打卡，OnDuty/OffDuty）。"""

    __tablename__ = "dingtalk_attendance_records"
    __table_args__ = (
        UniqueConstraint(
            "dingtalk_user_id", "work_date", "check_time", "check_type",
            name="uq_dt_attendance",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dingtalk_user_id = Column(String(128), index=True, nullable=True, comment="钉钉 userId")
    user_name = Column(String(128), nullable=True)
    department_id = Column(String(64), nullable=True)
    department_name = Column(String(128), nullable=True)
    work_date = Column(Date, index=True, nullable=True, comment="考勤归属日")
    check_time = Column(DateTime(timezone=True), nullable=True, comment="实际打卡时间")
    check_type = Column(String(32), nullable=True, comment="OnDuty 上班 / OffDuty 下班")
    time_result = Column(String(32), index=True, nullable=True, comment="Normal/Late/Early/NotSigned/...")
    location_result = Column(String(32), nullable=True, comment="Normal/Outside/NotSigned")
    source_type = Column(String(32), nullable=True)
    approve_id = Column(String(128), nullable=True)
    raw_payload = Column(JSONB, nullable=False, comment="钉钉原始打卡记录")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
