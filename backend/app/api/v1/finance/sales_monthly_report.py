"""
销售月报表 - API 路由 (v3: 完整月报字段)
"""
from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote
from decimal import Decimal
from typing import List, Optional
import io
import os
import tempfile

from app.api.v1.deps import get_db, get_current_user
from app.schemas.finance_sales_monthly_report import (
    BatchCreate, BatchOut, BatchListResp,
    ImportFileOut, UploadResult,
    BulkUploadFileResult, BulkUploadResp, ConfirmFileBody,
    UploadMatrixResp,
    OrderDetailListResp,
    ReportResp, ReportSummary, ShopReportOut, ShopReportManualUpdate,
    GenerateBody, GenerateResp, DeleteBatchBody,
    GenerateTaskStartResp, GenerateTaskOut,
    CalcLogOut, CalcLogListResp,
    StoreOwnershipCreate, StoreOwnershipUpdate,
    StoreOwnershipOut, StoreOwnershipListResp,
    WorkbookUploadResult, BulkWorkbookUploadResp,
    WorkbookSheetOut, ConfirmSheetBody, SheetResultItem,
    PrecheckResp,
)
from app.services.finance.sales_monthly_report import service as svc

router = APIRouter(prefix="/finance/sales-monthly-report", tags=["销售月报表"])


def _safe(val):
    return val if val is not None else 0


# ─── 店铺归属配置 ──────────────────────────────────────────
@router.get("/store-ownerships", response_model=StoreOwnershipListResp)
async def list_store_ownerships(
    partner_name: Optional[str] = Query(None),
    group_name: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    month: Optional[str] = Query(None, description="YYYY-MM，按生效月份过滤"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    items, total = await svc.list_store_ownerships(
        db,
        partner_name=partner_name,
        group_name=group_name,
        is_active=is_active,
        month=month,
        limit=limit,
        offset=offset,
    )
    return StoreOwnershipListResp(items=items, total=total)


@router.post("/store-ownerships", response_model=StoreOwnershipOut)
async def create_store_ownership(
    body: StoreOwnershipCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await svc.create_store_ownership(db, **body.model_dump())


@router.put("/store-ownerships/{ownership_id}", response_model=StoreOwnershipOut)
async def update_store_ownership(
    ownership_id: int,
    body: StoreOwnershipUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await svc.update_store_ownership(
            db, ownership_id, **body.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/store-ownerships/{ownership_id}")
async def deactivate_store_ownership(
    ownership_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        await svc.deactivate_store_ownership(db, ownership_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "已停用"}


# ─── 批次 ──────────────────────────────────────────────────
@router.get("/batches", response_model=BatchListResp)
async def list_batches(
    month: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    scope_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_deleted: bool = Query(False, description="是否包含已删除批次"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    items, total = await svc.list_batches(
        db,
        month=month,
        scope_type=scope_type,
        scope_name=scope_name,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
    )
    return BatchListResp(items=items, total=total)


@router.post("/batches", response_model=BatchOut)
async def create_batch(
    body: BatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await svc.create_batch(
        db,
        month=body.month,
        batch_name=body.batch_name,
        scope_type=body.scope_type,
        scope_name=body.scope_name,
        remark=body.remark,
        user_id=current_user.id,
    )


@router.get("/batches/{batch_id}", response_model=BatchOut)
async def get_batch(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    b = await svc.get_batch(db, batch_id)
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    return b


# ─── 软删除批次 ────────────────────────────────────────────
@router.delete("/batches/{batch_id}")
async def delete_batch(
    batch_id: int,
    body: DeleteBatchBody = DeleteBatchBody(),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return await svc.delete_batch(
            db, batch_id,
            user_id=getattr(current_user, "id", None),
            reason=body.reason,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batches/{batch_id}/lock", response_model=BatchOut)
async def lock_batch(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await svc.lock_batch(db, batch_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── 单文件上传 ────────────────────────────────────────────
@router.post("/batches/{batch_id}/upload", response_model=UploadResult)
async def upload_file(
    batch_id: int,
    file_type: str = Query(..., description="文件类型"),
    store_name: str = Query(..., description="店铺名称"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if not file_type:
        raise HTTPException(status_code=400, detail="请选择文件类型")
    if not store_name:
        raise HTTPException(status_code=400, detail="请输入店铺名称")
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="请选择上传文件")
    content = await file.read()
    try:
        record = await svc.save_upload(
            db,
            batch_id=batch_id,
            file_type=file_type,
            store_name=store_name,
            original_filename=file.filename,
            file_bytes=content,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return UploadResult(file=record, message="上传成功")


# ─── 批量上传 ──────────────────────────────────────────────
@router.post("/batches/{batch_id}/bulk-upload", response_model=BulkUploadResp)
async def bulk_upload(
    batch_id: int,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    files_data = [(f.filename, await f.read()) for f in files]
    try:
        raw_results = await svc.bulk_upload_files(db, batch_id=batch_id, files_data=files_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    results = [BulkUploadFileResult(**r) for r in raw_results]
    return BulkUploadResp(
        results=results,
        detected_count=sum(1 for r in results if r.detect_status == "detected"),
        need_confirm_count=sum(1 for r in results if r.detect_status == "need_confirm"),
        failed_count=sum(1 for r in results if r.detect_status == "failed"),
    )


# ─── 待确认文件 ────────────────────────────────────────────
@router.get("/batches/{batch_id}/unconfirmed-files", response_model=List[ImportFileOut])
async def get_unconfirmed_files(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await svc.get_unconfirmed_files(db, batch_id)


@router.post(
    "/batches/{batch_id}/import-files/{file_id}/confirm",
    response_model=ImportFileOut,
)
async def confirm_file(
    batch_id: int,
    file_id: int,
    body: ConfirmFileBody,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await svc.confirm_file(
            db,
            file_id=file_id,
            store_name=body.store_name,
            file_type=body.file_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── 上传进度矩阵 ──────────────────────────────────────────
@router.get("/batches/{batch_id}/upload-matrix", response_model=UploadMatrixResp)
async def get_upload_matrix(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        result = await svc.get_upload_matrix(db, batch_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return UploadMatrixResp(**result)


# ─── 生成前校验 ──────────────────────────────────────────────
@router.get("/batches/{batch_id}/precheck", response_model=PrecheckResp)
async def precheck_batch(
    batch_id: int,
    mode: str = Query("loose", description="loose / strict"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        result = await svc.precheck_batch(db, batch_id, mode=mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PrecheckResp(**result)


# ─── 生成月报（异步任务）──────────────────────────────────────
@router.post("/batches/{batch_id}/generate", response_model=GenerateTaskStartResp)
async def start_generate(
    batch_id: int,
    background_tasks: BackgroundTasks,
    body: GenerateBody = GenerateBody(),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """启动异步生成任务，立即返回 task_id（不再同步等待数分钟）。"""
    try:
        res = await svc.start_generate_task(
            db, batch_id, mode=body.mode,
            user=str(getattr(current_user, "id", "")),
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 仅当新建任务时才真正后台执行；重复点击直接返回已有任务
    if res.get("started"):
        background_tasks.add_task(svc.run_generate_task, res["task_id"], batch_id, body.mode)

    return GenerateTaskStartResp(
        ok=res["ok"],
        message=res["message"],
        task_id=res["task_id"],
        status=res["status"],
    )


@router.get("/generate-tasks/{task_id}", response_model=GenerateTaskOut)
async def get_generate_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    t = await svc.get_generate_task(db, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="生成任务不存在，可能已被清理。")
    return t


@router.get("/batches/{batch_id}/generate-task/latest", response_model=Optional[GenerateTaskOut])
async def get_latest_generate_task(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await svc.get_latest_generate_task(db, batch_id)


# ─── 计算日志 ──────────────────────────────────────────────
@router.get("/batches/{batch_id}/calc-logs", response_model=CalcLogListResp)
async def get_calc_logs(
    batch_id: int,
    task_id: Optional[int] = Query(None),
    store_name: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    field: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    items, total = await svc.get_calc_logs(
        db, batch_id, task_id=task_id, store_name=store_name,
        level=level, stage=stage, keyword=keyword, field=field,
        page=page, page_size=page_size,
    )
    return CalcLogListResp(items=items, total=total)


# ─── 月报结果 ──────────────────────────────────────────────
@router.get("/batches/{batch_id}/reports", response_model=ReportResp)
async def get_reports(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    b = await svc.get_batch(db, batch_id)
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    shops = await svc.get_shop_reports(db, batch_id)

    _, _, status_counts = await svc.get_order_details(db, batch_id, limit=0)

    summary = ReportSummary(
        store_count=len(shops),
        shipped_order_count=sum(_safe(s.shipped_order_count) for s in shops),
        actual_sales_amount=sum((_safe(s.actual_sales_amount) for s in shops), Decimal("0")),
        net_profit=sum((_safe(s.net_profit) for s in shops), Decimal("0")),
        pending_settlement_count=status_counts.get("pending_settlement", 0),
        abnormal_count=status_counts.get("abnormal", 0),
    )
    return ReportResp(batch=b, shops=shops, summary=summary)


# ─── 订单明细 ──────────────────────────────────────────────
@router.put("/batches/{batch_id}/reports/{store_name}/manual", response_model=ShopReportOut)
async def update_report_manual(
    batch_id: int,
    store_name: str,
    body: ShopReportManualUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await svc.update_shop_report_manual(
            db, batch_id, store_name, body.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/batches/{batch_id}/order-details", response_model=OrderDetailListResp)
async def get_order_details(
    batch_id: int,
    store_name: Optional[str] = Query(None),
    final_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if not await svc.get_batch(db, batch_id):
        raise HTTPException(status_code=404, detail="批次不存在或已删除")
    items, total, summary = await svc.get_order_details(
        db,
        batch_id,
        final_status=final_status,
        store_name=store_name,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return OrderDetailListResp(items=items, total=total, summary=summary)


# ─── 导出 ──────────────────────────────────────────────────
def _shops_to_dicts(shops) -> list:
    """将 ORM ShopReport 列表转换为 dict 列表供 exporter 使用"""
    fields = [
        "store_code", "store_name", "shipped_order_count", "shipped_amount",
        "refund_order_count", "after_ship_refund_amount",
        "before_ship_refund_amount", "after_settlement_refund_amount",
        "actual_sales_amount", "actual_sales_order_count", "actual_sales_order_completed",
        "paid_sales_amount", "avg_order_amount",
        "actual_product_cost", "platform_service_fee", "talent_commission",
        "return_loss", "freight_amount", "package_fee", "freight_insurance",
        "compensation_amount", "platform_other_fee", "small_payment_amount", "customer_service_fee", "ad_cost",
        "salary_fee", "rent_utility_fee", "other_monthly_expense",
        "management_fee", "tax_fee", "total_fee",
        "order_claim", "goods_loss", "gross_profit",
        "deposit_recharge", "rebate_amount", "other_deduction",
        "net_profit", "net_profit_rate", "total_refund_rate",
        "before_ship_refund_rate", "after_ship_refund_rate", "after_settlement_refund_rate",
    ]
    return [{f: getattr(s, f, None) for f in fields} for s in shops]


def _orders_to_dicts(orders) -> list:
    fields = [
        "store_name", "main_order_no", "sub_order_no",
        "product_code", "product_name", "sku_name", "quantity",
        "ship_time", "order_status", "after_sale_status",
        "order_pay_amount", "platform_discount", "talent_discount",
        "receivable_amount", "product_amount", "order_freight",
        "settlement_income", "settlement_amount_total", "settlement_difference", "fund_refund_amount",
        "platform_service_fee", "talent_commission", "refund_goods_amount",
        "product_cost_price", "product_cost_amount",
        "express_company", "express_no", "matched_freight",
        "final_status", "final_status_reason",
        "is_special_case", "abnormal_reason",
    ]
    return [{f: getattr(o, f, None) for f in fields} for o in orders]


@router.get("/batches/{batch_id}/export-report")
async def export_report(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    b = await svc.get_batch(db, batch_id)
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    shops = await svc.get_shop_reports(db, batch_id)
    buf = svc.export_report_excel(b.month, _shops_to_dicts(shops), b.batch_name)
    filename = quote(f"{b.batch_name}-月报.xlsx")
    return StreamingResponse(
        io.BytesIO(buf),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/batches/{batch_id}/export-pending")
async def export_pending(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    b = await svc.get_batch(db, batch_id)
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    items, _, _ = await svc.get_order_details(
        db, batch_id, final_status="pending_settlement", limit=100000
    )
    buf = svc.export_pending_excel(b.month, _orders_to_dicts(items))
    filename = quote(f"{b.batch_name}-待结算.xlsx")
    return StreamingResponse(
        io.BytesIO(buf),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/batches/{batch_id}/export-abnormal")
async def export_abnormal(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    b = await svc.get_batch(db, batch_id)
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    items, _, _ = await svc.get_order_details(
        db, batch_id, final_status="abnormal", limit=100000
    )
    buf = svc.export_abnormal_excel(b.month, _orders_to_dicts(items))
    filename = quote(f"{b.batch_name}-异常.xlsx")
    return StreamingResponse(
        io.BytesIO(buf),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/batches/{batch_id}/export-normal")
async def export_normal(
    batch_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """导出正常订单明细，用于核对计算逻辑。大文件写入临时文件后返回，避免内存和 30 秒超时问题。"""
    b = await svc.get_batch(db, batch_id, include_deleted=True)
    if not b:
        raise HTTPException(status_code=404, detail="销售月报批次不存在")
    if getattr(b, "is_deleted", False):
        raise HTTPException(status_code=400, detail="该销售月报批次已删除，不能导出")

    items = await svc.get_orders_by_statuses(
        db, batch_id,
        ["pre_settlement_refund", "paid", "refunded", "pending_settlement"]
    )

    buf = svc.export_normal_excel(b.month, _orders_to_dicts(items))

    export_dir = os.path.join(tempfile.gettempdir(), "mumaren_sales_monthly_exports")
    os.makedirs(export_dir, exist_ok=True)
    safe_name = str(b.batch_name or batch_id).replace("/", "_").replace("\\", "_")
    file_path = os.path.join(export_dir, f"normal_orders_{batch_id}_{safe_name}.xlsx")

    with open(file_path, "wb") as f:
        f.write(buf)

    try:
        await svc.add_calc_log(
            batch_id, None, None, "info", "export_normal_orders", "导出正常订单",
            f"导出正常订单明细 {len(items)} 条。", row_count=len(items),
        )
    except Exception:
        pass

    filename = f"销售月报-正常订单明细-{b.batch_name}.xlsx"
    quoted = quote(filename)
    background_tasks.add_task(os.remove, file_path)

    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


# ─── 工作簿上传 ────────────────────────────────────────────
@router.post("/batches/{batch_id}/upload-workbook", response_model=WorkbookUploadResult)
async def upload_workbook(
    batch_id: int,
    store_name: str = Query(..., description="店铺名称"),
    file: UploadFile = File(...),
    scope_type: Optional[str] = Query(None),
    scope_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if not store_name:
        raise HTTPException(status_code=400, detail="请输入店铺名称")
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="请选择 Excel 工作簿")
    raw_bytes = await file.read()
    try:
        result = await svc.save_upload_workbook(
            db,
            batch_id=batch_id,
            store_name=store_name,
            original_filename=file.filename,
            file_bytes=raw_bytes,
            scope_type=scope_type,
            scope_name=scope_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"upload_workbook unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"工作簿处理失败：{e}")
    return WorkbookUploadResult(
        import_file_id=result["import_file_id"],
        original_filename=result["original_filename"],
        store_name=result["store_name"],
        sheet_results=[SheetResultItem(**r) for r in result["sheet_results"]],
        total_sheets=result["total_sheets"],
        detected_count=result["detected_count"],
        need_confirm_count=result["need_confirm_count"],
        failed_count=result["failed_count"],
        skipped_count=result.get("skipped_count", 0),
        message=result.get("status_reset_msg"),
    )


@router.post("/batches/{batch_id}/bulk-upload-workbooks", response_model=BulkWorkbookUploadResp)
async def bulk_upload_workbooks(
    batch_id: int,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    files_data = [(f.filename, await f.read()) for f in files]
    try:
        raw = await svc.bulk_upload_workbooks(db, batch_id=batch_id, files_data=files_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    results = []
    for r in raw:
        results.append(WorkbookUploadResult(
            import_file_id=r["import_file_id"],
            original_filename=r["original_filename"],
            store_name=r["store_name"],
            sheet_results=[SheetResultItem(**s) for s in r.get("sheet_results", [])],
            total_sheets=r.get("total_sheets", 0),
            detected_count=r.get("detected_count", 0),
            need_confirm_count=r.get("need_confirm_count", 0),
            failed_count=r.get("failed_count", 0),
            skipped_count=r.get("skipped_count", 0),
        ))
    return BulkWorkbookUploadResp(
        results=results,
        total_workbooks=len(results),
        success_workbooks=sum(1 for r in results if r.detected_count > 0),
        need_confirm_workbooks=sum(1 for r in results if r.need_confirm_count > 0),
    )


@router.get("/batches/{batch_id}/workbook-sheets", response_model=List[WorkbookSheetOut])
async def get_workbook_sheets(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await svc.get_workbook_sheets(db, batch_id)


@router.post("/import-sheets/{sheet_id}/confirm")
async def confirm_sheet(
    sheet_id: int,
    body: ConfirmSheetBody,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return await svc.confirm_sheet(db, sheet_id, body.store_name, body.file_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
