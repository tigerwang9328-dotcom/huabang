"""销售月报 ORM 模型"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Text,
    DateTime, BigInteger, ForeignKey, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TEXT, JSONB
from sqlalchemy import text
from app.core.database import Base
from app.models.finance._base import TimestampMixin


class FinSalesMonthlyStoreOwnership(Base):
    """店铺归属配置（合伙人/分组维度）"""
    __tablename__ = "fin_sales_monthly_store_ownerships"

    id              = Column(Integer, primary_key=True)
    store_name      = Column(String(128), nullable=False)
    partner_name    = Column(String(64))
    group_name      = Column(String(64))
    is_active       = Column(Boolean, server_default=text("true"), nullable=False)
    effective_month = Column(String(7))
    end_month       = Column(String(7))
    remark          = Column(Text)
    created_by      = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    created_at      = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at      = Column(DateTime, server_default=text("now()"), nullable=False)


class FinSalesMonthlyReportBatch(Base):
    """销售月报批次"""
    __tablename__ = "fin_sales_monthly_report_batches"

    id                   = Column(Integer, primary_key=True)
    month                = Column(String(7), nullable=False)
    batch_name           = Column(String(256), nullable=False)
    scope_type           = Column(String(32), server_default=text("'all_stores'::character varying"), nullable=False)
    scope_name           = Column(String(128))
    status               = Column(String(32), server_default=text("'draft'::character varying"), nullable=False)
    remark               = Column(Text)
    expected_store_count = Column(Integer, server_default=text("0"))
    uploaded_file_count  = Column(Integer, server_default=text("0"))
    missing_required_count = Column(Integer, server_default=text("0"))
    abnormal_file_count  = Column(Integer, server_default=text("0"))
    store_count          = Column(Integer, server_default=text("0"))
    created_by           = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    locked_at            = Column(DateTime)
    # 软删除（财务数据不物理删除，仅从列表隐藏，便于追溯）
    is_deleted           = Column(Boolean, server_default=text("false"), nullable=False)
    deleted_at           = Column(DateTime)
    deleted_by           = Column(Integer, ForeignKey("sys_users.id", ondelete="SET NULL"))
    delete_reason        = Column(Text)
    created_at           = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at           = Column(DateTime, server_default=text("now()"), nullable=False)


class FinSalesMonthlyImportFile(Base):
    """销售月报上传文件清单"""
    __tablename__ = "fin_sales_monthly_import_files"

    id                  = Column(Integer, primary_key=True)
    batch_id            = Column(Integer, ForeignKey("fin_sales_monthly_report_batches.id", ondelete="CASCADE"), nullable=False)
    file_type           = Column(String(32), nullable=False)
    store_name          = Column(String(128), nullable=False)
    original_filename   = Column(String(512))
    file_path           = Column(String(1024))
    row_count           = Column(Integer, server_default=text("0"))
    error_count         = Column(Integer, server_default=text("0"))
    error_message       = Column(Text)
    # v2 新增字段
    detected_store_name = Column(String(128))
    detected_file_type  = Column(String(32))
    detect_status       = Column(String(32), server_default=text("'uploaded'::character varying"))
    detect_message      = Column(Text)
    is_active           = Column(Boolean, server_default=text("true"))
    replaced_by_file_id = Column(Integer, ForeignKey("fin_sales_monthly_import_files.id", ondelete="SET NULL"))
    source_sheet_name   = Column(String(256))
    scope_type          = Column(String(32))
    scope_name          = Column(String(128))
    created_at          = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at          = Column(DateTime, server_default=text("now()"), nullable=False)


class FinSalesMonthlyShopReport(Base):
    """销售月报店铺级聚合结果"""
    __tablename__ = "fin_sales_monthly_shop_reports"
    __table_args__ = (
        UniqueConstraint("batch_id", "store_name", name="uq_fin_smr_reports_batch_store"),
    )

    id                       = Column(Integer, primary_key=True)
    batch_id                 = Column(Integer, ForeignKey("fin_sales_monthly_report_batches.id", ondelete="CASCADE"), nullable=False)
    month                    = Column(String(7), nullable=False)
    store_name               = Column(String(128), nullable=False)
    # 基本统计
    shipped_order_count      = Column(Integer, server_default=text("0"))
    shipped_amount           = Column(Numeric(18, 2), server_default=text("0"))
    refund_order_count       = Column(Integer, server_default=text("0"))
    after_ship_refund_amount = Column(Numeric(18, 2), server_default=text("0"))
    before_ship_refund_amount = Column(Numeric(18, 2), server_default=text("0"))
    after_settlement_refund_amount = Column(Numeric(18, 2), server_default=text("0"))
    actual_sales_amount      = Column(Numeric(18, 2), server_default=text("0"))
    actual_sales_order_count = Column(Integer, server_default=text("0"))
    actual_sales_order_completed = Column(Integer, server_default=text("0"))
    paid_sales_amount        = Column(Numeric(18, 2), server_default=text("0"))
    avg_order_amount         = Column(Numeric(18, 2), server_default=text("0"))
    # 成本费用
    actual_product_cost      = Column(Numeric(18, 2), server_default=text("0"))
    platform_service_fee     = Column(Numeric(18, 2), server_default=text("0"))
    talent_commission        = Column(Numeric(18, 2), server_default=text("0"))
    return_loss              = Column(Numeric(18, 2), server_default=text("0"))
    freight_amount           = Column(Numeric(18, 2), server_default=text("0"))
    package_fee              = Column(Numeric(18, 2), server_default=text("0"))
    freight_insurance        = Column(Numeric(18, 2), server_default=text("0"))
    compensation_amount      = Column(Numeric(18, 2), server_default=text("0"))
    platform_other_fee       = Column(Numeric(18, 2), server_default=text("0"))   # 新版：平台其他费用
    customer_service_fee     = Column(Numeric(18, 2), server_default=text("0"))
    ad_cost                  = Column(Numeric(18, 2), server_default=text("0"))
    management_fee           = Column(Numeric(18, 2), server_default=text("0"))
    tax_fee                  = Column(Numeric(18, 2), server_default=text("0"))
    total_fee                = Column(Numeric(18, 2), server_default=text("0"))
    # 利润
    order_claim              = Column(Numeric(18, 2), server_default=text("0"))
    goods_loss               = Column(Numeric(18, 2), server_default=text("0"))
    gross_profit             = Column(Numeric(18, 2), server_default=text("0"))
    deposit_recharge         = Column(Numeric(18, 2), server_default=text("0"))
    rebate_amount            = Column(Numeric(18, 2), server_default=text("0"))
    other_deduction          = Column(Numeric(18, 2), server_default=text("0"))
    net_profit               = Column(Numeric(18, 2), server_default=text("0"))
    net_profit_rate          = Column(Numeric(8, 4), server_default=text("0"))
    total_refund_rate        = Column(Numeric(8, 4), server_default=text("0"))
    before_ship_refund_rate  = Column(Numeric(8, 4), server_default=text("0"))
    after_ship_refund_rate   = Column(Numeric(8, 4), server_default=text("0"))
    after_settlement_refund_rate = Column(Numeric(8, 4), server_default=text("0"))
    # v3 新字段
    store_code               = Column(String(64))
    small_payment_amount     = Column(Numeric(18, 2), server_default=text("0"), nullable=False)
    salary_fee               = Column(Numeric(18, 2), server_default=text("0"), nullable=False)
    rent_utility_fee         = Column(Numeric(18, 2), server_default=text("0"), nullable=False)
    other_monthly_expense    = Column(Numeric(18, 2), server_default=text("0"), nullable=False)
    created_at               = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at               = Column(DateTime, server_default=text("now()"), nullable=False)


class FinSalesMonthlyOrderDetail(Base):
    """销售月报订单明细"""
    __tablename__ = "fin_sales_monthly_order_details"

    id                   = Column(Integer, primary_key=True)
    batch_id             = Column(Integer, ForeignKey("fin_sales_monthly_report_batches.id", ondelete="CASCADE"), nullable=False)
    month                = Column(String(7), nullable=False)
    store_name           = Column(String(128), nullable=False)
    main_order_no        = Column(String(64))
    sub_order_no         = Column(String(64))
    product_code         = Column(String(64))
    product_name         = Column(String(512))
    sku_name             = Column(String(256))
    quantity             = Column(Integer, server_default=text("0"))
    ship_time            = Column(DateTime)
    order_status         = Column(String(64))
    after_sale_status    = Column(String(256))
    order_pay_amount     = Column(Numeric(18, 2), server_default=text("0"))
    platform_discount    = Column(Numeric(18, 2), server_default=text("0"))
    talent_discount      = Column(Numeric(18, 2), server_default=text("0"))
    receivable_amount    = Column(Numeric(18, 2), server_default=text("0"))
    product_amount       = Column(Numeric(18, 2), server_default=text("0"))
    order_freight        = Column(Numeric(18, 2), server_default=text("0"))
    settlement_income    = Column(Numeric(18, 2), server_default=text("0"))
    settlement_amount_total = Column(Numeric(18, 2), server_default=text("0"))
    settlement_difference = Column(Numeric(18, 2), server_default=text("0"))
    fund_refund_amount   = Column(Numeric(18, 2), server_default=text("0"))
    platform_service_fee = Column(Numeric(18, 2), server_default=text("0"))
    talent_commission    = Column(Numeric(18, 2), server_default=text("0"))
    refund_goods_amount  = Column(Numeric(18, 2), server_default=text("0"))
    product_cost_price   = Column(Numeric(18, 4), server_default=text("0"))
    product_cost_amount  = Column(Numeric(18, 2), server_default=text("0"))
    express_company      = Column(String(64))
    express_no           = Column(String(128))
    matched_freight      = Column(Numeric(18, 2), server_default=text("0"))
    final_status         = Column(String(32), server_default=text("'pending_settlement'::character varying"))
    final_status_reason  = Column(Text)
    is_special_case      = Column(Boolean, server_default=text("false"))
    abnormal_reason      = Column(Text)
    created_at           = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at           = Column(DateTime, server_default=text("now()"), nullable=False)


class FinSalesMonthlyImportSheet(Base):
    """工作簿 Sheet 解析记录"""
    __tablename__ = "fin_sales_monthly_import_sheets"

    id                  = Column(Integer, primary_key=True)
    import_file_id      = Column(Integer, ForeignKey("fin_sales_monthly_import_files.id", ondelete="CASCADE"), nullable=False)
    batch_id            = Column(Integer, ForeignKey("fin_sales_monthly_report_batches.id", ondelete="CASCADE"), nullable=False)
    store_name          = Column(String(128), nullable=False)
    sheet_name          = Column(String(256), nullable=False)
    detected_file_type  = Column(String(32))
    detect_status       = Column(String(32), server_default=text("'need_confirm'::character varying"), nullable=False)
    row_count           = Column(Integer, server_default=text("0"))
    success_count       = Column(Integer, server_default=text("0"))
    error_count         = Column(Integer, server_default=text("0"))
    error_message       = Column(Text)
    created_at          = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at          = Column(DateTime, server_default=text("now()"), nullable=False)


class FinSalesMonthlyGenerateTask(Base):
    """销售月报异步生成任务（pending/running/success/failed/cancelled）"""
    __tablename__ = "fin_sales_monthly_generate_tasks"

    id            = Column(Integer, primary_key=True)
    batch_id      = Column(Integer, ForeignKey("fin_sales_monthly_report_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    status        = Column(String(16), server_default=text("'pending'::character varying"), nullable=False)
    progress      = Column(Integer, server_default=text("0"), nullable=False)
    current_step  = Column(String(64))
    message       = Column(Text)
    error_message = Column(Text)
    result_json   = Column(JSONB)
    created_by    = Column(String(64))
    started_at    = Column(DateTime)
    finished_at   = Column(DateTime)
    created_at    = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at    = Column(DateTime, server_default=text("now()"), nullable=False)


class FinSalesMonthlyCalcLog(Base):
    """销售月报计算日志（业务计算过程，非程序错误日志；仅阶段汇总，不逐行写）"""
    __tablename__ = "fin_sales_monthly_calc_logs"

    id            = Column(BigInteger, primary_key=True)
    batch_id      = Column(Integer, ForeignKey("fin_sales_monthly_report_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id       = Column(Integer, index=True)
    store_name    = Column(String(128), index=True)
    level         = Column(String(16), server_default=text("'info'::character varying"), nullable=False, index=True)
    stage         = Column(String(48), index=True)
    stage_name    = Column(String(64))
    field         = Column(String(48), index=True)
    field_name    = Column(String(64))
    message       = Column(Text)
    detail_json   = Column(JSONB)
    row_count     = Column(Integer)
    success_count = Column(Integer)
    failed_count  = Column(Integer)
    duration_ms   = Column(Integer)
    created_at    = Column(DateTime, server_default=text("now()"), nullable=False, index=True)
