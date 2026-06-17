"""log schema: 审计日志表"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric, Text, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class LogDataSync(Base):
    """数据同步日志"""
    __tablename__ = "log_data_sync"
    __table_args__ = {"schema": "log"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_no = Column(String(64), nullable=False, unique=True)
    source_system = Column(String(32), comment="baison/kingdee/manual")
    data_type = Column(String(64), comment="sales_order/inventory/member等")
    sync_type = Column(String(16), comment="excel/api/manual")
    file_name = Column(String(256), comment="Excel文件名")
    total_rows = Column(Integer, default=0)
    success_rows = Column(Integer, default=0)
    duplicate_rows = Column(Integer, default=0)
    error_rows = Column(Integer, default=0)
    status = Column(String(16), default="running", comment="running/success/partial/failed")
    error_detail = Column(JSON, comment="错误明细列表（前100条）")
    start_at = Column(DateTime(timezone=True), server_default=func.now())
    end_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    operator_id = Column(BigInteger, comment="操作人user_id")
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LogDataQuality(Base):
    """数据质量检查日志"""
    __tablename__ = "log_data_quality"
    __table_args__ = {"schema": "log"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    check_date = Column(Date, nullable=False)
    check_code = Column(String(64), nullable=False, comment="检查项编码")
    check_name = Column(String(128), nullable=False)
    module = Column(String(32))
    result_status = Column(String(16), nullable=False,
                           comment="normal/warning/critical/blocking")
    affected_count = Column(Integer, default=0, comment="受影响记录数")
    detail = Column(JSON, comment="检查详情")
    ai_blocked = Column(Boolean, default=False, comment="是否阻断AI诊断")
    checked_at = Column(DateTime(timezone=True), server_default=func.now())


class LogAiCall(Base):
    """AI调用日志（权限合规审计）"""
    __tablename__ = "log_ai_call"
    __table_args__ = {"schema": "log"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    user_role = Column(String(64))
    call_type = Column(String(32), comment="ask/diagnose/daily_report/task_generate")
    user_question = Column(Text)
    data_scope = Column(String(256), comment="使用的数据范围描述")
    prompt_version = Column(String(32), comment="使用的prompt模板版本")
    model_name = Column(String(64))
    ai_provider = Column(String(32))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    response_summary = Column(Text, comment="AI返回摘要（不存全文）")
    triggered_sensitive_fields = Column(JSON, comment="触发了哪些敏感字段权限检查")
    permission_blocked = Column(Boolean, default=False, comment="是否被权限拦截")
    permission_block_reason = Column(String(256))
    data_quality_blocked = Column(Boolean, default=False, comment="是否因数据质量阻断")
    latency_ms = Column(Integer, comment="API调用耗时ms")
    status = Column(String(16), comment="success/failed/blocked")
    error_message = Column(Text)
    called_at = Column(DateTime(timezone=True), server_default=func.now())


class LogDingtalkPush(Base):
    """钉钉推送日志"""
    __tablename__ = "log_dingtalk_push"
    __table_args__ = {"schema": "log"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    push_type = Column(String(32), nullable=False,
                       comment="daily_report/task_reminder/warning/overdue/test")
    target_user_id = Column(String(64), comment="钉钉用户ID")
    target_user_name = Column(String(64))
    template_code = Column(String(64))
    message_title = Column(String(256))
    message_content = Column(Text)
    status = Column(String(16), nullable=False, comment="success/failed/skipped")
    dingtalk_response = Column(Text, comment="钉钉API返回")
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    is_rate_limited = Column(Boolean, default=False, comment="是否因频率限制跳过")
    pushed_at = Column(DateTime(timezone=True), server_default=func.now())


class LogUserLogin(Base):
    """用户登录日志"""
    __tablename__ = "log_user_login"
    __table_args__ = {"schema": "log"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(64))
    login_ip = Column(String(64))
    user_agent = Column(String(512))
    status = Column(String(16), comment="success/failed/locked")
    failure_reason = Column(String(128))
    login_at = Column(DateTime(timezone=True), server_default=func.now())


class LogUserOperation(Base):
    """用户操作日志"""
    __tablename__ = "log_user_operation"
    __table_args__ = {"schema": "log"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(64))
    user_role = Column(String(64))
    module = Column(String(64))
    operation = Column(String(64), nullable=False, comment="create/update/delete/export/approve")
    resource_type = Column(String(64), comment="操作的资源类型")
    resource_id = Column(String(64), comment="操作的资源ID")
    description = Column(String(512))
    request_data = Column(JSON, comment="请求参数摘要")
    result_code = Column(Integer)
    ip_address = Column(String(64))
    operated_at = Column(DateTime(timezone=True), server_default=func.now())


class LogExport(Base):
    """导出日志（敏感数据导出合规）"""
    __tablename__ = "log_export"
    __table_args__ = {"schema": "log"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(64))
    user_role = Column(String(64))
    module = Column(String(64))
    export_type = Column(String(64), comment="导出的数据类型")
    filter_params = Column(JSON, comment="筛选条件")
    row_count = Column(Integer, comment="导出行数")
    has_sensitive_fields = Column(Boolean, default=False)
    file_name = Column(String(256))
    status = Column(String(16), comment="success/failed")
    exported_at = Column(DateTime(timezone=True), server_default=func.now())


class LogError(Base):
    """系统错误日志"""
    __tablename__ = "log_error"
    __table_args__ = {"schema": "log"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    error_type = Column(String(64))
    module = Column(String(64))
    error_message = Column(Text)
    stack_trace = Column(Text)
    request_path = Column(String(512))
    request_method = Column(String(16))
    user_id = Column(BigInteger)
    severity = Column(String(16), comment="warning/error/critical")
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
