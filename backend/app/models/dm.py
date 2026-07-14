"""dm schema: 数据集市应用层"""
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, BigInteger, Numeric, Text, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class DmBossDailyReport(Base):
    """老板经营日报"""
    __tablename__ = "dm_boss_daily_report"
    __table_args__ = {"schema": "dm"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    report_date = Column(Date, nullable=False, unique=True)

    # 核心销售指标
    total_sales = Column(Numeric(14, 2), comment="总销售额")
    offline_sales = Column(Numeric(14, 2), comment="线下销售额")
    online_sales = Column(Numeric(14, 2), comment="线上销售额")
    online_ratio = Column(Numeric(6, 4))
    net_sales = Column(Numeric(14, 2))
    order_count = Column(Integer)
    item_count = Column(Integer)
    avg_order_value = Column(Numeric(12, 2), comment="客单价")
    items_per_order = Column(Numeric(6, 2), comment="连带率")
    avg_discount_rate = Column(Numeric(6, 4), comment="折扣率")
    actual_pay_amount = Column(Numeric(14, 2), comment="实收金额")
    return_amount = Column(Numeric(14, 2))
    return_rate = Column(Numeric(8, 4))

    # 对比（昨日/上周同日/上月同日）
    wow_sales_growth = Column(Numeric(8, 4), comment="周同比增长率")
    mom_sales_growth = Column(Numeric(8, 4), comment="月同比增长率")
    yoy_sales_growth = Column(Numeric(8, 4), comment="年同比增长率")

    # 财务（预估）
    gross_profit = Column(Numeric(14, 2))
    gross_margin = Column(Numeric(6, 4))
    total_expense = Column(Numeric(14, 2), comment="当日归集费用")
    operating_profit_estimate = Column(Numeric(14, 2), comment="预估经营利润")
    cash_balance = Column(Numeric(16, 2), comment="现金余额")
    cash_safety_days = Column(Integer, comment="现金安全天数")
    finance_data_type = Column(String(16), default="estimate")

    # 库存摘要
    total_inventory_amount = Column(Numeric(14, 2))
    inventory_total_qty = Column(Numeric(16, 4))
    inventory_age_unknown_qty = Column(Numeric(16, 4))
    inventory_age_unknown_amount = Column(Numeric(16, 2))
    age_90_plus_amount = Column(Numeric(14, 2), comment="90天以上库存")
    age_180_plus_amount = Column(Numeric(14, 2), comment="180天以上库存")

    # VIP资产
    vip_balance = Column(Numeric(16, 2))
    vip_negative_balance_count = Column(Integer, default=0)
    vip_negative_balance_amount = Column(Numeric(16, 2), default=0, comment="负余额绝对金额")
    vip_sales_amount = Column(Numeric(14, 2))
    vip_sales_ratio = Column(Numeric(8, 4))

    # 任务摘要
    pending_task_count = Column(Integer, default=0)
    overdue_task_count = Column(Integer, default=0)
    exception_count = Column(Integer, default=0)
    major_exception_count = Column(Integer, default=0)

    # AI生成内容
    ai_summary = Column(Text, comment="AI经营摘要")
    ai_today_focus = Column(JSON, comment="今日三件事列表")
    ai_risk_summary = Column(JSON, comment="风险摘要列表")
    ai_data_completeness = Column(String(32), comment="数据完整性评级")
    ai_model_used = Column(String(64))
    ai_generated_at = Column(DateTime(timezone=True))

    # 元数据
    is_cost_complete = Column(Boolean, default=False)
    is_finance_complete = Column(Boolean, default=False)
    data_quality_status = Column(String(16), default="normal",
                                 comment="normal/warning/critical/blocking")
    source_freshness = Column(JSON, comment="销售/库存/会员各自数据时间")
    metric_status = Column(JSON, comment="指标ready/estimated/pending_data/stale状态")
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DmStoreDiagnosis(Base):
    """门店诊断"""
    __tablename__ = "dm_store_diagnosis"
    __table_args__ = {"schema": "dm"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    diagnosis_date = Column(Date, nullable=False)
    store_code = Column(String(32), nullable=False)

    # 销售表现
    sales_amount = Column(Numeric(14, 2))
    sales_target = Column(Numeric(14, 2), comment="月目标（人工录入）")
    target_completion_rate = Column(Numeric(6, 4))
    sales_rank = Column(Integer, comment="当日门店排名")
    sales_trend_7d = Column(String(16), comment="up/down/flat")
    daily_sales_7d = Column(JSON, comment="近7天每日销售额")

    # 商品效率
    avg_order_value = Column(Numeric(12, 2))
    items_per_order = Column(Numeric(6, 2))
    avg_discount_rate = Column(Numeric(6, 4))
    member_ratio = Column(Numeric(6, 4))

    # 库存状况
    total_inventory_amount = Column(Numeric(14, 2))
    age_90_plus_amount = Column(Numeric(14, 2))
    sellable_days = Column(Integer, comment="可售天数")
    negative_sku_count = Column(Integer, default=0)

    # 诊断结论
    diagnosis_level = Column(String(16), comment="excellent/good/warning/critical")
    issues = Column(JSON, comment="问题列表")
    ai_diagnosis = Column(Text, comment="AI诊断文本")
    suggestions = Column(JSON, comment="建议列表")

    is_cost_complete = Column(Boolean, default=False)
    data_quality_status = Column(String(16), default="normal")
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class DmInventoryWarning(Base):
    """库存预警"""
    __tablename__ = "dm_inventory_warning"
    __table_args__ = {"schema": "dm"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    warning_date = Column(Date, nullable=False)
    store_code = Column(String(32))
    product_code = Column(String(64))
    sku_code = Column(String(64))
    warning_type = Column(String(32), nullable=False,
                          comment="negative/age_90/age_180/size_break/low_sellable_days/overstock")
    warning_level = Column(String(16), comment="info/warning/critical")
    current_quantity = Column(Integer)
    current_cost_amount = Column(Numeric(14, 2))
    age_days = Column(Integer)
    sellable_days = Column(Integer)
    description = Column(Text)
    rule_id = Column(String(16))
    thresholds = Column(JSON, default=dict)
    evidence = Column(JSON, default=dict)
    source_name = Column(String(64))
    is_converted_to_task = Column(Boolean, default=False)
    task_id = Column(BigInteger, comment="转化为的任务ID")
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class DmExceptionAudit(Base):
    """异常稽核"""
    __tablename__ = "dm_exception_audit"
    __table_args__ = {"schema": "dm"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    audit_date = Column(Date, nullable=False)
    exception_type = Column(String(32), nullable=False,
                            comment="discount_abnormal/return_abnormal/negative_inv/cost_missing/data_quality")
    severity = Column(String(16), comment="info/warning/critical")
    store_code = Column(String(32))
    product_code = Column(String(64))
    sku_code = Column(String(64))
    order_no = Column(String(64))
    description = Column(Text)
    data_snapshot = Column(JSON, comment="异常时的数据快照")
    is_reviewed = Column(Boolean, default=False)
    reviewed_by = Column(BigInteger)
    reviewed_at = Column(DateTime(timezone=True))
    review_note = Column(Text)
    is_converted_to_task = Column(Boolean, default=False)
    task_id = Column(BigInteger)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class DmMemberVisitList(Base):
    """会员回访名单"""
    __tablename__ = "dm_member_visit_list"
    __table_args__ = {"schema": "dm"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    visit_date = Column(Date, nullable=False, comment="推荐回访日期")
    member_no = Column(String(64), nullable=False)
    store_code = Column(String(32), comment="建议回访门店")
    guide_id = Column(String(32), comment="建议跟进导购")
    visit_reason = Column(String(32),
                          comment="birthday/sleeping/high_value/size_break/new_arrival")
    priority = Column(Integer, default=5, comment="优先级1-10")
    last_consume_date = Column(Date)
    sleep_days = Column(Integer, comment="沉睡天数")
    ai_suggestion = Column(Text, comment="AI跟进话术建议")
    visit_status = Column(String(16), default="pending",
                          comment="pending/visited/success/unreachable")
    visited_by = Column(String(32), comment="实际跟进导购ID")
    visited_at = Column(DateTime(timezone=True))
    visit_result = Column(Text, comment="跟进结果")
    is_converted = Column(Boolean, default=False, comment="是否成交")
    conversion_amount = Column(Numeric(12, 2))
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class DmReplenishmentAdvice(Base):
    """补货建议"""
    __tablename__ = "dm_replenishment_advice"
    __table_args__ = {"schema": "dm"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    advice_date = Column(Date, nullable=False)
    store_code = Column(String(32), nullable=False)
    product_code = Column(String(64), nullable=False)
    sku_code = Column(String(64))
    current_quantity = Column(Integer)
    daily_avg_sales_7d = Column(Numeric(8, 2), comment="近7天日均销量")
    sellable_days = Column(Integer, comment="可售天数")
    suggested_quantity = Column(Integer, comment="建议补货数量")
    urgency = Column(String(16), comment="urgent/normal/low")
    reason = Column(Text)
    status = Column(String(16), default="pending", comment="pending/confirmed/rejected")
    confirmed_by = Column(BigInteger)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class DmFinanceProfitDaily(Base):
    """财务利润日报（区分预估和核准）"""
    __tablename__ = "dm_finance_profit_daily"
    __table_args__ = {"schema": "dm"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False)
    store_code = Column(String(32), default="ALL")

    net_sales = Column(Numeric(14, 2))
    cost_of_goods = Column(Numeric(14, 2))
    gross_profit = Column(Numeric(14, 2))
    gross_margin = Column(Numeric(6, 4))
    total_expense = Column(Numeric(14, 2))
    operating_profit = Column(Numeric(14, 2), comment="经营利润=毛利-费用")
    operating_margin = Column(Numeric(6, 4))

    # 数据来源标记
    data_type = Column(String(16), nullable=False,
                       comment="estimate=预估 actual=财务核准")
    is_cost_complete = Column(Boolean, default=False)
    is_expense_complete = Column(Boolean, default=False)
    completeness_note = Column(String(256), comment="不完整原因说明")

    # 核准数据（如有）
    actual_profit = Column(Numeric(14, 2), comment="财务核准利润")
    estimate_vs_actual_diff = Column(Numeric(14, 2), comment="预估与实际差异")
    diff_rate = Column(Numeric(6, 4), comment="差异率")

    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
