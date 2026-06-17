"""app schema: 业务应用表（任务/反馈/配置）"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric, Text, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class AppActionTask(Base):
    """AI任务（全闭环）"""
    __tablename__ = "app_action_task"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_no = Column(String(32), nullable=False, unique=True, comment="任务编号T2024XXXXX")
    title = Column(String(256), nullable=False, comment="任务标题")
    description = Column(Text, comment="问题描述")
    data_evidence = Column(JSON, comment="数据依据（结构化）")
    data_evidence_text = Column(Text, comment="数据依据（文字说明）")
    suggested_actions = Column(JSON, comment="建议动作列表")
    review_metrics = Column(JSON, comment="复查指标列表")
    feedback_requirement = Column(Text, comment="反馈要求说明")

    # 任务归属
    source_type = Column(String(32), comment="rule_engine/ai_diagnose/manual/exception")
    source_id = Column(BigInteger, comment="关联的异常/诊断ID")
    related_store_code = Column(String(32))
    related_product_code = Column(String(64))
    related_date = Column(Date)

    # 责任人
    assignee_id = Column(BigInteger, comment="sys_user.id")
    assignee_name = Column(String(64))
    assignee_role = Column(String(64))
    creator_id = Column(BigInteger, nullable=False)
    confirmed_by = Column(BigInteger, comment="确认派发的人")
    confirmed_at = Column(DateTime(timezone=True))

    # 时间节点
    due_date = Column(Date, comment="截止日期")
    completed_at = Column(DateTime(timezone=True))
    overdue_at = Column(DateTime(timezone=True), comment="标记逾期时间")

    # 状态（详见任务闭环规则）
    status = Column(String(32), nullable=False, default="draft",
                    comment="draft/pending/processing/feedback_submitted/review_passed/review_failed/overdue/closed/cancelled")
    priority = Column(Integer, default=5, comment="优先级1-10，10最高")
    risk_level = Column(String(16), comment="low/medium/high/critical")
    requires_human_confirm = Column(Boolean, default=True)

    # 钉钉
    dingtalk_task_url = Column(String(512))
    dingtalk_notified_at = Column(DateTime(timezone=True))
    dingtalk_reminder_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)


class AppTaskFeedback(Base):
    """任务反馈"""
    __tablename__ = "app_task_feedback"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, nullable=False, comment="app_action_task.id")
    feedback_by = Column(BigInteger, nullable=False)
    feedback_content = Column(Text, nullable=False, comment="反馈内容")
    attachment_urls = Column(JSON, comment="附件URL列表")
    action_taken = Column(Text, comment="已采取的行动")
    result_description = Column(Text, comment="执行结果说明")
    metrics_after = Column(JSON, comment="执行后的指标值")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AppTaskReview(Base):
    """任务复查"""
    __tablename__ = "app_task_review"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, nullable=False)
    reviewed_by = Column(BigInteger, nullable=False)
    review_result = Column(String(16), nullable=False, comment="passed/failed/pending")
    review_note = Column(Text)
    metrics_before = Column(JSON, comment="任务前指标")
    metrics_after = Column(JSON, comment="复查时指标")
    improvement_confirmed = Column(Boolean, comment="指标是否改善")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AppManualTarget(Base):
    """人工录入目标（月度销售目标等）"""
    __tablename__ = "app_manual_target"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    target_month = Column(String(7), nullable=False, comment="YYYY-MM")
    store_code = Column(String(32), nullable=False)
    sales_target = Column(Numeric(14, 2), comment="月度销售目标")
    gross_profit_target = Column(Numeric(14, 2), comment="月度毛利目标")
    member_count_target = Column(Integer, comment="月度新增会员目标")
    created_by = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AppWarningConfig(Base):
    """预警规则配置"""
    __tablename__ = "app_warning_config"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_code = Column(String(64), nullable=False, unique=True)
    rule_name = Column(String(128), nullable=False)
    module = Column(String(32), comment="sales/inventory/finance/member/task")
    threshold_config = Column(JSON, nullable=False, comment="阈值配置JSON")
    is_enabled = Column(Boolean, default=True)
    severity = Column(String(16), default="warning", comment="info/warning/critical")
    auto_create_task = Column(Boolean, default=False)
    description = Column(Text)
    created_by = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AppPushTemplate(Base):
    """钉钉推送模板"""
    __tablename__ = "app_push_template"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    template_code = Column(String(64), nullable=False, unique=True)
    template_name = Column(String(128), nullable=False)
    push_type = Column(String(32), comment="daily_report/task_reminder/warning/overdue")
    content_template = Column(Text, nullable=False, comment="消息模板（支持变量{{var}}）")
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AppAiPromptTemplate(Base):
    """AI提示词模板（可热更新）"""
    __tablename__ = "app_ai_prompt_template"
    __table_args__ = {"schema": "app"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    template_code = Column(String(64), nullable=False, unique=True)
    template_name = Column(String(128), nullable=False)
    module = Column(String(32), comment="daily_report/diagnosis/task/ask")
    prompt_text = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    model_requirement = Column(String(64), comment="推荐使用的模型")
    is_active = Column(Boolean, default=True)
    created_by = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
