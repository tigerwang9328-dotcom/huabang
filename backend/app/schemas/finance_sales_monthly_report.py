"""
销售月报表 - Pydantic Schemas
============================
独立文件，不影响既有 finance.py schemas。
"""
from __future__ import annotations
from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, ConfigDict, Field

ScopeTypeLiteral    = Literal["all_stores", "partner", "custom_group", "single_store"]
FileTypeLiteral     = Literal["order", "settlement", "shipping_order", "fund", "freight",
                               "ad_cost", "product_cost"]
DetectStatusLiteral = Literal["uploaded", "detected", "need_confirm", "failed"]
FinalStatusLiteral  = Literal["pre_settlement_refund", "paid", "refunded", "pending_settlement"]


# ─── 店铺归属配置 ──────────────────────────────────────────
class StoreOwnershipCreate(BaseModel):
    store_name: str
    partner_name: Optional[str] = None
    group_name: Optional[str] = None
    effective_month: Optional[str] = None
    end_month: Optional[str] = None
    remark: Optional[str] = None


class StoreOwnershipUpdate(BaseModel):
    partner_name: Optional[str] = None
    group_name: Optional[str] = None
    effective_month: Optional[str] = None
    end_month: Optional[str] = None
    remark: Optional[str] = None
    is_active: Optional[bool] = None


class StoreOwnershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    store_name: str
    partner_name: Optional[str] = None
    group_name: Optional[str] = None
    is_active: bool
    effective_month: Optional[str] = None
    end_month: Optional[str] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None


class StoreOwnershipListResp(BaseModel):
    items: List[StoreOwnershipOut]
    total: int


# ─── 批次 ──────────────────────────────────────────────────
class BatchCreate(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")
    batch_name: str = ""
    scope_type: ScopeTypeLiteral = "all_stores"
    scope_name: Optional[str] = None
    remark: Optional[str] = None


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    month: str
    batch_name: str
    scope_type: str
    scope_name: Optional[str] = None
    status: str
    remark: Optional[str] = None
    expected_store_count: Optional[int] = 0
    uploaded_file_count: int = 0
    missing_required_count: int = 0
    abnormal_file_count: Optional[int] = 0
    store_count: Optional[int] = 0
    created_by: Optional[int] = None
    locked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class BatchListResp(BaseModel):
    items: List[BatchOut]
    total: int


# ─── 文件上传 ──────────────────────────────────────────────
class ImportFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    file_type: str
    store_name: str
    original_filename: Optional[str] = None
    file_path: Optional[str] = None
    row_count: int = 0
    error_count: int = 0
    error_message: Optional[str] = None
    detect_status: Optional[str] = None
    detect_message: Optional[str] = None
    detected_file_type: Optional[str] = None
    detected_store_name: Optional[str] = None
    is_active: Optional[bool] = True
    replaced_by_file_id: Optional[int] = None
    created_at: Optional[datetime] = None


class UploadResult(BaseModel):
    file: ImportFileOut
    message: str = "上传成功"


class BulkUploadFileResult(BaseModel):
    original_filename: str
    detect_status: str
    detect_message: Optional[str] = None
    detected_file_type: Optional[str] = None
    detected_store_name: Optional[str] = None


class BulkUploadResp(BaseModel):
    results: List[BulkUploadFileResult]
    detected_count: int
    need_confirm_count: int
    failed_count: int


class ConfirmFileBody(BaseModel):
    store_name: str
    file_type: str


# ─── 上传进度矩阵 ──────────────────────────────────────────
class MatrixFileStatus(BaseModel):
    file_type: str
    status: str
    file_id: Optional[int] = None
    filename: Optional[str] = None


class UploadMatrixRow(BaseModel):
    store_name: str
    partner_name: Optional[str] = None
    files: List[MatrixFileStatus]


class UploadMatrixResp(BaseModel):
    stores: List[UploadMatrixRow]
    file_types: List[str]


# ─── 生成月报 ──────────────────────────────────────────────
class GenerateBody(BaseModel):
    mode: Literal["loose", "strict"] = "loose"


class DeleteBatchBody(BaseModel):
    reason: Optional[str] = None


class ReportSummary(BaseModel):
    store_count: int = 0
    shipped_order_count: int = 0
    actual_sales_amount: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    pending_settlement_count: int = 0
    abnormal_count: int = 0


class GenerateResp(BaseModel):
    success: bool
    summary: ReportSummary
    message: str
    warnings: List[str] = []


class GenerateTaskStartResp(BaseModel):
    ok: bool
    message: str
    task_id: int
    status: str


class GenerateTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    status: str
    progress: int = 0
    current_step: Optional[str] = None
    message: Optional[str] = None
    error_message: Optional[str] = None
    result_json: Optional[dict] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class CalcLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    task_id: Optional[int] = None
    store_name: Optional[str] = None
    level: str
    stage: Optional[str] = None
    stage_name: Optional[str] = None
    field: Optional[str] = None
    field_name: Optional[str] = None
    message: Optional[str] = None
    detail_json: Optional[dict] = None
    row_count: Optional[int] = None
    success_count: Optional[int] = None
    failed_count: Optional[int] = None
    duration_ms: Optional[int] = None
    created_at: Optional[datetime] = None


class CalcLogListResp(BaseModel):
    items: List[CalcLogOut] = []
    total: int = 0


# ─── 月报结果 ──────────────────────────────────────────────
class ShopReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    month: str
    store_code: Optional[str] = None
    store_name: str
    shipped_order_count: int = 0
    shipped_amount: Decimal = Decimal("0")
    refund_order_count: int = 0
    after_ship_refund_amount: Decimal = Decimal("0")
    before_ship_refund_amount: Decimal = Decimal("0")
    after_settlement_refund_amount: Decimal = Decimal("0")
    actual_sales_amount: Decimal = Decimal("0")
    actual_sales_order_count: int = 0
    actual_sales_order_completed: int = 0
    paid_sales_amount: Decimal = Decimal("0")
    avg_order_amount: Decimal = Decimal("0")
    actual_product_cost: Decimal = Decimal("0")
    platform_service_fee: Decimal = Decimal("0")
    talent_commission: Decimal = Decimal("0")
    return_loss: Decimal = Decimal("0")
    freight_amount: Decimal = Decimal("0")
    package_fee: Decimal = Decimal("0")
    freight_insurance: Decimal = Decimal("0")
    compensation_amount: Decimal = Decimal("0")
    platform_other_fee: Decimal = Decimal("0")
    small_payment_amount: Decimal = Decimal("0")
    customer_service_fee: Decimal = Decimal("0")
    ad_cost: Decimal = Decimal("0")
    salary_fee: Decimal = Decimal("0")
    rent_utility_fee: Decimal = Decimal("0")
    other_monthly_expense: Decimal = Decimal("0")
    management_fee: Decimal = Decimal("0")
    tax_fee: Decimal = Decimal("0")
    total_fee: Decimal = Decimal("0")
    order_claim: Decimal = Decimal("0")
    goods_loss: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    deposit_recharge: Decimal = Decimal("0")
    rebate_amount: Decimal = Decimal("0")
    other_deduction: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    net_profit_rate: Decimal = Decimal("0")
    total_refund_rate: Decimal = Decimal("0")
    before_ship_refund_rate: Decimal = Decimal("0")
    after_ship_refund_rate: Decimal = Decimal("0")
    after_settlement_refund_rate: Decimal = Decimal("0")


class ReportResp(BaseModel):
    batch: BatchOut
    shops: List[ShopReportOut]
    summary: ReportSummary


class ShopReportManualUpdate(BaseModel):
    customer_service_fee: Decimal = Decimal("0")
    management_fee: Decimal = Decimal("0")
    tax_fee: Decimal = Decimal("0")
    order_claim: Decimal = Decimal("0")
    rebate_amount: Decimal = Decimal("0")
    deposit_recharge: Decimal = Decimal("0")
    other_deduction: Decimal = Decimal("0")


# ─── 订单明细 ──────────────────────────────────────────────
class OrderDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    store_name: Optional[str] = None
    main_order_no: Optional[str] = None
    sub_order_no: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    sku_name: Optional[str] = None
    quantity: int = 0
    ship_time: Optional[datetime] = None
    order_status: Optional[str] = None
    after_sale_status: Optional[str] = None
    order_pay_amount: Decimal = Decimal("0")
    platform_discount: Decimal = Decimal("0")
    talent_discount: Decimal = Decimal("0")
    receivable_amount: Decimal = Decimal("0")
    product_amount: Decimal = Decimal("0")
    order_freight: Decimal = Decimal("0")
    settlement_income: Decimal = Decimal("0")
    settlement_amount_total: Decimal = Decimal("0")
    settlement_difference: Decimal = Decimal("0")
    fund_refund_amount: Decimal = Decimal("0")
    platform_service_fee: Decimal = Decimal("0")
    talent_commission: Decimal = Decimal("0")
    refund_goods_amount: Decimal = Decimal("0")
    product_cost_price: Decimal = Decimal("0")
    product_cost_amount: Decimal = Decimal("0")
    express_company: Optional[str] = None
    express_no: Optional[str] = None
    matched_freight: Decimal = Decimal("0")
    final_status: Optional[str] = None
    final_status_reason: Optional[str] = None
    is_special_case: bool = False
    abnormal_reason: Optional[str] = None


class OrderDetailListResp(BaseModel):
    items: List[OrderDetailOut]
    total: int
    summary: Optional[dict] = None


# ─── 工作簿 Sheet 解析 ─────────────────────────────────────
class SheetResultItem(BaseModel):
    sheet_name: str
    detected_file_type: Optional[str] = None
    detect_status: str
    row_count: int = 0
    success_count: int = 0
    error_count: int = 0
    error_message: Optional[str] = None


class WorkbookUploadResult(BaseModel):
    import_file_id: int
    original_filename: str
    store_name: str
    sheet_results: List[SheetResultItem]
    total_sheets: int = 0
    detected_count: int = 0
    need_confirm_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    message: Optional[str] = None


class BulkWorkbookUploadResp(BaseModel):
    results: List[WorkbookUploadResult]
    total_workbooks: int = 0
    success_workbooks: int = 0
    need_confirm_workbooks: int = 0


class WorkbookSheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    import_file_id: int
    batch_id: int
    store_name: str
    sheet_name: str
    detected_file_type: Optional[str] = None
    detect_status: str
    row_count: int = 0
    success_count: int = 0
    error_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class ConfirmSheetBody(BaseModel):
    store_name: str
    file_type: str


# ─── 生成前校验 ────────────────────────────────────────────
class PrecheckStoreResult(BaseModel):
    store_name: str
    present_types: List[str] = []
    required_missing: List[str] = []
    optional_missing: List[str] = []
    can_generate: bool = True
    messages: List[str] = []


class PrecheckResp(BaseModel):
    ok: bool
    mode: str
    batch_id: int
    scope_type: Optional[str] = None
    scope_name: Optional[str] = None
    expected_store_count: int = 0
    uploaded_store_count: int = 0
    can_generate_count: int = 0
    stores: List[PrecheckStoreResult] = []
    blocking_errors: List[str] = []
    warnings: List[str] = []
