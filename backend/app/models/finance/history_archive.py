"""企业历史数据资产中心模型。

``FinHistoryArchiveFile`` 保留旧版表映射，只用于数据迁移和回退；新业务只使用
``DataArchiveCategory``、``DataArchiveFile`` 和 ``DataArchiveLog`` 三张独立表。
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinHistoryArchiveFile(Base):
    """旧版存档表映射。禁止在新业务中写入。"""

    __tablename__ = "fin_history_archive_files"
    __table_args__ = (
        Index("ix_fin_history_archive_month_status", "data_month", "status"),
        Index("ix_fin_history_archive_purge", "status", "purge_after"),
    )

    id = Column(Integer, primary_key=True)
    data_name = Column(String(200), nullable=False)
    data_month = Column(String(7), nullable=False, index=True)
    tags = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    description = Column(Text)
    original_filename = Column(String(512), nullable=False)
    file_extension = Column(String(16), nullable=False)
    mime_type = Column(String(128), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    file_sha256 = Column(String(64), nullable=False, index=True)
    file_path = Column(String(1024), nullable=False)
    status = Column(String(16), nullable=False, index=True)
    uploaded_by = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    voided_at = Column(DateTime)
    voided_by = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    void_reason = Column(Text)
    purge_after = Column(DateTime)
    purged_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime, nullable=False, server_default=text("now()"))


class DataArchiveCategory(Base):
    """可无限扩展的分类树；当前页面只操作三级。"""

    __tablename__ = "data_archive_categories"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_data_archive_category_parent_name"),
        CheckConstraint("level >= 1", name="ck_data_archive_category_level"),
        Index("ix_data_archive_category_parent_status", "parent_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    parent_id = Column(
        Integer,
        ForeignKey("data_archive_categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    name = Column(String(128), nullable=False)
    level = Column(Integer, nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, server_default=text("0"))
    is_fixed = Column(Boolean, nullable=False, server_default=text("false"))
    status = Column(String(16), nullable=False, server_default=text("'ACTIVE'"), index=True)
    created_by = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    updated_by = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime, nullable=False, server_default=text("now()"))


class DataArchiveFile(Base):
    """存档文件元数据；文件内容保存在本机或 MinIO。"""

    __tablename__ = "data_archive_files"
    __table_args__ = (
        UniqueConstraint("legacy_file_id", name="uq_data_archive_files_legacy_file"),
        Index("ix_data_archive_files_period_status", "data_year", "data_month", "status"),
        Index("ix_data_archive_files_category_status", "category_root_id", "category_id", "status"),
        Index("ix_data_archive_files_dimensions", "project_name", "company_name", "store_id"),
        Index("ix_data_archive_files_created", "created_at"),
    )

    id = Column(BigInteger, primary_key=True)
    data_name = Column(String(200), nullable=False)
    original_filename = Column(String(512), nullable=False)
    storage_provider = Column(String(16), nullable=False, server_default=text("'LOCAL'"))
    storage_key = Column(String(1024), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    file_extension = Column(String(16), nullable=False)
    mime_type = Column(String(128), nullable=False)
    md5 = Column(String(32), nullable=True, index=True)
    sha256 = Column(String(64), nullable=False, index=True)

    category_id = Column(
        Integer,
        ForeignKey("data_archive_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    category_root_id = Column(
        Integer,
        ForeignKey("data_archive_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    category_path = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    project_name = Column(String(128))
    company_name = Column(String(255))
    store_id = Column(Integer, ForeignKey("biz_stores.id", ondelete="SET NULL"), index=True)
    store_name_snapshot = Column(String(128))

    data_year = Column(Integer, nullable=False, index=True)
    data_month = Column(Integer, nullable=False, index=True)
    data_start_date = Column(Date)
    data_end_date = Column(Date)
    data_type = Column(String(32), nullable=False, index=True)
    description = Column(Text)

    status = Column(String(16), nullable=False, server_default=text("'NORMAL'"), index=True)
    uploaded_by = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"), index=True)
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime, nullable=False, server_default=text("now()"))
    deleted_at = Column(DateTime)
    deleted_by = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    delete_reason = Column(Text)

    legacy_file_id = Column(Integer)
    legacy_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class DataArchiveLog(Base):
    """模块独立审计日志，记录文件生命周期及下载环境。"""

    __tablename__ = "data_archive_logs"
    __table_args__ = (
        Index("ix_data_archive_logs_file_time", "file_id", "operation_time"),
        Index("ix_data_archive_logs_type_time", "operation_type", "operation_time"),
    )

    id = Column(BigInteger, primary_key=True)
    file_id = Column(
        BigInteger,
        ForeignKey("data_archive_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_type = Column(String(16), nullable=False, index=True)
    operation_user_id = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    operation_user_name = Column(String(128))
    operation_time = Column(DateTime, nullable=False, server_default=text("now()"))
    ip_address = Column(String(64))
    user_agent = Column(String(512))
    change_detail = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
