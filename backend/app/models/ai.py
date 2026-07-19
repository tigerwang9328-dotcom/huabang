"""ai schema: AI诊断结果表"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric, Text, JSON, UniqueConstraint, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class AiDiagnosisResult(Base):
    """AI诊断结果（结构化输出）"""
    __tablename__ = "ai_diagnosis_result"
    __table_args__ = {"schema": "ai"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    diagnosis_date = Column(Date, nullable=False)
    diagnosis_type = Column(String(32), nullable=False,
                            comment="store/product/inventory/finance/member/task")
    target_code = Column(String(64), comment="门店码/商品码等")

    # AI结构化输出（固定格式）
    problem = Column(Text, comment="问题是什么")
    data_evidence = Column(JSON, comment="数据依据（结构化）")
    possible_causes = Column(JSON, comment="可能原因列表")
    suggested_actions = Column(JSON, comment="建议动作列表")
    suggested_assignee = Column(String(64), comment="建议责任人角色")
    suggested_due_days = Column(Integer, comment="建议截止天数")
    feedback_requirement = Column(Text, comment="需要反馈什么")
    review_metrics = Column(JSON, comment="复查指标列表")
    risk_level = Column(String(16), comment="low/medium/high/critical")
    requires_human_confirm = Column(Boolean, default=True)

    # 元数据
    rule_triggered = Column(String(64), comment="触发的规则编码")
    data_quality_status = Column(String(16), comment="诊断时的数据质量状态")
    is_data_incomplete = Column(Boolean, default=False, comment="数据不完整时必须标记")
    data_incomplete_reason = Column(Text)

    # 模型信息
    model_used = Column(String(64))
    ai_provider = Column(String(32))
    prompt_version = Column(String(32))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)

    # 任务关联
    is_converted_to_task = Column(Boolean, default=False)
    task_id = Column(BigInteger)

    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AiRuleMatch(Base):
    """规则引擎触发记录"""
    __tablename__ = "ai_rule_match"
    __table_args__ = {"schema": "ai"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    match_date = Column(Date, nullable=False)
    rule_code = Column(String(64), nullable=False)
    rule_name = Column(String(128))
    severity = Column(String(16))
    target_type = Column(String(32), comment="store/product/sku/member/finance")
    target_code = Column(String(64))
    metric_name = Column(String(64), comment="触发规则的指标名")
    metric_value = Column(Numeric(16, 4), comment="触发时的指标值")
    threshold_value = Column(Numeric(16, 4), comment="规则阈值")
    description = Column(Text)
    data_snapshot = Column(JSON)
    is_sent_to_ai = Column(Boolean, default=False)
    ai_diagnosis_id = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AiBusinessAdviceSnapshot(Base):
    """公司/门店模块级 AI 经营建议缓存；事实值只保存在 safe_context 中。"""
    __tablename__ = "ai_business_advice_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "stat_date", "module", "scope_type", "target_code",
            name="uq_ai_business_advice_snapshot_unit",
        ),
        {"schema": "ai"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    module = Column(String(32), nullable=False)
    scope_type = Column(String(16), nullable=False)
    target_code = Column(String(64), nullable=False, default="company")
    safe_context = Column(JSONB, nullable=False, default=dict)
    input_hash = Column(String(64), nullable=False)
    conclusion = Column(JSONB, nullable=False, default=dict)
    mode = Column(String(16), nullable=False, default="template")
    status = Column(String(16), nullable=False, default="success")
    data_status = Column(String(16), nullable=False, default="pending_data")
    provider = Column(String(32))
    model_name = Column(String(128))
    prompt_version = Column(String(32), nullable=False, default="business-advice-v5")
    schema_version = Column(String(32), nullable=False, default="business-advice-json-v1")
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    latency_ms = Column(Integer)
    error_code = Column(String(64))
    fallback_reason = Column(Text)
    last_attempt_status = Column(String(16))
    last_attempt_error_code = Column(String(64))
    last_attempt_at = Column(DateTime(timezone=True))
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AiAssistantConversation(Base):
    """老板 AI 助手会话；按用户隔离，删除先归档。"""
    __tablename__ = "ai_assistant_conversation"
    __table_args__ = (
        Index("ix_ai_assistant_conversation_user_last", "user_id", "is_archived", "last_message_at"),
        {"schema": "ai"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    title = Column(String(128), nullable=False, default="新对话")
    route = Column(String(256))
    stat_date = Column(Date)
    store_code = Column(String(64))
    is_archived = Column(Boolean, nullable=False, default=False)
    last_message_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    archived_at = Column(DateTime(timezone=True))


class AiAssistantMessage(Base):
    """老板 AI 助手消息；助手消息保存结构化回答、来源和页面上下文。"""
    __tablename__ = "ai_assistant_message"
    __table_args__ = (
        Index("ix_ai_assistant_message_conversation_created", "conversation_id", "created_at"),
        {"schema": "ai"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        BigInteger,
        ForeignKey("ai.ai_assistant_conversation.id"),
        nullable=False,
    )
    user_id = Column(BigInteger, nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    answer_payload = Column(JSONB, nullable=False, default=dict)
    sources = Column(JSONB, nullable=False, default=list)
    context = Column(JSONB, nullable=False, default=dict)
    used_web = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
