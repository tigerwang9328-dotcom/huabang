"""ai schema: AI诊断结果表"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric, Text, JSON
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
