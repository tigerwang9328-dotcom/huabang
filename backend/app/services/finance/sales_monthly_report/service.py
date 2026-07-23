"""
销售月报 - 业务逻辑层
=====================
封装批次 CRUD、文件上传、月报生成等核心操作。
"""
from __future__ import annotations
import logging
import re
import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select, delete, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance.sales_monthly_report import (
    FinSalesMonthlyStoreOwnership,
    FinSalesMonthlyReportBatch,
    FinSalesMonthlyImportFile,
    FinSalesMonthlyImportSheet,
    FinSalesMonthlyShopReport,
    FinSalesMonthlyOrderDetail,
    FinSalesMonthlyGenerateTask,
    FinSalesMonthlyCalcLog,
)
from app.core.database import AsyncSessionLocal
from app.services.finance.sales_monthly_report import (
    calculator,
    settings as svc_settings,
)
from app.services.finance.sales_monthly_report import importers
from app.services.finance.sales_monthly_report.exporter import (
    export_report_excel as _export_report_excel,
    export_pending_excel as _export_pending_excel,
    export_abnormal_excel as _export_abnormal_excel,
    export_normal_excel as _export_normal_excel,
)
from app.services.finance.sales_monthly_report.status_rules import (
    determine_status, STATUS_LABELS, RULES_VERSION as determine_status_version,
)

logger = logging.getLogger(__name__)

# 本进程加载该模块的时间。生成任务依附于当前 Web 进程；若任务创建时间早于
# 本时间，说明它来自已退出的旧进程，应在查询/重试时回收为失败。
_PROCESS_STARTED_AT = datetime.utcnow()

UPLOAD_ROOT = Path("/srv/mumaren_ai_platform/data/uploads/finance/sales_monthly_report")
BATCH_SIZE  = 500

# 新版（销售月报规则优化版）：7 类表，停用 售后单 / 独立运费险表
REQUIRED_FILE_TYPES = ["order", "settlement", "shipping_order", "product_cost"]
OPTIONAL_FILE_TYPES = ["fund", "freight", "ad_cost"]
ALL_FILE_TYPES      = REQUIRED_FILE_TYPES + OPTIONAL_FILE_TYPES
DEPRECATED_FILE_TYPES = ["after_sale", "freight_insurance"]

# file_type → 中文名（用于结构化错误展示）
FILE_TYPE_CN = {
    "order":             "店铺订单",
    "settlement":        "结算账单",
    "shipping_order":    "发货订单",
    "product_cost":      "商品成本表",
    "fund":              "资金账单",
    "freight":           "运费",
    "ad_cost":           "广告费",
    "after_sale":        "售后单(已停用)",
    "freight_insurance": "运费险表(已停用)",
    "workbook":          "工作簿",
}


def _validate_parse(file_type: str, file_path: str, filename: str | None,
                    month: str, store_name: str) -> tuple[bool, str | None]:
    """
    同步：用对应解析器试解析单个文件，仅验证能否解析，返回 (ok, 中文错误)。
    供 precheck 在生成前提前暴露 CSV/格式/表头问题。
    """
    try:
        wb = importers.load_table_workbook(file_path, filename)
    except Exception as e:
        return False, importers.humanize_parse_error(str(e))
    try:
        if file_type == "order":
            importers.parse_order_file(wb, month, store_name)
        elif file_type == "settlement":
            importers.parse_settlement_file(wb, month)
        elif file_type == "product_cost":
            importers.parse_product_cost_file(wb)
        elif file_type == "shipping_order":
            importers.parse_shipping_order_file(wb, month)
        elif file_type == "fund":
            importers.parse_fund_aggregates(wb, month)
        elif file_type == "freight":
            importers.parse_freight_by_waybill(wb)
        elif file_type == "ad_cost":
            importers.parse_amount_file(wb, "ad_cost")
        return True, None
    except Exception as e:
        logger.warning(f"[precheck] {store_name} {file_type} 解析失败: {e}", exc_info=True)
        return False, importers.humanize_parse_error(str(e))
    finally:
        try:
            wb.close()
        except Exception:
            pass

# (文件类型, 关键词列表) — 新版 7 类，按优先顺序匹配（发货订单必须早于普通订单）
FILE_TYPE_DETECTION_RULES: list[tuple[str, list[str]]] = [
    ("product_cost",      ["成本", "商品成本"]),
    ("fund",              ["资金账单", "资金流水", "资金明细", "资金"]),
    ("settlement",        ["结算账单", "结算明细", "账单", "结算"]),
    ("freight",           ["运费", "快递费", "物流费"]),
    ("ad_cost",           ["广告", "推广", "投流", "千川"]),
    ("shipping_order",    ["发货订单", "发货明细", "发货记录", "出库明细", "发货单"]),
    ("order",             ["店铺订单", "订单明细", "订单"]),
]

# 已停用 Sheet/文件 关键词（命中即标记 skipped，不参与计算）
DEPRECATED_SHEET_KEYWORDS = ["运费险", "退货运费险", "运险", "售后单", "售后明细", "退款单", "售后"]

# Sheet 名称识别规则（新版 7 类）
SHEET_TYPE_DETECTION_RULES: list[tuple[str, list[str]]] = [
    ("product_cost",      ["商品成本表", "商品成本", "成本表", "成本"]),
    ("fund",              ["资金账单", "资金流水", "资金明细", "资金"]),
    ("shipping_order",    ["发货订单", "发货明细", "发货记录", "出库明细", "发货单"]),
    ("order",             ["店铺订单", "订单明细", "店铺订单明细", "订单"]),
    ("settlement",        ["结算账单", "结算明细", "结算"]),
    ("ad_cost",           ["广告费", "推广费", "投流", "千川", "广告消耗", "广告"]),
    ("freight",           ["运费明细", "快递费", "物流费", "运费"]),
]

# 无关 Sheet 名称（标记为 skipped）
SKIP_SHEET_NAMES = {"说明", "readme", "汇总", "透视表", "sheet1", "sheet2", "sheet3"}


def detect_sheet_type(sheet_name: str) -> str | None:
    """
    识别 Sheet 名称对应的新版 7 类文件类型，或返回特殊标记：
      None         → 无关/无法识别
      "_deprecated" → 售后单/运费险 等已停用类型（不参与计算）
    注意：必须先判停用类型（运费险含“运费”会误命中运费）。
    """
    name = sheet_name.strip()
    name_lower = name.lower()
    if name_lower in SKIP_SHEET_NAMES or not name:
        return None
    # 新版停用：运费险 / 售后单 → 不参与计算
    if any(kw in name for kw in DEPRECATED_SHEET_KEYWORDS):
        return "_deprecated"
    for ft, keywords in SHEET_TYPE_DETECTION_RULES:
        if any(kw in name for kw in keywords):
            return ft
    return None


# ─── 内部工具 ──────────────────────────────────────────────

def _auto_batch_name(month: str, scope_type: str, scope_name: str | None) -> str:
    if scope_type == "all_stores":
        return f"{month}-全公司销售月报"
    if scope_name:
        return f"{month}-{scope_name}-销售月报"
    return f"{month}-销售月报"


def _detect_file_type(filename: str) -> str | None:
    """按优先顺序匹配文件类型关键词"""
    name = filename.replace("_", " ").replace("-", " ")
    for ft, keywords in FILE_TYPE_DETECTION_RULES:
        if any(kw in name for kw in keywords):
            return ft
    return None


async def _detect_store(
    db: AsyncSession, filename: str, batch_id: int
) -> tuple[str | None, str, str]:
    """从文件名中识别店铺，返回 (store_name, detect_status, message)"""
    # 从活跃的店铺归属配置里匹配
    q = await db.execute(
        select(FinSalesMonthlyStoreOwnership).where(
            FinSalesMonthlyStoreOwnership.is_active.is_(True)
        )
    )
    ownerships = q.scalars().all()
    matched = [o for o in ownerships if o.store_name in filename]
    if len(matched) == 1:
        return matched[0].store_name, "detected", ""
    if len(matched) > 1:
        names = "、".join(o.store_name for o in matched)
        return None, "need_confirm", f"匹配到多个店铺：{names}，请人工确认"
    return None, "need_confirm", "未识别店铺，请人工确认"


async def _update_batch_stats(db: AsyncSession, batch_id: int) -> None:
    """更新批次的文件统计（uploaded_file_count / missing_required_count）"""
    q = await db.execute(
        select(FinSalesMonthlyImportFile).where(
            FinSalesMonthlyImportFile.batch_id == batch_id,
            FinSalesMonthlyImportFile.is_active.is_(True),
        )
    )
    files = q.scalars().all()
    uploaded_count     = len(files)
    present_types      = {f.file_type for f in files if f.file_type}
    missing_required   = len([t for t in REQUIRED_FILE_TYPES if t not in present_types])
    abnormal_count     = sum(1 for f in files if f.detect_status in ("need_confirm", "failed"))

    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if b:
        b.uploaded_file_count   = uploaded_count
        b.missing_required_count = missing_required
        b.abnormal_file_count    = abnormal_count
        b.updated_at             = datetime.utcnow()
    await db.commit()


async def _compute_expected_store_count(
    db: AsyncSession, batch: "FinSalesMonthlyReportBatch"
) -> int:
    """计算批次预期店铺数"""
    if batch.scope_type == "single_store":
        return 1 if batch.scope_name else 0
    from sqlalchemy import func
    q = select(FinSalesMonthlyStoreOwnership).where(
        FinSalesMonthlyStoreOwnership.is_active.is_(True)
    )
    if batch.scope_type == "partner" and batch.scope_name:
        q = q.where(FinSalesMonthlyStoreOwnership.partner_name == batch.scope_name)
    elif batch.scope_type == "custom_group" and batch.scope_name:
        q = q.where(FinSalesMonthlyStoreOwnership.group_name == batch.scope_name)
    total_q = select(func.count()).select_from(q.subquery())
    return (await db.execute(total_q)).scalar() or 0


# ─── 店铺归属配置 ──────────────────────────────────────────

async def list_store_ownerships(
    db: AsyncSession, *,
    partner_name: str | None = None,
    group_name: str | None = None,
    is_active: bool | None = None,
    month: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list, int]:
    q = select(FinSalesMonthlyStoreOwnership)
    if partner_name:
        q = q.where(FinSalesMonthlyStoreOwnership.partner_name.ilike(f"%{partner_name}%"))
    if group_name:
        q = q.where(FinSalesMonthlyStoreOwnership.group_name.ilike(f"%{group_name}%"))
    if is_active is not None:
        q = q.where(FinSalesMonthlyStoreOwnership.is_active.is_(is_active))
    if month:
        q = q.where(
            and_(
                (FinSalesMonthlyStoreOwnership.effective_month <= month) |
                (FinSalesMonthlyStoreOwnership.effective_month.is_(None)),
                (FinSalesMonthlyStoreOwnership.end_month >= month) |
                (FinSalesMonthlyStoreOwnership.end_month.is_(None)),
            )
        )
    from sqlalchemy import func
    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar() or 0
    q = q.order_by(FinSalesMonthlyStoreOwnership.id).limit(limit).offset(offset)
    items = (await db.execute(q)).scalars().all()
    return list(items), total


async def create_store_ownership(db: AsyncSession, **kwargs) -> FinSalesMonthlyStoreOwnership:
    obj = FinSalesMonthlyStoreOwnership(**kwargs)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def update_store_ownership(
    db: AsyncSession, ownership_id: int, **kwargs
) -> FinSalesMonthlyStoreOwnership:
    obj = await db.get(FinSalesMonthlyStoreOwnership, ownership_id)
    if not obj:
        raise ValueError("店铺归属配置不存在")
    for k, v in kwargs.items():
        setattr(obj, k, v)
    obj.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(obj)
    return obj


async def deactivate_store_ownership(
    db: AsyncSession, ownership_id: int
) -> FinSalesMonthlyStoreOwnership:
    obj = await db.get(FinSalesMonthlyStoreOwnership, ownership_id)
    if not obj:
        raise ValueError("店铺归属配置不存在")
    obj.is_active = False
    obj.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(obj)
    return obj


# ─── 批次 ──────────────────────────────────────────────────

async def create_batch(
    db: AsyncSession, *,
    month: str,
    batch_name: str = "",
    scope_type: str = "all_stores",
    scope_name: str | None = None,
    remark: str | None = None,
    user_id: int | None = None,
) -> FinSalesMonthlyReportBatch:
    if not batch_name:
        batch_name = _auto_batch_name(month, scope_type, scope_name)
    b = FinSalesMonthlyReportBatch(
        month=month,
        batch_name=batch_name,
        scope_type=scope_type,
        scope_name=scope_name,
        remark=remark,
        created_by=user_id,
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)
    b.expected_store_count = await _compute_expected_store_count(db, b)
    await db.commit()
    await db.refresh(b)
    return b


def _ensure_not_deleted(b: FinSalesMonthlyReportBatch) -> None:
    """已软删除批次禁止任何后续操作。"""
    if getattr(b, "is_deleted", False):
        raise ValueError("该销售月报批次已删除，不能继续操作。")


async def list_batches(
    db: AsyncSession, *,
    month: str | None = None,
    scope_type: str | None = None,
    scope_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
    include_deleted: bool = False,
) -> tuple[list, int]:
    q = select(FinSalesMonthlyReportBatch)
    if not include_deleted:
        # 默认只返回未删除批次（兼容历史 NULL 行）
        q = q.where(FinSalesMonthlyReportBatch.is_deleted.isnot(True))
    if month:
        q = q.where(FinSalesMonthlyReportBatch.month == month)
    if scope_type:
        q = q.where(FinSalesMonthlyReportBatch.scope_type == scope_type)
    if scope_name:
        q = q.where(FinSalesMonthlyReportBatch.scope_name.ilike(f"%{scope_name}%"))
    from sqlalchemy import func
    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar() or 0
    q = q.order_by(FinSalesMonthlyReportBatch.id.desc()).limit(limit).offset(offset)
    items = (await db.execute(q)).scalars().all()
    return list(items), total


async def get_batch(
    db: AsyncSession, batch_id: int, include_deleted: bool = False
) -> FinSalesMonthlyReportBatch | None:
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if b is None:
        return None
    if not include_deleted and getattr(b, "is_deleted", False):
        return None
    return b


async def lock_batch(
    db: AsyncSession, batch_id: int
) -> FinSalesMonthlyReportBatch:
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise ValueError("批次不存在")
    _ensure_not_deleted(b)
    if b.status != "completed":
        raise ValueError("只有已完成的批次才能锁定")
    b.status    = "locked"
    b.locked_at = datetime.utcnow()
    await db.commit()
    await db.refresh(b)
    return b


async def delete_batch(
    db: AsyncSession, batch_id: int, *,
    user_id: int | None = None,
    reason: str | None = None,
) -> dict:
    """软删除销售月报批次（不物理删除关联文件/订单/月报结果）。"""
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise LookupError("销售月报批次不存在")
    if getattr(b, "is_deleted", False):
        return {"ok": True, "message": "该批次已删除"}
    if b.status == "locked":
        raise ValueError("该批次已锁定，不能删除。如需删除，请先解锁。")
    if b.status == "processing":
        raise ValueError("该批次正在生成中，不能删除")
    b.is_deleted    = True
    b.deleted_at    = datetime.utcnow()
    b.deleted_by    = user_id
    b.delete_reason = (reason or None)
    b.updated_at    = datetime.utcnow()
    await db.commit()
    return {"ok": True, "message": "销售月报批次已删除"}


# ─── 文件上传 ──────────────────────────────────────────────

async def save_upload(
    db: AsyncSession, *,
    batch_id: int,
    file_type: str,
    store_name: str,
    original_filename: str,
    file_bytes: bytes,
) -> FinSalesMonthlyImportFile:
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise ValueError("批次不存在")
    _ensure_not_deleted(b)
    if b.status == "locked":
        raise ValueError("批次已锁定，无法上传")

    # 单表上传扩展名校验（xlsx/xlsm/xltx/xltm/csv；.xls 视环境）
    importers.check_single_table_ext(original_filename)

    # 存储文件
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w\-\.]", "_", original_filename)
    file_path = UPLOAD_ROOT / f"{batch_id}_{file_type}_{store_name}_{ts}_{safe_name}"
    await asyncio.to_thread(file_path.write_bytes, file_bytes)

    # 旧文件标记失效
    old_q = await db.execute(
        select(FinSalesMonthlyImportFile).where(
            FinSalesMonthlyImportFile.batch_id == batch_id,
            FinSalesMonthlyImportFile.file_type == file_type,
            FinSalesMonthlyImportFile.store_name == store_name,
            FinSalesMonthlyImportFile.is_active.is_(True),
        )
    )
    old_files = old_q.scalars().all()

    record = FinSalesMonthlyImportFile(
        batch_id=batch_id,
        file_type=file_type,
        store_name=store_name,
        original_filename=original_filename,
        file_path=str(file_path),
        detect_status="detected",
    )
    db.add(record)
    await db.flush()

    for old in old_files:
        old.is_active = False
        old.replaced_by_file_id = record.id

    # 已完成批次再上传新文件 → 退回 draft，提示重新生成
    if b.status == "completed":
        b.status = "draft"
        b.updated_at = datetime.utcnow()

    await _update_batch_stats(db, batch_id)
    return record


async def save_upload_workbook(
    db: AsyncSession,
    *,
    batch_id: int,
    store_name: str,
    original_filename: str,
    file_bytes: bytes,
    scope_type: str | None = None,
    scope_name: str | None = None,
) -> dict:
    """
    解析工作簿，自动识别每个 Sheet 并分别入库。
    所有 openpyxl 操作在线程池中运行，不阻塞事件循环。
    """
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise ValueError("批次不存在")
    _ensure_not_deleted(b)
    if b.status == "locked":
        raise ValueError("批次已锁定，无法上传")

    # 工作簿上传只接受真正的多 Sheet Excel 工作簿（拒绝 CSV/.xls）
    importers.check_workbook_ext(original_filename)

    # 1. 保存原始工作簿文件
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w\-\.]", "_", original_filename)
    file_path = UPLOAD_ROOT / f"{batch_id}_wb_{store_name}_{ts}_{safe_name}"
    await asyncio.to_thread(file_path.write_bytes, file_bytes)

    # 2. 创建工作簿主记录（is_active=False，自身不参与月报生成）
    wb_record = FinSalesMonthlyImportFile(
        batch_id=batch_id,
        file_type="workbook",
        store_name=store_name,
        original_filename=original_filename,
        file_path=str(file_path),
        detect_status="detected",
        is_active=False,
    )
    db.add(wb_record)
    await db.flush()
    wb_record_id = wb_record.id

    batch_month = b.month

    # 3. 在线程池中执行所有阻塞 openpyxl 操作
    def _process_workbook_sync() -> dict:
        """同步函数：识别每个 Sheet 并提取为独立 xlsx bytes（不阻塞 asyncio 事件循环）"""
        import openpyxl
        import io as _io_inner

        try:
            wb = openpyxl.load_workbook(str(file_path), data_only=True)
        except Exception as exc:
            return {"error": f"无法打开工作簿：{exc}", "sheets": []}

        seen_types: dict[str, bool] = {}
        sheets_info = []

        for sn in wb.sheetnames:
            sn_stripped = sn.strip()
            sn_lower = sn_stripped.lower()

            # 跳过无关 Sheet
            if sn_lower in SKIP_SHEET_NAMES or not sn_stripped:
                sheets_info.append({
                    "sheet_name": sn, "detected_ft": None,
                    "detect_status": "skipped", "row_count": 0,
                    "success_count": 0, "error_msg": "无关工作表，已跳过",
                    "file_bytes": None,
                })
                continue

            ft = detect_sheet_type(sn_stripped)

            if ft == "_deprecated":
                sheets_info.append({
                    "sheet_name": sn, "detected_ft": None,
                    "detect_status": "skipped", "row_count": 0,
                    "success_count": 0,
                    "error_msg": "新版规则已停用售后单/独立运费险表，该 Sheet 不参与销售月报计算",
                    "file_bytes": None,
                })
                continue

            if ft is None:
                sheets_info.append({
                    "sheet_name": sn, "detected_ft": None,
                    "detect_status": "need_confirm", "row_count": 0,
                    "success_count": 0,
                    "error_msg": "无法识别 Sheet 类型，请人工确认",
                    "file_bytes": None,
                })
                continue

            if ft in seen_types:
                sheets_info.append({
                    "sheet_name": sn, "detected_ft": ft,
                    "detect_status": "need_confirm", "row_count": 0,
                    "success_count": 0,
                    "error_msg": f"同一工作簿存在多个 {ft} Sheet，请人工确认",
                    "file_bytes": None,
                })
                continue

            ws = wb[sn]
            row_count = ws.max_row or 0

            try:
                # 用 write_only 模式 + append 提取 Sheet（比 cell-by-cell 快 10-20 倍）
                buf = _io_inner.BytesIO()
                new_wb = openpyxl.Workbook(write_only=True)
                new_ws = new_wb.create_sheet()
                for row_vals in ws.iter_rows(values_only=True):
                    new_ws.append(list(row_vals))
                new_wb.save(buf)
                sheet_bytes = buf.getvalue()
                new_wb.close()

                seen_types[ft] = True
                sheets_info.append({
                    "sheet_name": sn, "detected_ft": ft,
                    "detect_status": "detected",
                    "row_count": row_count,
                    "success_count": max(0, row_count - 1),
                    "error_msg": None,
                    "file_bytes": sheet_bytes,
                })
            except Exception as exc:
                sheets_info.append({
                    "sheet_name": sn, "detected_ft": ft,
                    "detect_status": "failed",
                    "row_count": row_count, "success_count": 0,
                    "error_msg": str(exc)[:500],
                    "file_bytes": None,
                })

        wb.close()
        return {"error": None, "sheets": sheets_info}

    workbook_data = await asyncio.to_thread(_process_workbook_sync)

    if workbook_data.get("error"):
        raise ValueError(workbook_data["error"])

    # 4. 将提取结果写入数据库（异步安全）
    sheet_results = []

    for sinfo in workbook_data["sheets"]:
        sn          = sinfo["sheet_name"]
        detected_ft = sinfo["detected_ft"]
        det_status  = sinfo["detect_status"]
        row_count   = sinfo.get("row_count", 0)
        success_cnt = sinfo.get("success_count", 0)
        error_msg   = sinfo.get("error_msg")
        sheet_bytes = sinfo.get("file_bytes")

        if det_status == "detected" and sheet_bytes:
            sheet_safe = re.sub(r"[^\w\-\.]", "_", f"{store_name}_{detected_ft}_{sn}.xlsx")
            sheet_file_path = UPLOAD_ROOT / f"{batch_id}_sheet_{ts}_{sheet_safe}"
            await asyncio.to_thread(sheet_file_path.write_bytes, sheet_bytes)

            # 旧同类型文件标记失效
            old_q = await db.execute(
                select(FinSalesMonthlyImportFile).where(
                    FinSalesMonthlyImportFile.batch_id == batch_id,
                    FinSalesMonthlyImportFile.file_type == detected_ft,
                    FinSalesMonthlyImportFile.store_name == store_name,
                    FinSalesMonthlyImportFile.is_active.is_(True),
                )
            )
            old_files = old_q.scalars().all()

            sheet_import_rec = FinSalesMonthlyImportFile(
                batch_id=batch_id,
                file_type=detected_ft,
                store_name=store_name,
                original_filename=f"{original_filename}[{sn}]",
                file_path=str(sheet_file_path),
                detect_status="detected",
                detected_file_type=detected_ft,
                detected_store_name=store_name,
                is_active=True,
                row_count=success_cnt,
            )
            db.add(sheet_import_rec)
            await db.flush()

            for old in old_files:
                old.is_active = False
                old.replaced_by_file_id = sheet_import_rec.id

        # Sheet 详情记录
        sheet_rec = FinSalesMonthlyImportSheet(
            import_file_id=wb_record_id,
            batch_id=batch_id,
            store_name=store_name,
            sheet_name=sn,
            detected_file_type=detected_ft,
            detect_status=det_status,
            row_count=row_count,
            success_count=success_cnt,
            error_count=1 if det_status == "failed" else 0,
            error_message=error_msg,
        )
        db.add(sheet_rec)
        await db.flush()

        sheet_results.append({
            "sheet_name": sn,
            "detected_file_type": detected_ft,
            "detect_status": det_status,
            "row_count": row_count,
            "success_count": success_cnt,
            "error_count": 1 if det_status == "failed" else 0,
            "error_message": error_msg,
        })

    # 5. 批次状态：completed → draft（需重新生成）
    status_reset_msg = None
    if b.status == "completed":
        b.status = "draft"
        b.updated_at = datetime.utcnow()
        status_reset_msg = "文件已更新，请重新生成月报"

    await db.commit()
    await _update_batch_stats(db, batch_id)

    detected_count     = sum(1 for r in sheet_results if r["detect_status"] == "detected")
    need_confirm_count = sum(1 for r in sheet_results if r["detect_status"] == "need_confirm")
    failed_count       = sum(1 for r in sheet_results if r["detect_status"] == "failed")
    skipped_count      = sum(1 for r in sheet_results if r["detect_status"] == "skipped")

    return {
        "import_file_id": wb_record_id,
        "original_filename": original_filename,
        "store_name": store_name,
        "sheet_results": sheet_results,
        "total_sheets": len(sheet_results),
        "detected_count": detected_count,
        "need_confirm_count": need_confirm_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "status_reset_msg": status_reset_msg,
    }


def _parse_check_sheet(wb, file_type: str, month: str, store_name: str) -> None:
    """对单个 sheet 做解析验证（只检查是否能解析，不保存结果）。"""
    if file_type == "order":
        result = importers.parse_order_file(wb, month, store_name)
        if not result:
            raise ValueError("订单文件解析结果为空，请检查发货时间是否在当月")
    elif file_type == "settlement":
        importers.parse_settlement_file(wb, month)
    elif file_type == "after_sale":
        importers.parse_after_sale_file(wb)
    elif file_type == "product_cost":
        importers.parse_product_cost_file(wb)
    elif file_type == "shipping_order":
        importers.parse_shipping_order_file(wb, month)
    elif file_type in ("fund", "freight", "freight_insurance", "ad_cost"):
        pass
    else:
        raise ValueError(f"未知文件类型: {file_type}")


async def bulk_upload_workbooks(
    db: AsyncSession,
    *,
    batch_id: int,
    files_data: list[tuple[str, bytes]],
) -> list[dict]:
    """批量上传工作簿。店铺名称从文件名中识别。"""
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise ValueError("批次不存在")
    _ensure_not_deleted(b)
    if b.status == "locked":
        raise ValueError("批次已锁定，请先解锁")

    results = []
    for original_filename, file_bytes in files_data:
        store_name, dstatus, dmsg = await _detect_store(db, original_filename, batch_id)
        if not store_name:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_name = re.sub(r"[^\w\-\.]", "_", original_filename)
            file_path = UPLOAD_ROOT / f"{batch_id}_wb_unknown_{ts}_{safe_name}"
            await asyncio.to_thread(file_path.write_bytes, file_bytes)
            wb_record = FinSalesMonthlyImportFile(
                batch_id=batch_id,
                file_type="workbook",
                store_name="",
                original_filename=original_filename,
                file_path=str(file_path),
                detect_status="need_confirm",
                detect_message=dmsg or "无法识别店铺，请人工确认",
                is_active=False,
            )
            db.add(wb_record)
            await db.flush()
            results.append({
                "import_file_id": wb_record.id,
                "original_filename": original_filename,
                "store_name": "",
                "sheet_results": [],
                "total_sheets": 0,
                "detected_count": 0,
                "need_confirm_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
            })
            continue

        try:
            result = await save_upload_workbook(
                db,
                batch_id=batch_id,
                store_name=store_name,
                original_filename=original_filename,
                file_bytes=file_bytes,
            )
            results.append(result)
        except Exception as e:
            logger.error(f"工作簿解析失败 {original_filename}: {e}")
            results.append({
                "import_file_id": 0,
                "original_filename": original_filename,
                "store_name": store_name,
                "sheet_results": [],
                "total_sheets": 0,
                "detected_count": 0,
                "need_confirm_count": 0,
                "failed_count": 1,
                "skipped_count": 0,
            })

    await db.commit()
    return results


async def get_workbook_sheets(
    db: AsyncSession, batch_id: int
) -> list:
    q = await db.execute(
        select(FinSalesMonthlyImportSheet).where(
            FinSalesMonthlyImportSheet.batch_id == batch_id
        ).order_by(FinSalesMonthlyImportSheet.id)
    )
    return q.scalars().all()


async def confirm_sheet(
    db: AsyncSession,
    sheet_id: int,
    store_name: str,
    file_type: str,
) -> dict:
    """人工确认 Sheet 类型，重新创建 import_file 记录。"""
    import openpyxl
    import io as _io

    sheet_rec = await db.get(FinSalesMonthlyImportSheet, sheet_id)
    if not sheet_rec:
        raise ValueError("Sheet 记录不存在")
    if sheet_rec.detect_status not in ("need_confirm", "failed"):
        raise ValueError("该 Sheet 不在待确认状态")

    wb_file = await db.get(FinSalesMonthlyImportFile, sheet_rec.import_file_id)
    if not wb_file or not wb_file.file_path:
        raise ValueError("工作簿文件不存在")

    b = await db.get(FinSalesMonthlyReportBatch, sheet_rec.batch_id)
    wb = openpyxl.load_workbook(wb_file.file_path, data_only=True)
    if sheet_rec.sheet_name not in wb.sheetnames:
        raise ValueError(f"工作簿中找不到 Sheet: {sheet_rec.sheet_name}")

    ws = wb[sheet_rec.sheet_name]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    sheet_file_bytes = _io.BytesIO()
    tmp_wb = openpyxl.Workbook()
    tmp_ws = tmp_wb.active
    for row in ws.iter_rows():
        for cell in row:
            tmp_ws.cell(row=cell.row, column=cell.column, value=cell.value)
    tmp_wb.save(sheet_file_bytes)

    sheet_safe_name = re.sub(r"[^\w\-\.]", "_", f"{store_name}_{file_type}_{sheet_rec.sheet_name}.xlsx")
    sheet_file_path = UPLOAD_ROOT / f"{sheet_rec.batch_id}_sheet_confirm_{ts}_{sheet_safe_name}"
    sheet_bytes = sheet_file_bytes.getvalue()
    await asyncio.to_thread(sheet_file_path.write_bytes, sheet_bytes)

    old_q = await db.execute(
        select(FinSalesMonthlyImportFile).where(
            FinSalesMonthlyImportFile.batch_id == sheet_rec.batch_id,
            FinSalesMonthlyImportFile.file_type == file_type,
            FinSalesMonthlyImportFile.store_name == store_name,
            FinSalesMonthlyImportFile.is_active.is_(True),
        )
    )
    for old in old_q.scalars().all():
        old.is_active = False

    new_rec = FinSalesMonthlyImportFile(
        batch_id=sheet_rec.batch_id,
        file_type=file_type,
        store_name=store_name,
        original_filename=wb_file.original_filename + f"[{sheet_rec.sheet_name}]",
        file_path=str(sheet_file_path),
        detect_status="detected",
        detected_file_type=file_type,
        detected_store_name=store_name,
        is_active=True,
    )
    db.add(new_rec)
    await db.flush()

    sheet_rec.detected_file_type = file_type
    sheet_rec.detect_status = "detected"
    sheet_rec.store_name = store_name
    sheet_rec.updated_at = datetime.utcnow()

    wb.close()
    await db.commit()
    await _update_batch_stats(db, sheet_rec.batch_id)
    return {"sheet_id": sheet_id, "import_file_id": new_rec.id, "message": "人工确认成功"}


async def bulk_upload_files(
    db: AsyncSession, *,
    batch_id: int,
    files_data: list[tuple[str, bytes]],
) -> list[dict]:
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise ValueError("批次不存在")
    _ensure_not_deleted(b)
    if b.status == "locked":
        raise ValueError("批次已锁定，请先解锁")

    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    results = []

    for original_filename, file_bytes in files_data:
        detect_status = "need_confirm"
        detect_message = ""
        detected_file_type = _detect_file_type(original_filename)
        detected_store_name = None

        if detected_file_type:
            store, dstatus, dmsg = await _detect_store(db, original_filename, batch_id)
            detected_store_name = store
            if store:
                detect_status = "detected"
                detect_message = ""
            else:
                detect_status = dstatus
                detect_message = dmsg or "无法识别文件类型，请人工确认"
        else:
            detect_status = "need_confirm"
            detect_message = "无法识别文件类型，请人工确认"

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[^\w\-\.]", "_", original_filename)
        file_path = UPLOAD_ROOT / f"{batch_id}_bulk_{ts}_{safe_name}"
        await asyncio.to_thread(file_path.write_bytes, file_bytes)

        record = FinSalesMonthlyImportFile(
            batch_id=batch_id,
            file_type=detected_file_type or "unknown",
            store_name=detected_store_name or "",
            original_filename=original_filename,
            file_path=str(file_path),
            detected_file_type=detected_file_type,
            detected_store_name=detected_store_name,
            detect_status=detect_status,
            detect_message=detect_message,
            is_active=(detect_status == "detected"),
        )
        db.add(record)
        results.append({
            "original_filename":    original_filename,
            "detect_status":        detect_status,
            "detect_message":       detect_message,
            "detected_file_type":   detected_file_type,
            "detected_store_name":  detected_store_name,
        })

    await db.commit()
    await _update_batch_stats(db, batch_id)
    return results


async def get_unconfirmed_files(
    db: AsyncSession, batch_id: int
) -> list[FinSalesMonthlyImportFile]:
    q = await db.execute(
        select(FinSalesMonthlyImportFile).where(
            FinSalesMonthlyImportFile.batch_id == batch_id,
            FinSalesMonthlyImportFile.detect_status == "need_confirm",
        )
    )
    return q.scalars().all()


async def confirm_file(
    db: AsyncSession,
    file_id: int,
    store_name: str,
    file_type: str,
) -> FinSalesMonthlyImportFile:
    f = await db.get(FinSalesMonthlyImportFile, file_id)
    if not f:
        raise ValueError("文件记录不存在")
    if f.detect_status != "need_confirm":
        raise ValueError("该文件不在待确认状态")
    f.store_name  = store_name
    f.file_type   = file_type
    f.detect_status = "detected"
    f.detect_message = "人工确认"
    f.is_active   = True
    f.updated_at  = datetime.utcnow()
    await db.commit()
    await _update_batch_stats(db, f.batch_id)
    await db.refresh(f)
    return f


async def get_upload_matrix(
    db: AsyncSession, batch_id: int
) -> dict:
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise ValueError("批次不存在")
    _ensure_not_deleted(b)
    stores_info = await _get_scope_stores(db, b)
    q = await db.execute(
        select(FinSalesMonthlyImportFile).where(
            FinSalesMonthlyImportFile.batch_id == batch_id,
            FinSalesMonthlyImportFile.is_active.is_(True),
        )
    )
    files = q.scalars().all()
    file_map: dict[tuple, FinSalesMonthlyImportFile] = {}
    for f in files:
        file_map[(f.store_name, f.file_type)] = f

    matrix_rows = _build_matrix_rows(stores_info, file_map)
    return {
        "stores": matrix_rows,
        "file_types": ALL_FILE_TYPES,
    }


def _build_matrix_rows(stores_info: list[dict], file_map: dict) -> list[dict]:
    """构建矩阵数据（内部用）"""
    rows = []
    for si in stores_info:
        store_name = si["store_name"]
        file_statuses = []
        for ft in ALL_FILE_TYPES:
            f = file_map.get((store_name, ft))
            if f:
                file_statuses.append({
                    "file_type": ft,
                    "status": "uploaded",
                    "file_id": f.id,
                    "filename": f.original_filename,
                })
            else:
                file_statuses.append({
                    "file_type": ft,
                    "status": "missing",
                    "file_id": None,
                    "filename": None,
                })
        rows.append({
            "store_name": store_name,
            "partner_name": si.get("partner_name"),
            "files": file_statuses,
        })
    return rows


async def _get_scope_stores(
    db: AsyncSession, batch: FinSalesMonthlyReportBatch
) -> list[dict]:
    """返回当月指定范围内的店铺列表 [{store_name, partner_name, group_name}]"""
    q = select(FinSalesMonthlyStoreOwnership).where(
        FinSalesMonthlyStoreOwnership.is_active.is_(True)
    )
    if batch.scope_type == "partner" and batch.scope_name:
        q = q.where(FinSalesMonthlyStoreOwnership.partner_name == batch.scope_name)
    elif batch.scope_type == "custom_group" and batch.scope_name:
        q = q.where(FinSalesMonthlyStoreOwnership.group_name == batch.scope_name)
    elif batch.scope_type == "single_store" and batch.scope_name:
        q = q.where(FinSalesMonthlyStoreOwnership.store_name == batch.scope_name)
    result = await db.execute(q)
    rows = result.scalars().all()
    if rows:
        return [{"store_name": r.store_name, "partner_name": r.partner_name,
                 "group_name": r.group_name} for r in rows]
    # 如果归属配置里没有，从已上传文件推断
    q2 = await db.execute(
        select(FinSalesMonthlyImportFile.store_name).distinct().where(
            FinSalesMonthlyImportFile.batch_id == batch.id,
            FinSalesMonthlyImportFile.is_active.is_(True),
        )
    )
    store_names = [r[0] for r in q2.all() if r[0]]
    return [{"store_name": s, "partner_name": None, "group_name": None} for s in store_names]


# ─── 月报生成 ──────────────────────────────────────────────


async def precheck_batch(db: AsyncSession, batch_id: int, mode: str = "loose") -> dict:
    """
    生成前校验：检查每个店铺的必传/可选文件缺失情况。
    返回结构化结果供前端展示。
    """
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise ValueError("批次不存在")
    _ensure_not_deleted(b)

    # 取活跃文件
    q = await db.execute(
        select(FinSalesMonthlyImportFile).where(
            FinSalesMonthlyImportFile.batch_id == batch_id,
            FinSalesMonthlyImportFile.is_active.is_(True),
            FinSalesMonthlyImportFile.detect_status == "detected",
        )
    )
    active_files = q.scalars().all()

    # 计算预期店铺
    expected = await _compute_expected_store_count(db, b)

    # 按店铺分组（保留文件记录，用于生成前试解析）
    from collections import defaultdict
    store_file_recs: dict[str, dict[str, FinSalesMonthlyImportFile]] = defaultdict(dict)
    for f in active_files:
        if f.file_type != "workbook":
            store_file_recs[f.store_name][f.file_type] = f
    store_files: dict[str, set] = {s: set(recs.keys()) for s, recs in store_file_recs.items()}

    # 如果 single_store 且没有任何文件，用 scope_name 占位
    if b.scope_type == "single_store" and b.scope_name and not store_files:
        store_files[b.scope_name] = set()

    def _cn(ft: str) -> str:
        return FILE_TYPE_CN.get(ft, ft)

    # 检查每个店铺
    store_results = []
    blocking_errors: list[str] = []
    warnings_list: list[str] = []

    for store_name, present_types in store_files.items():
        missing_req = [t for t in REQUIRED_FILE_TYPES if t not in present_types]
        missing_opt = [t for t in OPTIONAL_FILE_TYPES if t not in present_types]
        can_generate = len(missing_req) == 0 or mode == "loose"
        messages = []
        # 必传缺失（用中文名展示，单独点名商品成本表）
        if missing_req:
            msg = f"缺少必传文件：{'、'.join(_cn(t) for t in missing_req)}"
            messages.append(msg)
            if mode == "strict":
                blocking_errors.append(f"{store_name} {msg}")
            else:
                warnings_list.append(f"{store_name} {msg}，相关字段按0处理")
        if "product_cost" in missing_req:
            messages.append("缺少商品成本表")
            warnings_list.append(f"{store_name} 缺少商品成本表，成本按 0 处理，毛利和净利润不可信")
        if missing_opt:
            warnings_list.append(
                f"{store_name} 缺少可选文件：{'、'.join(_cn(t) for t in missing_opt)}，相关字段按0处理"
            )
        if "order" not in present_types:
            messages.append("无订单文件，无法生成")
            can_generate = False
            blocking_errors.append(f"{store_name} 无订单文件")

        # 生成前试解析关键文件，提前暴露 CSV/格式/表头问题
        recs = store_file_recs.get(store_name, {})
        for ft in ("order", "settlement", "shipping_order", "fund", "product_cost",
                   "after_sale", "freight", "freight_insurance", "ad_cost"):
            rec = recs.get(ft)
            if not rec:
                continue
            ok2, err = await asyncio.to_thread(
                _validate_parse, ft, rec.file_path, rec.original_filename,
                b.month, store_name,
            )
            if not ok2:
                line = f"{_cn(ft)}解析失败：{err}"
                messages.append(line)
                warnings_list.append(f"{store_name} {line}")
                # 订单/结算解析失败 → 该店铺无法生成正常月报
                if ft in ("order", "settlement"):
                    can_generate = False
                    blocking_errors.append(f"{store_name} {line}")

        store_results.append({
            "store_name": store_name,
            "present_types": list(present_types),
            "required_missing": missing_req,
            "optional_missing": missing_opt,
            "can_generate": can_generate,
            "messages": messages,
        })

    if not store_files:
        blocking_errors.append("批次内没有任何已识别的上传文件")

    can_generate_count = sum(1 for s in store_results if s["can_generate"])
    ok = len(blocking_errors) == 0 and can_generate_count > 0

    return {
        "ok": ok,
        "mode": mode,
        "batch_id": batch_id,
        "scope_type": b.scope_type,
        "scope_name": b.scope_name,
        "expected_store_count": expected,
        "uploaded_store_count": len(store_files),
        "can_generate_count": can_generate_count,
        "stores": store_results,
        "blocking_errors": blocking_errors,
        "warnings": warnings_list,
    }


def _build_field_logs_v2(agg, stats, fund_agg, cost_total_codes, freight_col, ad_cost_col,
                         shipping_cost_stats, insurance_stats) -> list[dict]:
    """新版完整月报字段级计算日志（每字段一条，含来源/公式/值/异常）。"""
    def s(v): return str(v if v is not None else 0)
    logs = []
    def add(field, name, msg, detail, level="info", rc=None, sc=None, fc=None):
        logs.append({"field": field, "field_name": name, "stage": "field_calc_" + field,
                     "level": level, "message": msg,
                     "detail": {"field": field, "field_name": name, **detail},
                     "row_count": rc, "success_count": sc, "failed_count": fc})
    paid = agg["actual_sales_order_count"]
    add("shipped_order_count", "发货订单数", f"发货订单数=当月发货主订单去重={agg['shipped_order_count']}",
        {"source_tables": ["店铺订单"], "formula": "发货时间为当月的主订单编号去重", "included_value": s(agg["shipped_order_count"])})
    add("shipped_amount", "发货金额", f"发货金额=应收金额汇总={agg['shipped_amount']}",
        {"source_tables": ["店铺订单"], "formula": "发货金额=应收金额(商品单价×数量-商家优惠+运费)汇总", "included_value": s(agg["shipped_amount"])})
    add("refund_order_count", "退款订单数", f"退款订单数=结算账单收入合计<0的主订单去重={agg['refund_order_count']}",
        {"source_tables": ["结算账单"], "formula": "收入合计<0的订单主订单编号去重", "included_value": s(agg["refund_order_count"])})
    add("after_ship_refund_amount", "发货后退款金额",
        f"退货金额口径：仅统计结算账单中收入合计 < 0 的订单；不再将“不结算订单中的应收金额”计入退货金额。发货后退款金额={agg['after_ship_refund_amount']}",
        {"source_tables": ["结算账单"], "formula": "仅汇总结算账单收入合计<0的金额绝对值；不计入不结算订单的应收金额",
         "settlement_refund_total": s(stats["settlement_refund_sum"]), "included_value": s(agg["after_ship_refund_amount"])})
    asa = agg["actual_sales_amount"]
    add("actual_sales_amount", "实际销售额", f"实际销售额=已收款订单收款金额={asa}",
        {"source_tables": ["结算账单", "店铺订单"], "formula": "已收款订单收款金额(结算收入合计>0)汇总",
         "settlement_matched": stats["settlement_matched"], "paid_order_count": paid,
         "raw_value": s(stats["settlement_income_sum"]), "matched_value": s(stats["paid_income_sum"]),
         "included_value": s(asa), "written_value": s(asa),
         "difference_reason": ("实销单量>0但实际销售额=0：已收款订单未匹配到结算收款" if (paid > 0 and asa == 0) else None)},
        level=("warn" if (paid > 0 and asa == 0) else "info"))
    add("actual_sales_order_count", "实销单量", f"实销单量=已收款主订单去重={paid}", {"formula": "已收款订单主订单编号去重", "included_value": s(paid)})
    add("avg_order_amount", "客单价", f"客单价=实际销售额/实销单量={agg['avg_order_amount']}",
        {"formula": "实际销售额 / 实销单量", "included_value": s(agg["avg_order_amount"])})
    apc = agg["actual_product_cost"]
    add("actual_product_cost", "实际销售成本", f"实际销售成本=Σ(商品编码实发数量×成本价)={apc}",
        {"source_tables": ["发货订单", "商品成本表"], "formula": "Σ(每个商品编码的实发数量总和 × 该商品编码成本价)",
         "cost_matched": shipping_cost_stats["cost_matched_count"], "cost_missing": shipping_cost_stats["cost_missing_count"],
         "cost_total_codes": cost_total_codes, "raw_value": s(apc), "included_value": s(apc), "written_value": s(apc),
         "unmatched_product_code_samples": shipping_cost_stats["cost_missing_samples"],
         "difference_reason": ("发货订单商品编码未匹配成本价" if shipping_cost_stats["cost_missing_count"] else None)},
        level=("warn" if shipping_cost_stats["cost_missing_count"] else "info"),
        sc=shipping_cost_stats["cost_matched_count"], fc=shipping_cost_stats["cost_missing_count"])
    add("platform_service_fee", "平台服务费", f"平台服务费={agg['platform_service_fee']}",
        {"source_tables": ["资金账单"], "formula": "资金账单 动账时间当月 平台服务费之和", "included_value": s(agg["platform_service_fee"])})
    add("talent_commission", "达人佣金", f"达人佣金={agg['talent_commission']}",
        {"source_tables": ["结算账单"], "formula": "结算账单达人佣金按子订单编号匹配后汇总",
         "matched_sub_orders": stats["settlement_talent_commission_matched"], "included_value": s(agg["talent_commission"])})
    add("return_loss", "退货损耗", f"退货损耗=退款订单数={agg['return_loss']}", {"formula": "退款订单数", "included_value": s(agg["return_loss"])})
    add("freight_amount", "运费", f"运费={agg['freight_amount']}（运费表匹配 {stats['freight_matched_cnt']} 单）",
        {"source_tables": ["运费"], "formula": "运费表按子订单/运单匹配本月订单之和", "amount_column": freight_col,
         "matched_count": stats["freight_matched_cnt"], "included_value": s(agg["freight_amount"])})
    add("package_fee", "包装费", f"包装费=发货订单数×0.5={agg['package_fee']}", {"formula": "发货订单数 × 0.5", "included_value": s(agg["package_fee"])})
    add("freight_insurance", "运费险", f"运费险={agg['freight_insurance']}",
        {"source_tables": ["资金账单"], "formula": "资金账单运费险按子订单编号匹配后汇总",
         "raw_value": s(insurance_stats["raw_amount"]),
         "matched_count": insurance_stats["matched_count"], "unmatched_count": insurance_stats["unmatched_count"],
         "unmatched_amount": s(insurance_stats["unmatched_amount"]), "included_value": s(agg["freight_insurance"])},
        level=("warn" if insurance_stats["unmatched_count"] else "info"),
        sc=insurance_stats["matched_count"], fc=insurance_stats["unmatched_count"])
    add("platform_other_fee", "平台其他费用", f"平台其他费用={agg['platform_other_fee']}",
        {"source_tables": ["资金账单"], "formula": "偏远地区物流服务 + 权益保险 + 上门取件运费（动账时间当月）",
         "scene_breakdown": fund_agg.get("scene_breakdown"), "included_value": s(agg["platform_other_fee"])})
    add("ad_cost", "推广消耗", f"推广消耗={agg['ad_cost']}", {"source_tables": ["广告费"], "amount_column": ad_cost_col, "formula": "广告费表总额", "included_value": s(agg["ad_cost"])})
    add("compensation_amount", "消费者赔付", f"消费者赔付={agg['compensation_amount']}", {"source_tables": ["资金账单"], "formula": "动账场景=消费者赔付 当月合计", "included_value": s(agg["compensation_amount"])})
    add("small_payment_amount", "小额打款", f"小额打款={agg['small_payment_amount']}", {"source_tables": ["资金账单"], "formula": "动账场景=小额打款 当月合计", "included_value": s(agg["small_payment_amount"])})
    add("goods_loss", "货值损耗", f"货值损耗=发货订单数×1={agg['goods_loss']}", {"formula": "发货订单数 × 1", "included_value": s(agg["goods_loss"])})
    add("total_fee", "费用合计", f"费用合计={agg['total_fee']}",
        {"formula": "成本+平台服务费+达人佣金+退货损耗+运费+包装费+运费险+消费者赔付+小额打款+平台其他费用+客服+推广+管理费用+税务",
         "components": {"实际销售成本": s(agg["actual_product_cost"]), "平台服务费": s(agg["platform_service_fee"]),
                        "达人佣金": s(agg["talent_commission"]), "退货损耗": s(agg["return_loss"]), "运费": s(agg["freight_amount"]),
                        "包装费": s(agg["package_fee"]), "运费险": s(agg["freight_insurance"]), "消费者赔付": s(agg["compensation_amount"]),
                        "小额打款": s(agg["small_payment_amount"]), "平台其他费用": s(agg["platform_other_fee"]),
                        "推广消耗": s(agg["ad_cost"]), "税费": s(agg["tax_fee"])}, "included_value": s(agg["total_fee"])})
    add("gross_profit", "毛利", f"毛利=实际销售额-费用合计+订单理赔-货值损耗={agg['gross_profit']}",
        {"formula": "实际销售额 - 费用合计 + 订单理赔 - 货值损耗", "included_value": s(agg["gross_profit"])})
    add("net_profit", "净利润", f"净利润=毛利+返佣返点-保证金充值-其他扣减项={agg['net_profit']}",
        {"formula": "毛利 + 返佣返点 - 保证金充值 - 其他扣减项", "included_value": s(agg["net_profit"])})
    add("net_profit_rate", "净利润率", f"净利润率={agg['net_profit_rate']}", {"formula": "净利润 / 实际销售额", "included_value": s(agg["net_profit_rate"])})
    return logs


def _build_business_field_logs(agg, stats, settlement_diag, shipping_cost_stats,
                               fund_agg) -> list[dict]:
    """2026-06 文档版字段日志；active 生成链路只调用本函数。"""
    def s(value):
        return str(value if value is not None else 0)

    logs: list[dict] = []

    def add(field, name, formula, detail, level="info"):
        logs.append({
            "field": field, "field_name": name, "stage": "field_calc_" + field,
            "level": level, "message": f"{name}：{formula}，结果={s(agg.get(field))}",
            "detail": {"formula": formula, "written_value": s(agg.get(field)), **detail},
        })

    join_detail = {
        "join_type": "店铺订单主表 LEFT JOIN",
        "settlement_match_key": "主订单编号 + 子订单编号",
        "settlement_matched": stats["settlement_matched"],
        "settlement_unmatched": stats["settlement_unmatched"],
        "freight_match_key": "快递单号",
        "freight_matched": stats["freight_matched_cnt"],
    }
    add("shipped_order_count", "发货订单数", "发货时间非空的主订单编号去重", join_detail)
    add("shipped_amount", "发货金额", "当月发货订单商品金额汇总", join_detail)
    add("refund_order_count", "退款订单数", "仅已退款订单的主订单编号去重", {
        "refunded": stats["refunded"]})
    add("after_ship_refund_amount", "发货后退款金额", "已退款子订单结算差异汇总（商品金额-结算账单全日期净结算金额）", {})
    add("before_ship_refund_amount", "发货前退款金额", "发货时间为空且订单状态为已关闭的订单应收金额汇总", {})
    add("after_settlement_refund_amount", "结算后退款金额", "已收款订单后续结算后退款金额", {})
    add("actual_sales_amount", "实际销售额", "发货金额-发货后退款金额", {})
    add("actual_sales_order_count", "实销单量", "已收款与待结算订单主订单编号合并去重", {})
    add("actual_sales_order_completed", "实际销售订单", "与实销单量使用同一标准：已收款与待结算主订单编号合并去重", {})
    add("paid_sales_amount", "已付款销售额", "当月全部正向收款金额汇总（退款率分母）", {})
    add("actual_product_cost", "实际销售成本", "Σ(商品编码实发数量×成本单价)", shipping_cost_stats,
        level="warn" if shipping_cost_stats.get("cost_missing_count") else "info")
    add("platform_service_fee", "平台服务费", "结算账单当月平台服务费匹配汇总后取绝对值", settlement_diag)
    add("talent_commission", "达人佣金", "结算账单当月达人佣金匹配汇总后取绝对值", settlement_diag)
    add("freight_amount", "运费", "运费表按快递单号匹配后逐发货订单行汇总", join_detail)
    add("freight_insurance", "运费险", "资金账单当月运费险总额", {})
    add("platform_other_fee", "平台其他费用", "权益保险+上门取件运费+偏远地区物流服务", {
        "scene_breakdown": fund_agg.get("scene_breakdown", {})})
    for field, name, numerator in (
        ("total_refund_rate", "总退款率", "发货前退款+发货后退款+结算后退款"),
        ("before_ship_refund_rate", "发货前退款率", "发货前退款金额"),
        ("after_ship_refund_rate", "发货后退款率", "发货后退款金额"),
        ("after_settlement_refund_rate", "结算后退款率", "结算后退款金额"),
    ):
        add(field, name, f"{numerator}/已付款销售额", {
            "denominator": s(agg.get("paid_sales_amount")), "numerator_rule": numerator})
    add("total_fee", "费用合计", "成本+平台费+佣金+退货损耗+运费+包装+运费险+赔付+小额打款+平台其他+客服+推广+管理+税务", {})
    add("gross_profit", "毛利", "实际销售额-费用合计+订单理赔-货值损耗", {})
    add("net_profit", "净利润", "毛利+返佣返点-保证金-其他扣减项", {})
    return logs


def _merge_and_classify(orders, settlement_map, cost_map, freight_data=None,
                        fund_refund_by_sub=None, settlement_label_amount_map=None):
    """以店铺订单为主表，左连接附表并生成三类互斥订单标签。"""
    from collections import Counter
    Z = Decimal("0")
    fr_by_way = (freight_data or {}).get("by_waybill", {}) or {}
    fund_refund_by_sub = fund_refund_by_sub or {}
    settlement_label_amount_map = settlement_label_amount_map or {}

    final_orders: list[dict] = []
    status_counts: Counter = Counter()
    reason_counts: Counter = Counter()
    rule_code_counts: Counter = Counter()
    cost_matched = 0
    cost_unmatched = 0
    cost_unmatched_samples: list[str] = []
    settlement_matched = 0
    settlement_unmatched = 0
    settlement_income_sum = settlement_refund_sum = Z
    receivable_sum = Z
    freight_matched_sum = Z
    freight_matched_cnt = 0
    fund_refund_matched = 0
    fund_refund_matched_sum = Z

    for o in orders:
        main_no = o.get("main_order_no", "")
        sub_no = o.get("sub_order_no", "")
        key = (main_no, sub_no)
        for field in ("settlement_amount_total", "settlement_income", "refund_amount",
                      "settlement_before_refund", "platform_service_fee", "talent_commission"):
            o.setdefault(field, Z)
        sett = settlement_map.get(key)
        if sett is not None:
            settlement_matched += 1
            o["settlement_amount_total"] = sett.get("settlement_amount_total", Z) or Z
            o["settlement_income"] = sett.get("settlement_income", Z) or Z
            o["refund_amount"] = sett.get("refund_amount", Z) or Z
            o["settlement_before_refund"] = sett.get("settlement_before_refund", Z) or Z
            o["platform_service_fee"] = sett.get("platform_service_fee", Z) or Z
            o["talent_commission"] = sett.get("talent_commission", Z) or Z
        else:
            settlement_unmatched += 1
        o["settlement_difference"] = (
            _cdec(o.get("product_amount")) - _cdec(o.get("settlement_amount_total"))
        )
        income = o.get("settlement_income") or Z
        refund = o.get("refund_amount") or Z
        if sub_no in fund_refund_by_sub:
            o["fund_refund_amount"] = _cdec(fund_refund_by_sub[sub_no])
            fund_refund_matched += 1
            fund_refund_matched_sum += o["fund_refund_amount"]
        else:
            o["fund_refund_amount"] = Z

        pcode = o.get("product_code", "")
        if pcode in cost_map:
            cost_matched += 1
            o["product_cost_price"] = cost_map[pcode]
        else:
            cost_unmatched += 1
            if pcode and pcode not in cost_unmatched_samples and len(cost_unmatched_samples) < 10:
                cost_unmatched_samples.append(pcode)
            o["product_cost_price"] = Z
        o["product_cost_amount"] = o["product_cost_price"] * Decimal(str(o.get("quantity") or 0))

        # 新文档仅按快递单号左连接运费表。
        fr = fr_by_way.get(o.get("express_no")) if o.get("express_no") else None
        if fr is not None:
            freight_matched_sum += _cdec(fr)
            freight_matched_cnt += 1
        o["matched_freight"] = _cdec(fr) if fr is not None else Z

        settlement_income_sum += _cdec(income)
        settlement_refund_sum += _cdec(refund)
        receivable_sum += _cdec(o.get("receivable_amount"))

        ctx = dict(o)
        ctx["classification_settlement_amount"] = settlement_label_amount_map.get(key, Z)
        ctx["refund_amount"] = refund
        final_status, reason = determine_status(ctx)
        rule_code = ctx.get("matched_rule_code")
        o["final_status"]        = final_status
        o["final_status_reason"] = reason
        o["matched_rule_code"]   = rule_code
        o["classification_settlement_amount"] = settlement_label_amount_map.get(key, Z)
        o["is_special_case"]     = False
        o["abnormal_reason"]     = None
        o["refund_goods_amount"] = refund
        o["classification_label"] = STATUS_LABELS.get(final_status)
        if rule_code:
            rule_code_counts[rule_code] += 1
        final_orders.append(o)
        status_counts[final_status] += 1
        reason_counts[reason] += 1

    stats = {
        "paid": status_counts.get("paid", 0),
        "refunded": status_counts.get("refunded", 0),
        "pending": status_counts.get("pending_settlement", 0),
        "unclassified": status_counts.get(None, 0),
        "reason_counts": dict(reason_counts),
        "rule_code_counts": dict(rule_code_counts),
        "cost_matched": cost_matched,
        "cost_unmatched": cost_unmatched,
        "cost_unmatched_samples": cost_unmatched_samples,
        "order_count": len(final_orders),
        "settlement_matched": settlement_matched,
        "settlement_unmatched": settlement_unmatched,
        "settlement_income_sum": settlement_income_sum,
        "settlement_refund_sum": settlement_refund_sum,
        "receivable_sum": receivable_sum,
        "freight_matched_sum": freight_matched_sum,
        "freight_matched_cnt": freight_matched_cnt,
        "fund_refund_matched": fund_refund_matched,
        "fund_refund_matched_sum": fund_refund_matched_sum,
    }
    return final_orders, stats


async def generate_report_sync(
    db: AsyncSession, batch_id: int, mode: str = "loose", on_progress=None,
    task_id: int | None = None,
) -> dict:
    """
    销售月报生成核心逻辑（同步耗时逻辑，业务规则保持不变）。
    on_progress: 可选 async 回调 (progress:int, step:str, message:str)，用于异步任务上报进度。
    task_id: 用于写业务计算日志（fin_sales_monthly_calc_logs）。
    重型解析/判定通过 asyncio.to_thread 移出事件循环，避免阻塞任务状态轮询。
    """
    import time as _time

    async def _p(pct: int, step: str, msg: str) -> None:
        if on_progress is not None:
            try:
                await on_progress(pct, step, msg)
            except Exception:
                logger.warning("[generate] 进度回调失败", exc_info=True)

    async def _log(level, stage, message, store=None, detail=None,
                   row_count=None, success_count=None, failed_count=None, duration_ms=None,
                   field=None, field_name=None):
        await add_calc_log(batch_id, task_id, store, level, stage,
                           CALC_STAGE_NAMES.get(stage, stage), message,
                           detail_json=detail, row_count=row_count,
                           success_count=success_count, failed_count=failed_count,
                           duration_ms=duration_ms, field=field, field_name=field_name)

    await _p(5, "precheck", "正在进行生成前检查")
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise ValueError("批次不存在")
    _ensure_not_deleted(b)
    if b.status == "locked":
        raise ValueError("批次已锁定，请先解锁")

    # 取已上传活跃文件
    q = await db.execute(
        select(FinSalesMonthlyImportFile).where(
            FinSalesMonthlyImportFile.batch_id == batch_id,
            FinSalesMonthlyImportFile.is_active.is_(True),
            FinSalesMonthlyImportFile.detect_status == "detected",
        )
    )
    active_files = q.scalars().all()
    if not active_files:
        raise ValueError("批次内没有任何已识别的上传文件")

    # 按店铺分组
    from collections import defaultdict
    store_files: dict[str, dict[str, FinSalesMonthlyImportFile]] = defaultdict(dict)
    for f in active_files:
        store_files[f.store_name][f.file_type] = f

    # 保留已有手工补录科目，重新生成时只替换自动计算字段。
    old_reports = (await db.execute(
        select(FinSalesMonthlyShopReport).where(FinSalesMonthlyShopReport.batch_id == batch_id)
    )).scalars().all()
    manual_by_store = {
        row.store_name: {
            "customer_service_fee": row.customer_service_fee,
            "management_fee": row.management_fee,
            "tax_fee": row.tax_fee,
            "order_claim": row.order_claim,
            "deposit_recharge": row.deposit_recharge,
            "rebate_amount": row.rebate_amount,
            "other_deduction": row.other_deduction,
            "salary_fee": row.salary_fee,
            "rent_utility_fee": row.rent_utility_fee,
            "other_monthly_expense": row.other_monthly_expense,
        }
        for row in old_reports
    }

    # 读取 settings
    pkg_cost    = await svc_settings.get_package_unit_cost(db)
    gds_cost    = await svc_settings.get_goods_loss_unit_cost(db)
    return_loss = await svc_settings.is_return_loss_enabled(db)

    # strict 模式校验
    warnings: list[str] = []
    if mode == "strict":
        missing_stores = []
        for store_name, files in store_files.items():
            missing = [t for t in REQUIRED_FILE_TYPES if t not in files]
            if missing:
                missing_stores.append(
                    f"{store_name} 缺少必传文件：{'、'.join(FILE_TYPE_CN.get(t, t) for t in missing)}"
                )
        if missing_stores:
            raise ValueError("严格模式校验失败：\n" + "\n".join(missing_stores))

    # 重新生成前清空本批次旧计算日志，避免新旧两次运行的日志混在一起
    try:
        async with AsyncSessionLocal() as _logdb:
            await _logdb.execute(
                delete(FinSalesMonthlyCalcLog).where(FinSalesMonthlyCalcLog.batch_id == batch_id)
            )
            await _logdb.commit()
    except Exception:
        logger.warning("[generate] 清空旧计算日志失败（不影响主流程）", exc_info=True)

    await _log("info", "start",
               f"开始生成 {b.month} 销售月报，规则版本：{determine_status_version}，"
               f"模式={'宽松' if mode != 'strict' else '严格'}，共 {len(store_files)} 个店铺。"
               f"上传表类型：店铺订单/结算账单/资金账单/发货订单/运费/广告费/商品成本表（7类，已停用售后单与独立运费险表）；"
               f"应收金额=商品单价×数量-商家实际承担优惠+运费",
               detail={"rules_version": determine_status_version, "month": b.month, "mode": mode,
                       "store_count": len(store_files), "file_types": ALL_FILE_TYPES,
                       "deprecated_file_types": DEPRECATED_FILE_TYPES,
                       "receivable_formula": "商品单价×商品数量 - 商家实际承担优惠金额 + 运费",
                       "stores": list(store_files.keys())[:30]})

    normal_shop_rows: list[dict] = []
    abnormal_stores: list[str] = []
    merged_orders: list[dict] = []
    store_extras: dict[str, dict] = {}   # 每店原始解析合计，供一致性校验记录 raw_value

    await _p(10, "load_files", "正在读取上传文件")
    total_stores = max(1, len(store_files))
    # 每个文件类型 → 解析步骤名/中文消息
    _STEP_BY_TYPE = {
        "order":             ("parse_orders", "正在解析店铺订单"),
        "shipping_order":    ("parse_shipping_order", "正在解析发货订单"),
        "settlement":        ("parse_settlement", "正在解析结算账单"),
        "after_sale":        ("parse_after_sale", "正在解析售后单"),
        "product_cost":      ("parse_cost", "正在匹配商品成本"),
        "fund":              ("parse_settlement", "正在解析资金账单"),
        "freight":           ("parse_settlement", "正在解析运费"),
        "freight_insurance": ("parse_settlement", "正在解析运费险"),
        "ad_cost":           ("parse_settlement", "正在解析广告费"),
    }

    for _store_idx, (store_name, files) in enumerate(store_files.items()):
        # 店铺级进度：10 → 85 线性推进
        _base = 10 + int(75 * _store_idx / total_stores)
        await _p(_base, "parse_orders",
                 f"正在处理店铺 {_store_idx + 1}/{total_stores}：{store_name}")
        # 检查必传文件
        missing_req = [t for t in REQUIRED_FILE_TYPES if t not in files]
        if missing_req and mode == "strict":
            abnormal_stores.append(store_name)
            warnings.append(
                f"{store_name} 缺少必传文件：{'、'.join(FILE_TYPE_CN.get(t, t) for t in missing_req)}"
            )
            continue
        if missing_req:
            warnings.append(
                f"{store_name} 缺少{'、'.join(FILE_TYPE_CN.get(t, t) for t in missing_req)}，相关费用按 0 处理"
            )
        if "product_cost" in missing_req:
            warnings.append(f"{store_name} 缺少商品成本表，成本按 0 处理，毛利和净利润不可信")

        if "product_cost" not in files:
            await _log("warn", "parse_cost",
                       f"{store_name} 缺少商品成本表，宽松模式下商品成本按 0 处理，毛利和净利润不可信",
                       store=store_name)
        if "shipping_order" not in files:
            await _log("warn", "parse_shipping_order",
                       f"{store_name} 缺少发货订单，宽松模式下实际销售成本按 0 处理",
                       store=store_name)

        # 解析各文件（新版 7 类；重型解析放线程池）
        settlement_map: dict[tuple[str, str], dict] = {}
        settlement_label_amount_map: dict[tuple[str, str], Decimal] = {}
        settlement_diag: dict = {}
        cost_map: dict[str, Decimal] = {}
        freight_data: dict    = {}
        fund_agg: dict        = {}
        ad_cost_amt           = Decimal("0")
        orders: list[dict]    = []
        order_diag: dict      = {}
        shipping_by_product: dict[str, dict] = {}
        shipping_diag: dict   = {}
        cost_total_codes      = 0
        ad_cost_col = freight_col = None

        for file_type, file_rec in files.items():
            if file_type in DEPRECATED_FILE_TYPES:
                continue  # 售后单/独立运费险表：新版停用，不参与计算
            _st, _msg = _STEP_BY_TYPE.get(file_type, ("parse_orders", "正在解析文件"))
            await _p(_base, _st, f"{_msg}：{store_name}")
            _t0 = _time.monotonic()
            try:
                parsed = await asyncio.to_thread(
                    importers.parse_one_for_generate,
                    file_type, file_rec.file_path, file_rec.original_filename,
                    b.month, store_name,
                )
            except Exception as e:
                logger.warning(f"[generate] {store_name} 解析 {file_type} 失败: {e}", exc_info=True)
                cn = FILE_TYPE_CN.get(file_type, file_type)
                emsg = importers.humanize_parse_error(str(e))
                warnings.append(f"{store_name} {cn}解析失败：{emsg}")
                await _log("error", "load_files", f"{store_name} {cn}解析失败：{emsg}",
                           store=store_name)
                continue
            _dur = int((_time.monotonic() - _t0) * 1000)

            if file_type == "order":
                orders = parsed.get("orders", []) or []
                order_diag = parsed.get("diag", {}) or {}
                d = order_diag
                m_s, m_e = importers._month_range(b.month)
                await _log(
                    "info" if orders else "warn", "parse_orders",
                    f"店铺订单共读取 {d.get('total_rows', 0)} 行，识别发货时间列为「"
                    f"{d.get('ship_time_column_name') or '未识别'}」，按 {b.month} 筛选后保留 "
                    f"{d.get('rows_in_selected_month', 0)} 行",
                    store=store_name,
                    detail={
                        "filter": f"{m_s:%Y-%m-%d %H:%M:%S} <= 发货时间 < {m_e:%Y-%m-%d %H:%M:%S}",
                        "total_rows": d.get("total_rows"),
                        "ship_time_column": d.get("ship_time_column_name"),
                        "ship_time_parse_success_count": d.get("ship_time_parse_success_count"),
                        "ship_time_parse_failed_count": d.get("ship_time_parse_failed_count"),
                        "ship_time_blank_count": d.get("ship_time_blank_count"),
                        "rows_in_month": d.get("rows_in_selected_month"),
                        "min_ship_time": d.get("min_ship_time"),
                        "max_ship_time": d.get("max_ship_time"),
                        "parse_failed_samples": d.get("parse_failed_samples"),
                        "clean_rule": "主订单号/子订单号/商品编码去除前后空格、全角空格、换行、制表符、不可见字符",
                        "express_rule": "快递信息列拆分为快递单号 + 快递名称，用于算运费",
                        "receivable_rule": "应收金额 = 商品单价×商品数量 - 商家实际承担优惠金额 + 运费",
                    },
                    row_count=d.get("total_rows"),
                    success_count=d.get("rows_in_selected_month"),
                    failed_count=d.get("ship_time_parse_failed_count"), duration_ms=_dur,
                )
            elif file_type == "shipping_order":
                shipping_by_product = parsed.get("shipping_by_product", {}) or {}
                shipping_diag = parsed.get("diag", {}) or {}
                sd = shipping_diag
                await _log(
                    "info" if shipping_by_product else "warn", "parse_shipping_order",
                    f"发货订单共读取 {sd.get('total_rows', 0)} 行，识别发货日期列为「"
                    f"{sd.get('ship_date_column') or '未识别'}」，按 {b.month} 筛选后保留 "
                    f"{sd.get('rows_in_month', 0)} 行，聚合 {sd.get('product_code_count', 0)} 个商品编码",
                    store=store_name,
                    detail={
                        "ship_date_column": sd.get("ship_date_column"), "month": b.month,
                        "filter": sd.get("filter"), "total_rows": sd.get("total_rows"),
                        "rows_in_month": sd.get("rows_in_month"),
                        "date_parse_failed_count": sd.get("date_parse_failed_count"),
                        "product_code_count": sd.get("product_code_count"),
                    },
                    row_count=sd.get("total_rows"), success_count=sd.get("rows_in_month"),
                    failed_count=sd.get("date_parse_failed_count"), duration_ms=_dur,
                )
                await _log(
                    "info", "parse_shipping_order",
                    f"实发数量聚合：发货数量 {sd.get('shipped_quantity_total', 0)} - "
                    f"实退数量 {sd.get('returned_quantity_total', 0)} = "
                    f"实发数量 {sd.get('net_shipped_quantity_total', 0)}",
                    store=store_name,
                    detail={
                        "formula": sd.get("formula"), "product_code_count": sd.get("product_code_count"),
                        "shipped_quantity_total": sd.get("shipped_quantity_total"),
                        "returned_quantity_total": sd.get("returned_quantity_total"),
                        "net_shipped_quantity_total": sd.get("net_shipped_quantity_total"),
                    },
                )
            elif file_type == "settlement":
                settlement_map = parsed.get("settlement_map", {}) or {}
                settlement_label_amount_map = parsed.get("settlement_label_amount_map", {}) or {}
                settlement_diag = parsed.get("diag", {}) or {}
                inc = _cdec(settlement_diag.get("payment_total"))
                ref = _cdec(settlement_diag.get("refund_total"))
                commission = _cdec(settlement_diag.get("talent_commission_total"))
                await _log("info", "parse_settlement",
                           f"结算账单按结算时间筛选当月后保留 {settlement_diag.get('rows_in_month', 0)} 行，"
                           f"当月联合键 {len(settlement_map)} 个，标签全日期联合键 "
                           f"{len(settlement_label_amount_map)} 个，收款 {inc}，退款 {ref}，达人佣金 {commission}",
                           store=store_name,
                           detail=settlement_diag,
                           row_count=settlement_diag.get("total_rows"),
                           success_count=settlement_diag.get("rows_in_month"),
                           failed_count=settlement_diag.get("date_parse_failed_count"), duration_ms=_dur)
            elif file_type == "product_cost":
                cost_map = parsed.get("cost_map", {}) or {}
                cost_total_codes = len(cost_map)
                await _log("info", "parse_cost",
                           f"商品成本表共 {len(cost_map)} 个商品编码",
                           store=store_name, detail={"cost_codes": len(cost_map)},
                           row_count=len(cost_map), duration_ms=_dur)
            elif file_type == "fund":
                fund_agg = parsed.get("fund_agg", {}) or {}
                await _log("info", "parse_settlement",
                           f"资金账单(动账时间当月)：消费者赔付 {fund_agg.get('consumer_compensation', 0)}，"
                           f"小额打款 {fund_agg.get('small_payment', 0)}，运费险 {fund_agg.get('freight_insurance', 0)}，"
                           f"平台其他费用 {fund_agg.get('platform_other_fee', 0)}",
                           store=store_name,
                        detail={k: (str(v) if isinstance(v, Decimal) else v)
                                   for k, v in fund_agg.items()
                                   if k not in ("freight_insurance_by_sub", "fund_refund_by_sub")},
                           row_count=fund_agg.get("rows_in_month", 0), duration_ms=_dur)
            elif file_type == "freight":
                freight_data = parsed.get("freight", {}) or {}
                frd = parsed.get("diag", {}) or {}
                freight_col = freight_data.get("amount_column")
                await _log("info", "load_files",
                           f"运费表：金额列「{freight_data.get('amount_column')}」总额 {freight_data.get('total')}，"
                           f"匹配键 {frd.get('match_by')}（子订单 {len(freight_data.get('by_sub', {}))} / 运单 {len(freight_data.get('by_waybill', {}))}）",
                           store=store_name, detail=frd,
                           row_count=freight_data.get("rows", 0), duration_ms=_dur)
            elif file_type == "ad_cost":
                amt = parsed.get("amount", Decimal("0"))
                amt_diag = parsed.get("diag", {}) or {}
                ad_cost_amt = amt
                ad_cost_col = amt_diag.get("amount_column")
                await _log("info", "load_files",
                           f"广告费总额：{amt}（金额列：{amt_diag.get('amount_column') or '未知'}）",
                           store=store_name, detail=amt_diag, duration_ms=_dur)

        if "order" not in files:
            warnings.append(f"{store_name}: 无订单文件，跳过")
            await _log("error", "parse_orders", f"{store_name}：无订单文件，跳过", store=store_name)
            continue
        if not orders:
            d = order_diag or {}
            col = d.get("ship_time_column_name") or "未识别"
            lines = [
                f"{store_name}：订单表解析为空，{d.get('message', '')}".rstrip("，"),
                f"  - 已识别发货时间列：{col}",
                f"  - 订单总行数：{d.get('total_rows', 0)}",
                f"  - 发货时间解析成功：{d.get('ship_time_parse_success_count', 0)}",
                f"  - 发货时间解析失败：{d.get('ship_time_parse_failed_count', 0)}",
                f"  - {b.month} 月内订单数：{d.get('rows_in_selected_month', 0)}",
                f"  - 最小发货时间：{d.get('min_ship_time') or '-'}",
                f"  - 最大发货时间：{d.get('max_ship_time') or '-'}",
            ]
            samples = d.get("parse_failed_samples") or []
            if samples:
                lines.append(f"  - 解析失败样例：{('、'.join(samples))}")
            warnings.append("\n".join(lines))
            continue

        await _p(_base, "classify_orders", f"正在判定订单状态：{store_name}")
        # 合并(结算收款/退款+成本+运费匹配) + 新版状态判定（重型循环放线程池）
        final_orders, stats = await asyncio.to_thread(
            _merge_and_classify, orders, settlement_map, cost_map, freight_data,
            fund_agg.get("fund_refund_by_sub", {}), settlement_label_amount_map,
        )
        merged_orders.extend(final_orders)

        actual_product_cost, shipping_cost_stats = calculator.calculate_actual_sales_cost(
            shipping_by_product, cost_map
        )
        if shipping_cost_stats["cost_missing_count"]:
            warnings.append(
                f"{store_name} 发货订单有 {shipping_cost_stats['cost_missing_count']} 个商品编码未匹配成本价"
            )

        order_subs = {o.get("sub_order_no") for o in final_orders if o.get("sub_order_no")}
        insurance_raw_total = _cdec(fund_agg.get("freight_insurance"))
        insurance_stats = {
            "raw_amount": insurance_raw_total,
            "matched_count": int(fund_agg.get("freight_insurance_with_sub_count", 0) or 0),
            "unmatched_count": int(fund_agg.get("freight_insurance_without_sub_count", 0) or 0),
            "matched_amount": insurance_raw_total,
            "unmatched_amount": Decimal("0"),
        }

        # 商品成本匹配日志
        await _log("info" if stats["cost_unmatched"] == 0 else "warn", "parse_cost",
                   f"商品成本匹配：成功 {stats['cost_matched']} 行，失败 {stats['cost_unmatched']} 行",
                   store=store_name,
                   detail={"cost_matched": stats["cost_matched"],
                           "cost_unmatched": stats["cost_unmatched"],
                           "cost_unmatched_samples": stats["cost_unmatched_samples"]},
                   success_count=stats["cost_matched"], failed_count=stats["cost_unmatched"])
        await _log(
            "info" if shipping_cost_stats["cost_missing_count"] == 0 else "warn", "parse_cost",
            f"实际销售成本=Σ(实发数量×成本价)={actual_product_cost}，"
            f"商品编码匹配成功 {shipping_cost_stats['cost_matched_count']} 个，"
            f"匹配失败 {shipping_cost_stats['cost_missing_count']} 个",
            store=store_name, detail=shipping_cost_stats,
            success_count=shipping_cost_stats["cost_matched_count"],
            failed_count=shipping_cost_stats["cost_missing_count"],
        )

        # 三类互斥订单标签命中日志
        rcc = stats["rule_code_counts"]
        await _log("info", "classify_orders",
                   f"三类标签完成：已收款 {stats['paid']}，已退款 {stats['refunded']}，"
                   f"待结算 {stats['pending']}，未发货/未命中 {stats['unclassified']}",
                   store=store_name,
                   detail={
                       "rules_version": determine_status_version,
                       "status_counts": {"已收款": stats["paid"], "已退款": stats["refunded"],
                                         "待结算": stats["pending"], "未分类": stats["unclassified"]},
                       "rule_code_counts": rcc,
                       "paid_rule_1_count": rcc.get("paid_rule_1", 0),
                       "paid_rule_2_count": rcc.get("paid_rule_2", 0),
                       "paid_rule_3_count": rcc.get("paid_rule_3", 0),
                       "refunded_rule_1_count": rcc.get("refunded_rule_1", 0),
                       "refunded_rule_2_count": rcc.get("refunded_rule_2", 0),
                       "pending_rule_1_count": rcc.get("pending_rule_1", 0),
                       "pending_rule_2_count": rcc.get("pending_rule_2", 0),
                       "evaluation_order": "发货时间 → 订单状态 → 售后状态 → 金额判断",
                       "settlement_matched": stats["settlement_matched"],
                       "settlement_unmatched": stats["settlement_unmatched"],
                       "fund_refund_matched": stats["fund_refund_matched"],
                       "fund_refund_matched_sum": stats["fund_refund_matched_sum"],
                   },
                   row_count=len(final_orders),
                   success_count=(stats["paid"] + stats["refunded"] + stats["pending"]),
                   failed_count=stats["unclassified"])

        # 聚合月报（新版费用来源：资金账单 + 运费表匹配 + 广告费）
        await _p(_base, "aggregate_shop", f"正在汇总店铺月报：{store_name}")
        manual = manual_by_store.get(store_name, {})
        agg = calculator.aggregate_shop_report(
            orders=final_orders,
            actual_product_cost=actual_product_cost,
            platform_service_fee=_cdec(settlement_diag.get("platform_service_fee_total")),
            talent_commission=_cdec(settlement_diag.get("talent_commission_total")),
            freight_insurance=insurance_raw_total,
            platform_other_fee=_cdec(fund_agg.get("platform_other_fee")),
            compensation_amount=_cdec(fund_agg.get("consumer_compensation")),
            small_payment_amount=_cdec(fund_agg.get("small_payment")),
            ad_cost=ad_cost_amt,
            **manual,
            package_unit_cost=pkg_cost,
            goods_loss_unit_cost=gds_cost,
            return_loss_enabled=return_loss,
        )
        agg["store_name"] = store_name
        normal_shop_rows.append(agg)

        # 店铺月报汇总日志（新版公式）
        await _log("success", "aggregate_shop",
                   f"{store_name} 月报汇总：发货订单 {agg['shipped_order_count']}，发货金额(商品金额) {agg['shipped_amount']}，"
                   f"实际销售额 {agg['actual_sales_amount']}，实际销售成本 {agg['actual_product_cost']}，"
                   f"费用合计 {agg['total_fee']}，净利润 {agg['net_profit']}",
                   store=store_name,
                   detail={
                       "rules_version": determine_status_version,
                       "shipped_order_count": agg["shipped_order_count"],
                       "shipped_amount": agg["shipped_amount"],
                       "shipped_amount_formula": "发货金额 = 当月发货订单商品金额汇总",
                       "actual_sales_amount": agg["actual_sales_amount"],
                       "actual_sales_rule": "实际销售额 = 发货金额 - 发货后退款金额",
                       "actual_product_cost": agg["actual_product_cost"],
                       "actual_product_cost_rule": "实际销售成本 = Σ(发货订单按商品编码汇总的实发数量 × 成本价)",
                       "platform_service_fee": agg["platform_service_fee"],
                       "platform_service_fee_rule": "结算账单按结算时间筛选当月、按子订单匹配汇总后取绝对值",
                       "talent_commission": agg["talent_commission"],
                       "talent_commission_rule": "结算账单达人佣金按子订单匹配汇总后取绝对值",
                       "freight_amount": agg["freight_amount"],
                       "freight_rule": "运费表按快递单号左连接后逐发货订单行汇总",
                       "freight_insurance": agg["freight_insurance"],
                       "freight_insurance_rule": "资金账单按动账时间筛选当月后汇总运费险总额",
                       "platform_other_fee": agg["platform_other_fee"],
                       "platform_other_fee_rule": "资金账单 偏远地区物流服务+权益保险+上门取件运费",
                       "compensation_amount": agg["compensation_amount"],
                       "small_payment_amount": agg["small_payment_amount"],
                       "total_fee": agg["total_fee"],
                       "total_fee_formula": "成本 + 平台服务费 + 达人佣金 + 退货损耗 + 运费 + 包装费 + 运费险 + 消费者赔付 + 小额打款 + 平台其他费用 + 客服 + 推广 + 管理费用 + 税务",
                       "gross_profit": agg["gross_profit"],
                       "gross_profit_formula": "实际销售额 - 费用合计 + 订单理赔 - 货值损耗",
                       "net_profit": agg["net_profit"],
                       "net_profit_formula": "毛利 + 返佣返点 - 保证金充值 - 其他扣减项",
                   })

        # 一致性校验所需 4 类值
        psf_written = agg["platform_service_fee"]
        ref_written = agg["after_ship_refund_amount"]
        store_extras[store_name] = {
            "platform_service_fee": {"raw": psf_written, "matched": psf_written, "included": psf_written},
            "after_ship_refund_amount": {"raw": ref_written, "matched": ref_written, "included": ref_written},
            "talent_commission": {"raw": agg["talent_commission"], "matched": agg["talent_commission"], "included": agg["talent_commission"]},
        }

        # ── 字段级计算日志（新版关键字段） ──
        await _p(_base, "aggregate_shop", f"正在记录字段级计算日志：{store_name}")
        for fl in _build_business_field_logs(
            agg, stats, settlement_diag, shipping_cost_stats, fund_agg,
        ):
            await _log(fl["level"], fl["stage"], f"{store_name} {fl['message']}",
                       store=store_name, detail=fl["detail"],
                       row_count=fl.get("row_count"), success_count=fl.get("success_count"),
                       failed_count=fl.get("failed_count"),
                       field=fl["field"], field_name=fl["field_name"])
        # 关键异常进 warnings
        if agg["actual_sales_order_count"] > 0 and agg["actual_sales_amount"] == 0:
            warnings.append(f"{store_name} 实销单量>0 但实际销售额=0（发货金额与发货后退款金额相等）")
        if agg["actual_sales_order_count"] > 0 and agg["actual_product_cost"] == 0:
            warnings.append(f"{store_name} 存在实销订单但实际销售成本=0（发货订单无当月实发数量，或商品编码未匹配成本价）")
        if stats.get("order_count") and stats.get("settlement_matched", 0) / max(1, stats["order_count"]) < 0.8:
            warnings.append(f"{store_name} 结算账单子订单匹配率低于80%")
        _fr_total = _cdec((freight_data or {}).get("total"))
        if _fr_total > 0 and stats["freight_matched_sum"] == 0:
            warnings.append(
                f"{store_name} 运费表有金额（{_fr_total}）但按子订单/快递单号匹配本月订单 0 单，运费计 0；"
                f"请检查运费表与订单的快递单号是否同一快递公司/同一单号口径"
            )

    # ── 写库前金额异常校验：拦截编号被识别成金额（防 NumericValueOutOfRange）──
    await _p(94, "validate_report_values", "正在校验月报金额是否异常")
    all_anomalies: list[dict] = []
    for row in normal_shop_rows:
        anomalies = calculator.validate_shop_report_values(row, row.get("store_name"))
        for a in anomalies:
            cn = FILE_TYPE_CN.get(a["field"], a["field"])
            await _log("error", "validate_report_values",
                       f"{a.get('store_name')} {a['field']} 金额异常：{a['value']}，"
                       f"疑似将编号列识别为金额列（阈值 {a['threshold']}）",
                       store=a.get("store_name"), detail=a)
        all_anomalies.extend(anomalies)
    if all_anomalies:
        b.status = "failed"
        await db.commit()
        lines = []
        for a in all_anomalies[:8]:
            field_cn = {
                "freight_insurance": "运费险金额", "total_fee": "费用合计",
                "gross_profit": "毛利", "net_profit": "净利润",
            }.get(a["field"], a["field"])
            lines.append(
                f"- {a.get('store_name')} {field_cn}异常：{a['value']}，"
                f"该值疑似订单号/保单号/运单号，不是金额"
            )
        raise ValueError(
            "生成月报失败：检测到金额字段异常（疑似把编号识别成了金额），已阻断写入。\n"
            "请检查运费险表的金额列识别是否正确（表头应含 运费险金额/保费/保险费/扣费金额）。\n"
            "具体：\n" + "\n".join(lines)
        )

    await _p(95, "write_reports", "正在写入月报结果")
    # 仅在新结果已完整计算并通过金额校验后替换旧结果；删除和写入处于同一事务。
    # 后续任一步失败都会回滚，保留上一次成功生成的月报。
    await db.execute(
        delete(FinSalesMonthlyShopReport).where(
            FinSalesMonthlyShopReport.batch_id == batch_id
        )
    )
    await db.execute(
        delete(FinSalesMonthlyOrderDetail).where(
            FinSalesMonthlyOrderDetail.batch_id == batch_id
        )
    )

    # 批量写入 shop reports
    shop_objs = []
    for row in normal_shop_rows:
        shop_objs.append(FinSalesMonthlyShopReport(
            batch_id=batch_id, month=b.month, store_name=row["store_name"],
            shipped_order_count=row["shipped_order_count"],
            shipped_amount=row["shipped_amount"],
            refund_order_count=row["refund_order_count"],
            after_ship_refund_amount=row["after_ship_refund_amount"],
            before_ship_refund_amount=row["before_ship_refund_amount"],
            after_settlement_refund_amount=row["after_settlement_refund_amount"],
            actual_sales_amount=row["actual_sales_amount"],
            actual_sales_order_count=row["actual_sales_order_count"],
            actual_sales_order_completed=row["actual_sales_order_completed"],
            paid_sales_amount=row["paid_sales_amount"],
            avg_order_amount=row["avg_order_amount"],
            actual_product_cost=row["actual_product_cost"],
            platform_service_fee=row["platform_service_fee"],
            talent_commission=row["talent_commission"],
            return_loss=row["return_loss"],
            freight_amount=row["freight_amount"],
            package_fee=row["package_fee"],
            freight_insurance=row["freight_insurance"],
            compensation_amount=row["compensation_amount"],
            platform_other_fee=row.get("platform_other_fee", Decimal("0")),
            customer_service_fee=row["customer_service_fee"],
            ad_cost=row["ad_cost"],
            management_fee=row["management_fee"],
            tax_fee=row["tax_fee"],
            total_fee=row["total_fee"],
            order_claim=row["order_claim"],
            goods_loss=row["goods_loss"],
            gross_profit=row["gross_profit"],
            deposit_recharge=row["deposit_recharge"],
            rebate_amount=row["rebate_amount"],
            other_deduction=row["other_deduction"],
            net_profit=row["net_profit"],
            net_profit_rate=row["net_profit_rate"],
            total_refund_rate=row["total_refund_rate"],
            before_ship_refund_rate=row["before_ship_refund_rate"],
            after_ship_refund_rate=row["after_ship_refund_rate"],
            after_settlement_refund_rate=row["after_settlement_refund_rate"],
            small_payment_amount=row.get("small_payment_amount", Decimal("0")),
            salary_fee=row.get("salary_fee", Decimal("0")),
            rent_utility_fee=row.get("rent_utility_fee", Decimal("0")),
            other_monthly_expense=row.get("other_monthly_expense", Decimal("0")),
        ))
    db.add_all(shop_objs)

    # 批量写入订单明细
    order_objs = []
    for o in merged_orders:
        order_objs.append(FinSalesMonthlyOrderDetail(
            batch_id=batch_id,
            month=b.month,
            store_name=o.get("store_name", ""),
            main_order_no=o.get("main_order_no"),
            sub_order_no=o.get("sub_order_no"),
            product_code=o.get("product_code"),
            product_name=o.get("product_name"),
            sku_name=o.get("sku_name"),
            quantity=int(o.get("quantity") or 0),
            ship_time=o.get("ship_time"),
            order_status=o.get("order_status"),
            after_sale_status=o.get("after_sale_status"),
            order_pay_amount=o.get("order_pay_amount", Decimal("0")),
            platform_discount=o.get("platform_discount", Decimal("0")),
            talent_discount=o.get("talent_discount", Decimal("0")),
            receivable_amount=o.get("receivable_amount", Decimal("0")),
            product_amount=o.get("product_amount", Decimal("0")),
            order_freight=o.get("order_freight", Decimal("0")),
            settlement_income=o.get("settlement_income", Decimal("0")),
            settlement_amount_total=o.get("settlement_amount_total", Decimal("0")),
            settlement_difference=o.get("settlement_difference", Decimal("0")),
            fund_refund_amount=o.get("fund_refund_amount", Decimal("0")),
            platform_service_fee=o.get("platform_service_fee", Decimal("0")),
            talent_commission=o.get("talent_commission", Decimal("0")),
            refund_goods_amount=o.get("refund_goods_amount", Decimal("0")),
            product_cost_price=o.get("product_cost_price", Decimal("0")),
            product_cost_amount=o.get("product_cost_amount", Decimal("0")),
            express_company=o.get("express_company"),
            express_no=o.get("express_no"),
            matched_freight=o.get("matched_freight", Decimal("0")),
            final_status=o.get("final_status"),
            final_status_reason=o.get("final_status_reason"),
            is_special_case=bool(o.get("is_special_case")),
            abnormal_reason=o.get("abnormal_reason"),
        ))
    # 分批写入订单明细（每 BATCH_SIZE 行 flush，不逐行 commit）
    for i in range(0, len(order_objs), BATCH_SIZE):
        db.add_all(order_objs[i:i + BATCH_SIZE])
        await db.flush()

    await _log("info", "write_reports",
               f"写入月报结果：店铺月报 {len(shop_objs)} 行，订单明细 {len(order_objs)} 行（分批每 {BATCH_SIZE} 行）",
               row_count=len(order_objs), success_count=len(shop_objs))

    b.store_count = len(normal_shop_rows)
    if len(normal_shop_rows) == 0:
        b.status = "failed"
        reason_parts = [w for w in warnings if w]
        detail = "\n".join(f"- {w}" for w in reason_parts[:8]) if reason_parts else "- 无法生成任何店铺月报"
        await _log("error", "finish", "生成失败：没有任何店铺产生有效结果")
        raise ValueError(
            "生成月报失败，没有任何店铺产生有效结果，请检查订单表、结算账单、商品成本表是否已上传并解析成功。\n"
            f"具体原因：\n{detail}"
        )
    b.status = "completed"
    await db.commit()

    # ── 月报结果一致性校验：重新从库读回，比对“计算值 vs 落表值” ──
    await _p(98, "validate_report_consistency", "正在校验月报结果一致性")
    inconsistent_stores = await _validate_report_consistency(
        db, batch_id, normal_shop_rows, store_extras, _log
    )
    if inconsistent_stores:
        warnings.append(
            f"以下店铺月报字段一致性校验未通过（计算值≠落表值）：{'、'.join(inconsistent_stores)}，请检查字段映射"
        )

    await _p(100, "finish", "生成完成")

    pending_count  = sum(1 for o in merged_orders if o.get("final_status") == "pending_settlement")
    abnormal_count = sum(1 for o in merged_orders if o.get("final_status") == "abnormal")
    total_sales    = sum((r["actual_sales_amount"] for r in normal_shop_rows), Decimal("0"))
    total_profit   = sum((r["net_profit"] for r in normal_shop_rows), Decimal("0"))
    total_shipped  = sum(r["shipped_order_count"] for r in normal_shop_rows)

    message = (
        f"已生成 {len(normal_shop_rows)} 个店铺月报，共 {len(merged_orders)} 笔订单"
    )
    if abnormal_stores:
        message += f"；{len(abnormal_stores)} 个店铺因缺必传文件进入异常"

    await _log("success", "finish", message,
               detail={"store_count": len(normal_shop_rows), "order_count": len(merged_orders),
                       "pending_settlement_count": pending_count, "abnormal_count": abnormal_count})

    return {
        "success": True,
        "message": message,
        "warnings": warnings,
        "summary": {
            "store_count": len(normal_shop_rows),
            "shipped_order_count": total_shipped,
            "actual_sales_amount": total_sales,
            "net_profit": total_profit,
            "pending_settlement_count": pending_count,
            "abnormal_count": abnormal_count,
        },
    }


async def get_shop_reports(
    db: AsyncSession, batch_id: int
) -> list[FinSalesMonthlyShopReport]:
    q = await db.execute(
        select(FinSalesMonthlyShopReport).where(
            FinSalesMonthlyShopReport.batch_id == batch_id
        ).order_by(FinSalesMonthlyShopReport.store_name)
    )
    return q.scalars().all()


async def update_shop_report_manual(
    db: AsyncSession, batch_id: int, store_name: str, values: dict
) -> FinSalesMonthlyShopReport:
    """更新无数据源手工科目，并立即重算费用、毛利和净利润。"""
    batch = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not batch:
        raise ValueError("批次不存在")
    _ensure_not_deleted(batch)
    if batch.status == "locked":
        raise ValueError("批次已锁定，不能修改手工科目")
    q = await db.execute(select(FinSalesMonthlyShopReport).where(
        FinSalesMonthlyShopReport.batch_id == batch_id,
        FinSalesMonthlyShopReport.store_name == store_name,
    ))
    report = q.scalars().first()
    if not report:
        raise ValueError("店铺月报不存在，请先生成月报")
    allowed = {
        "customer_service_fee", "management_fee", "tax_fee", "order_claim",
        "rebate_amount", "deposit_recharge", "other_deduction",
    }
    for field in allowed:
        if field in values:
            setattr(report, field, _cdec(values[field]))
    report.total_fee = sum((_cdec(getattr(report, field, 0)) for field in (
        "actual_product_cost", "platform_service_fee", "talent_commission", "return_loss",
        "freight_amount", "package_fee", "freight_insurance", "compensation_amount",
        "small_payment_amount", "platform_other_fee", "customer_service_fee", "ad_cost",
        "management_fee", "tax_fee",
    )), Decimal("0"))
    report.gross_profit = (
        _cdec(report.actual_sales_amount) - _cdec(report.total_fee)
        + _cdec(report.order_claim) - _cdec(report.goods_loss)
    )
    report.net_profit = (
        _cdec(report.gross_profit) + _cdec(report.rebate_amount)
        - _cdec(report.deposit_recharge) - _cdec(report.other_deduction)
    )
    report.net_profit_rate = (
        _cdec(report.net_profit) / _cdec(report.actual_sales_amount)
        if _cdec(report.actual_sales_amount) > 0 else Decimal("0")
    )
    report.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(report)
    return report


async def get_order_details(
    db: AsyncSession,
    batch_id: int,
    *,
    final_status: str | None = None,
    store_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int, dict]:
    q = select(FinSalesMonthlyOrderDetail).where(
        FinSalesMonthlyOrderDetail.batch_id == batch_id
    )
    if final_status:
        q = q.where(FinSalesMonthlyOrderDetail.final_status == final_status)
    if store_name:
        q = q.where(FinSalesMonthlyOrderDetail.store_name.ilike(f"%{store_name}%"))

    from sqlalchemy import func
    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar() or 0

    # status counts
    cnt_q = await db.execute(
        select(
            FinSalesMonthlyOrderDetail.final_status,
            func.count(FinSalesMonthlyOrderDetail.id)
        ).where(
            FinSalesMonthlyOrderDetail.batch_id == batch_id
        ).group_by(FinSalesMonthlyOrderDetail.final_status)
    )
    status_counts = {row[0]: row[1] for row in cnt_q.all()}

    if limit == 0:
        return [], total, status_counts

    q = q.order_by(FinSalesMonthlyOrderDetail.id).limit(limit).offset(offset)
    items = (await db.execute(q)).scalars().all()
    return list(items), total, status_counts


# ─── 导出包装 ──────────────────────────────────────────────

def export_report_excel(month: str, rows, batch_name: str = "") -> bytes:
    return _export_report_excel(month=month, shop_rows=rows, batch_name=batch_name)


def export_pending_excel(month: str, rows) -> bytes:
    return _export_pending_excel(month=month, order_rows=rows)


def export_abnormal_excel(month: str, rows) -> bytes:
    return _export_abnormal_excel(month=month, order_rows=rows)


def export_normal_excel(month: str, rows) -> bytes:
    return _export_normal_excel(month=month, order_rows=rows)


async def get_orders_by_statuses(
    db: AsyncSession, batch_id: int, statuses: list[str], limit: int = 2_000_000
) -> list:
    """按 final_status 列表取订单明细（用于导出正常订单，排除 abnormal）。"""
    q = (
        select(FinSalesMonthlyOrderDetail)
        .where(
            FinSalesMonthlyOrderDetail.batch_id == batch_id,
            FinSalesMonthlyOrderDetail.final_status.in_(statuses),
        )
        .order_by(FinSalesMonthlyOrderDetail.id)
        .limit(limit)
    )
    return (await db.execute(q)).scalars().all()


# ─── 异步生成任务 ─────────────────────────────────────────────
_TASK_RUNNING_STATUSES = ("pending", "running")


def _jsonify(obj):
    """把 Decimal/datetime 等转成 JSON 可序列化结构，供 result_json 存储。"""
    from decimal import Decimal as _D
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, _D):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


async def get_generate_task(db: AsyncSession, task_id: int) -> FinSalesMonthlyGenerateTask | None:
    task = await db.get(FinSalesMonthlyGenerateTask, task_id)
    if task and _is_orphaned_generate_task(task):
        _set_orphaned_generate_task_failed(task)
        b = await db.get(FinSalesMonthlyReportBatch, task.batch_id)
        if b and b.status == "processing":
            b.status = "failed"
            b.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(task)
    return task


async def get_latest_generate_task(
    db: AsyncSession, batch_id: int
) -> FinSalesMonthlyGenerateTask | None:
    q = await db.execute(
        select(FinSalesMonthlyGenerateTask)
        .where(FinSalesMonthlyGenerateTask.batch_id == batch_id)
        .order_by(FinSalesMonthlyGenerateTask.id.desc())
        .limit(1)
    )
    task = q.scalars().first()
    if task and _is_orphaned_generate_task(task):
        _set_orphaned_generate_task_failed(task)
        b = await db.get(FinSalesMonthlyReportBatch, task.batch_id)
        if b and b.status == "processing":
            b.status = "failed"
            b.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(task)
    return task


async def _get_running_task(
    db: AsyncSession, batch_id: int
) -> FinSalesMonthlyGenerateTask | None:
    q = await db.execute(
        select(FinSalesMonthlyGenerateTask)
        .where(
            FinSalesMonthlyGenerateTask.batch_id == batch_id,
            FinSalesMonthlyGenerateTask.status.in_(_TASK_RUNNING_STATUSES),
        )
        .order_by(FinSalesMonthlyGenerateTask.id.desc())
        .limit(1)
    )
    return q.scalars().first()


def _is_orphaned_generate_task(task: FinSalesMonthlyGenerateTask) -> bool:
    if task.status not in _TASK_RUNNING_STATUSES:
        return False
    task_time = task.started_at or task.created_at
    return bool(task_time and task_time < _PROCESS_STARTED_AT)


def _set_orphaned_generate_task_failed(task: FinSalesMonthlyGenerateTask) -> None:
    now = datetime.utcnow()
    task.status = "failed"
    task.current_step = "failed"
    task.message = "服务重启，原生成任务已自动结束"
    task.error_message = "生成任务所属服务进程已重启，请重新生成月报"
    task.finished_at = now
    task.updated_at = now


async def start_generate_task(
    db: AsyncSession, batch_id: int, *, mode: str = "loose", user: str | None = None
) -> dict:
    """创建生成任务并把批次置为 processing；不在请求内同步执行生成。"""
    b = await db.get(FinSalesMonthlyReportBatch, batch_id)
    if not b:
        raise LookupError("销售月报批次不存在")
    _ensure_not_deleted(b)
    if b.status == "locked":
        raise ValueError("批次已锁定，请先解锁")

    # PostgreSQL 事务级咨询锁：同一批次的并发启动请求串行执行，防止创建两个任务。
    await db.execute(
        text("SELECT pg_advisory_xact_lock(CAST(:lock_key AS bigint))"),
        {"lock_key": 736270000000 + batch_id},
    )

    # 并发控制：已有进行中的任务 → 不重复启动
    running = await _get_running_task(db, batch_id)
    if running and _is_orphaned_generate_task(running):
        _set_orphaned_generate_task_failed(running)
        running = None
    if running:
        return {
            "ok": False,
            "message": "该批次已有生成任务正在执行，请勿重复点击",
            "task_id": running.id,
            "status": running.status,
            "started": False,
        }

    task = FinSalesMonthlyGenerateTask(
        batch_id=batch_id,
        status="pending",
        progress=0,
        current_step="pending",
        message="任务已创建，等待执行",
        created_by=(str(user) if user is not None else None),
    )
    db.add(task)
    b.status = "processing"
    b.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return {
        "ok": True,
        "message": "月报生成任务已启动",
        "task_id": task.id,
        "status": "pending",
        "started": True,
    }


async def _update_task(task_id: int, **fields) -> None:
    """用独立 session 更新任务行，避免干扰生成事务。"""
    async with AsyncSessionLocal() as db:
        t = await db.get(FinSalesMonthlyGenerateTask, task_id)
        if not t:
            return
        for k, v in fields.items():
            setattr(t, k, v)
        t.updated_at = datetime.utcnow()
        await db.commit()


async def run_generate_task(task_id: int, batch_id: int, mode: str = "loose") -> None:
    """后台任务入口：执行生成逻辑并持续上报进度。自带 DB session。"""
    await _update_task(
        task_id, status="running", progress=1,
        current_step="precheck", message="正在进行生成前检查",
        started_at=datetime.utcnow(), error_message=None,
    )

    async def _on_progress(pct: int, step: str, msg: str) -> None:
        await _update_task(task_id, progress=pct, current_step=step, message=msg)

    try:
        async with AsyncSessionLocal() as db:
            result = await generate_report_sync(
                db, batch_id, mode=mode, on_progress=_on_progress, task_id=task_id
            )
        await _update_task(
            task_id, status="success", progress=100,
            current_step="finish", message=result.get("message") or "生成成功",
            error_message=None, result_json=_jsonify(result),
            finished_at=datetime.utcnow(),
        )
    except Exception as e:
        logger.error(f"[run_generate_task] task={task_id} batch={batch_id} 生成失败: {e}", exc_info=True)
        err = importers.humanize_parse_error(str(e)) if "\n" not in str(e) else str(e)
        await add_calc_log(batch_id, task_id, None, "error", "finish", "生成结束",
                           f"生成失败：{err.splitlines()[0] if err else '未知错误'}")
        await _update_task(
            task_id, status="failed",
            current_step="failed", message="生成失败",
            error_message=err, finished_at=datetime.utcnow(),
        )
        # 保证批次状态落到 failed（generate_report_sync 内部异常可能未改状态）
        try:
            async with AsyncSessionLocal() as db2:
                b = await db2.get(FinSalesMonthlyReportBatch, batch_id)
                if b and b.status == "processing":
                    b.status = "failed"
                    b.updated_at = datetime.utcnow()
                    await db2.commit()
        except Exception:
            logger.error("[run_generate_task] 批次状态回写 failed 失败", exc_info=True)


# ─── 计算日志 ─────────────────────────────────────────────────
# 阶段编码 → 中文名（财务可读）
CALC_STAGE_NAMES = {
    "start":            "开始生成",
    "load_files":       "读取上传文件",
    "parse_orders":     "解析店铺订单",
    "parse_shipping_order": "解析发货订单",
    "clean_fields":     "清洗订单字段",
    "split_express":    "拆分快递信息",
    "parse_settlement": "解析结算账单",
    "parse_after_sale": "解析售后单",
    "parse_cost":       "匹配商品成本",
    "classify_orders":  "判定订单状态",
    "aggregate_shop":   "汇总店铺月报",
    "validate_report_values": "月报结果写入前校验",
    "write_reports":    "写入月报结果",
    "validate_report_consistency": "月报结果一致性校验",
    "finish":           "生成结束",
    "export_normal_orders": "导出正常订单",
}

# 字段级日志阶段名（field_calc_<字段> → 字段计算-中文名）
_FIELD_CN = {
    "shipped_order_count": "发货订单数", "shipped_amount": "发货金额",
    "refund_order_count": "退款订单数", "after_ship_refund_amount": "发货后退款金额",
    "actual_sales_amount": "实际销售额", "actual_sales_order_count": "实销单量",
    "avg_order_amount": "客单价", "actual_product_cost": "实际销售成本",
    "platform_service_fee": "平台服务费", "talent_commission": "达人佣金",
    "return_loss": "退货损耗", "freight_amount": "运费", "package_fee": "包装费",
    "freight_insurance": "运费险", "platform_other_fee": "平台其他费用",
    "compensation_amount": "消费者赔付", "small_payment_amount": "小额打款",
    "ad_cost": "推广消耗", "goods_loss": "货值损耗",
    "total_fee": "费用合计", "gross_profit": "毛利", "net_profit": "净利润",
    "net_profit_rate": "净利润率",
}
for _f, _cn in _FIELD_CN.items():
    CALC_STAGE_NAMES["field_calc_" + _f] = "字段计算-" + _cn

# 一致性校验字段
_CONSISTENCY_INT_FIELDS = ["shipped_order_count", "refund_order_count", "actual_sales_order_count",
                           "actual_sales_order_completed"]
_CONSISTENCY_DEC_FIELDS = [
    "shipped_amount", "after_ship_refund_amount", "before_ship_refund_amount",
    "after_settlement_refund_amount", "actual_sales_amount", "paid_sales_amount", "avg_order_amount",
    "actual_product_cost", "platform_service_fee", "talent_commission", "return_loss",
    "freight_amount", "package_fee", "freight_insurance", "ad_cost", "total_fee",
    "goods_loss", "gross_profit", "net_profit", "net_profit_rate", "total_refund_rate",
    "before_ship_refund_rate", "after_ship_refund_rate", "after_settlement_refund_rate",
]
# 易错字段：记录 raw / matched / included / written 四类值
_FOUR_VALUE_FIELDS = [
    "platform_service_fee", "talent_commission", "after_ship_refund_amount",
    "actual_sales_amount", "shipped_amount", "total_fee", "gross_profit", "net_profit",
]


def _cdec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


async def _validate_report_consistency(db, batch_id, calc_rows, store_extras, _log) -> list[str]:
    """重新从 fin_sales_monthly_shop_reports 读回落表值，与计算值逐字段比对。
    返回不一致的店铺名列表。金额允许 0.01 误差，数量必须完全一致。"""
    written_q = await db.execute(
        select(FinSalesMonthlyShopReport).where(
            FinSalesMonthlyShopReport.batch_id == batch_id
        )
    )
    written_by_store: dict[str, FinSalesMonthlyShopReport] = {}
    for r in written_q.scalars().all():
        written_by_store[r.store_name] = r  # 唯一约束保证一店一行

    inconsistent: list[str] = []
    for agg in calc_rows:
        store = agg.get("store_name")
        wr = written_by_store.get(store)
        if wr is None:
            inconsistent.append(store)
            await _log("error", "validate_report_consistency",
                       f"{store} 未在月报结果表中找到落表记录", store=store)
            continue
        checks: dict = {}
        bad: list[str] = []
        for f in _CONSISTENCY_INT_FIELDS:
            c = int(agg.get(f) or 0)
            w = int(getattr(wr, f, 0) or 0)
            ok = c == w
            checks[f] = {"calculated": c, "written": w, "consistent": ok}
            if not ok:
                bad.append(f)
        for f in _CONSISTENCY_DEC_FIELDS:
            c = _cdec(agg.get(f))
            w = _cdec(getattr(wr, f, 0))
            ok = (c - w).copy_abs() <= Decimal("0.01")
            checks[f] = {"calculated": str(c), "written": str(w), "consistent": ok}
            if not ok:
                bad.append(f)
        # 四类值（raw / matched / included / written）
        four: dict = {}
        for f in _FOUR_VALUE_FIELDS:
            ex = (store_extras.get(store, {}) or {}).get(f, {})
            included = _cdec(agg.get(f))
            raw = _cdec(ex.get("raw", included))
            matched = _cdec(ex.get("matched", included))
            inc = _cdec(ex.get("included", included))
            w = _cdec(getattr(wr, f, 0))
            diff_reason = None
            if (raw - inc).copy_abs() > Decimal("0.01"):
                diff_reason = "原始解析合计含未匹配本月发货订单/非本店子订单，按业务口径仅计入匹配后金额"
            four[f] = {
                "raw_value": str(raw),
                "matched_value": str(matched),
                "included_value": str(inc),
                "written_value": str(w),
                "rule": _FIELD_RULES.get(f),
                "difference_reason": diff_reason,
            }
        if bad:
            inconsistent.append(store)
            await _log("error", "validate_report_consistency",
                       f"{store} 月报关键字段一致性校验未通过：{('、'.join(bad))}（计算值≠落表值，请检查字段映射）",
                       store=store, failed_count=len(bad),
                       detail={"store_name": store, "checks": checks, "four_values": four})
        else:
            await _log("success", "validate_report_consistency",
                       f"{store} 月报关键字段一致性校验通过（{len(checks)} 个字段计算值=落表值）",
                       store=store, success_count=len(checks),
                       detail={"store_name": store, "checks": checks, "four_values": four})
    return inconsistent


_FIELD_RULES = {
    "platform_service_fee": "结算账单平台服务费按子订单编号匹配店铺订单后汇总并取绝对值",
    "talent_commission": "结算账单达人佣金按子订单编号匹配后汇总并取绝对值",
    "after_ship_refund_amount": "发货后退款金额 = Σ已退款子订单(商品金额-结算账单全日期净结算金额)",
    "actual_sales_amount": "实际销售额 = 发货金额 - 发货后退款金额",
    "shipped_amount": "当月发货订单商品金额汇总",
    "total_fee": "成本 + 平台服务费 + 达人佣金 + 退货损耗 + 运费 + 包装费 + 运费险 + 赔付 + 客服 + 推广 + 税务",
    "gross_profit": "实际销售额 - 费用合计 + 订单理赔 - 货值损耗",
    "net_profit": "毛利 + 返佣返点 - 保证金充值 - 其他扣减项",
}


def _build_field_logs(agg: dict, stats: dict, raws: dict) -> list[dict]:
    """
    根据汇总结果 + 阶段统计构建“字段级计算日志”条目（每字段一条，含 4 类值/公式/原因/样例）。
    仅字段级/汇总级，绝不逐行。返回 list，每项含 level/stage/field/field_name/message/detail/计数。
    """
    def s(v):  # Decimal/数值 → 字符串
        return str(v if v is not None else 0)

    logs: list[dict] = []

    def add(field, field_name, message, detail, level="info",
            row_count=None, success_count=None, failed_count=None):
        detail = {"field": field, "field_name": field_name, **detail}
        logs.append({"field": field, "field_name": field_name,
                     "stage": "field_calc_" + field, "level": level,
                     "message": message, "detail": detail,
                     "row_count": row_count, "success_count": success_count,
                     "failed_count": failed_count})

    order_cnt = stats.get("order_count", 0)
    paid_cnt = agg.get("actual_sales_order_count", 0)

    # 发货订单数
    add("shipped_order_count", "发货订单数",
        f"发货订单数 = 当月发货主订单编号去重 = {agg['shipped_order_count']}",
        {"source_tables": ["店铺订单"], "source_fields": ["主订单编号", "发货时间"],
         "filter_rule": "发货时间在当月", "match_key": "主订单编号去重",
         "formula": "当月发货主订单编号去重数量", "raw_count": order_cnt,
         "included_value": s(agg["shipped_order_count"]), "written_value": s(agg["shipped_order_count"])},
        row_count=order_cnt, success_count=agg["shipped_order_count"])

    # 发货金额
    si = stats.get("shipped_income_sum", Decimal("0"))
    sr = stats.get("shipped_refund_sum", Decimal("0"))
    lvl = "info"
    add("shipped_amount", "发货金额",
        f"发货金额 = 当月发货订单商品金额汇总 = {agg['shipped_amount']}",
        {"source_tables": ["店铺订单"], "source_fields": ["商品金额", "发货时间"],
         "formula": "当月发货订单商品金额汇总", "settlement_income_sum": s(si),
         "refund_goods_amount_sum": s(sr), "raw_value": s(agg["shipped_amount"]),
         "included_value": s(agg["shipped_amount"]), "written_value": s(agg["shipped_amount"]),
         "difference_reason": None},
        level=lvl)

    # 退款订单数
    add("refund_order_count", "退款订单数",
        f"退款订单数 = 已退款订单主订单编号去重 = {agg['refund_order_count']}",
        {"source_tables": ["店铺订单", "售后单"], "formula": "已退款订单主订单编号去重数量",
         "refunded_order_count": stats.get("refunded", 0),
         "included_value": s(agg["refund_order_count"]), "written_value": s(agg["refund_order_count"])},
        success_count=agg["refund_order_count"])

    # 发货后退款金额
    ref_raw = raws.get("after_sale_refund_raw", Decimal("0"))
    add("after_ship_refund_amount", "发货后退款金额",
        f"发货后退款金额 = 退款金额汇总 = {agg['after_ship_refund_amount']}（售后退商品金额原始合计 {ref_raw}）",
        {"source_tables": ["售后单"], "source_fields": ["退商品金额", "子订单编号"],
         "match_key": "子订单编号", "formula": "退款金额(售后退商品金额按子订单匹配后)汇总",
         "raw_value": s(ref_raw), "matched_value": s(agg["after_ship_refund_amount"]),
         "included_value": s(agg["after_ship_refund_amount"]), "written_value": s(agg["after_ship_refund_amount"]),
         "after_sale_matched": stats.get("after_sale_matched", 0),
         "difference_reason": ("原始合计含非当月/未匹配本月订单的售后记录，仅计入匹配订单部分"
                               if (ref_raw - agg["after_ship_refund_amount"]).copy_abs() > Decimal("0.01") else None)})

    # 实际销售额（重点）
    paid_income = stats.get("paid_income_sum", Decimal("0"))
    asa = agg["actual_sales_amount"]
    asa_zero_warn = (paid_cnt > 0 and asa == 0)
    add("actual_sales_amount", "实际销售额",
        f"实际销售额 = 已收款订单收款金额汇总 = {asa}",
        {"source_tables": ["店铺订单", "结算账单"],
         "source_fields": ["收款金额(店铺订单结算金额列)", "子订单号", "订单状态", "售后状态"],
         "filter_rule": "仅统计已收款(paid)订单", "match_key": "子订单编号",
         "formula": "已收款订单收款金额汇总",
         "settlement_income_sum_all": s(si),
         "settlement_pos_orders": stats.get("income_pos_cnt", 0),
         "settlement_matched_orders": stats.get("settlement_matched", 0),
         "paid_order_count": paid_cnt,
         "paid_income_sum": s(paid_income),
         "paid_income_zero_count": stats.get("paid_income_zero", 0),
         "paid_income_positive_count": stats.get("paid_income_pos", 0),
         "paid_unmatched_settlement_count": stats.get("paid_settle_unmatched", 0),
         "raw_value": s(si), "matched_value": s(paid_income),
         "included_value": s(asa), "written_value": s(asa),
         "uncounted_reasons": {
             "收款金额为0": stats.get("paid_income_zero", 0),
             "子订单未匹配结算账单": stats.get("paid_settle_unmatched", 0),
         },
         "difference_reason": ("实销单量>0 但实际销售额=0：已收款订单的收款金额(店铺订单结算金额列)全部为0/为空；"
                               "当前收款金额取自店铺订单结算金额列，未从结算账单收入合计>0取数"
                               if asa_zero_warn else None),
         "samples": stats.get("paid_settle_unmatched_samples", [])},
        level=("warn" if asa_zero_warn else "info"),
        row_count=paid_cnt, success_count=stats.get("paid_income_pos", 0),
        failed_count=stats.get("paid_income_zero", 0))

    # 实销单量
    add("actual_sales_order_count", "实销单量",
        f"实销单量 = 已收款与待结算订单主订单编号合并去重 = {paid_cnt}",
        {"source_tables": ["店铺订单"], "formula": "已收款与待结算订单主订单编号合并去重数量",
         "paid_order_count": paid_cnt, "included_value": s(paid_cnt), "written_value": s(paid_cnt)},
        success_count=paid_cnt)

    # 客单价
    avg = agg["avg_order_amount"]
    add("avg_order_amount", "客单价",
        f"客单价 = 实际销售额({asa}) / 实销单量({paid_cnt}) = {avg}",
        {"formula": "实际销售额 / 实销单量", "actual_sales_amount": s(asa),
         "actual_sales_order_count": paid_cnt, "included_value": s(avg), "written_value": s(avg),
         "difference_reason": ("客单价=0 因为实际销售额=0" if (paid_cnt > 0 and avg == 0) else None)},
        level=("warn" if (paid_cnt > 0 and avg == 0) else "info"))

    # 实际销售货值（重点）
    apc = agg["actual_product_cost"]
    apc_zero_warn = (paid_cnt > 0 and apc == 0)
    add("actual_product_cost", "实际销售货值",
        f"实际销售货值 = 已收款订单 成本价 × 商品数量 汇总 = {apc}",
        {"source_tables": ["店铺订单", "商品成本表"], "source_fields": ["商品编码", "成本价", "商品数量"],
         "match_key": "商品编码", "formula": "已收款订单 成本价 × 有效商品数量 汇总（数量=2且退款=商品金额时按1计）",
         "paid_order_count": paid_cnt,
         "paid_qty_sum": stats.get("paid_qty_sum", 0),
         "paid_effective_qty_sum": stats.get("paid_eff_qty_sum", 0),
         "qty2_adjusted_count": stats.get("paid_qty2_adjust", 0),
         "cost_matched_count": stats.get("paid_cost_matched", 0),
         "cost_missing_count": stats.get("paid_cost_missing", 0),
         "cost_total_codes": raws.get("cost_total_codes", 0),
         "raw_value": s(apc), "matched_value": s(apc),
         "included_value": s(apc), "written_value": s(apc),
         "difference_reason": ("存在实销订单但实际销售货值=0：商品编码未匹配到商品成本表（匹配成功0）或成本价为0，"
                               "请检查商品成本表是否上传、商品编码格式是否一致、成本价字段是否识别"
                               if apc_zero_warn else None),
         "unmatched_product_code_samples": stats.get("paid_cost_missing_samples", [])},
        level=("warn" if apc_zero_warn else "info"),
        row_count=paid_cnt, success_count=stats.get("paid_cost_matched", 0),
        failed_count=stats.get("paid_cost_missing", 0))

    # 平台服务费
    psf_raw = raws.get("settlement_psf_raw", Decimal("0"))
    add("platform_service_fee", "平台服务费",
        f"平台服务费 = 结算账单平台服务费按子订单匹配后汇总 = {agg['platform_service_fee']}（原始合计 {psf_raw}）",
        {"source_tables": ["结算账单"], "source_fields": ["平台服务费", "子订单号"], "match_key": "子订单编号",
         "formula": "结算账单平台服务费按子订单编号匹配店铺订单后汇总并取绝对值",
         "raw_value": s(psf_raw), "matched_value": s(stats.get("platform_fee_matched_sum", 0)),
         "included_value": s(agg["platform_service_fee"]), "written_value": s(agg["platform_service_fee"]),
         "settlement_matched_orders": stats.get("settlement_matched", 0),
         "difference_reason": ("原始合计含未匹配本月订单的结算记录，仅计入匹配部分"
                               if (psf_raw - agg["platform_service_fee"]).copy_abs() > Decimal("0.01") else None)})

    # 达人佣金
    tc_raw = raws.get("settlement_tc_raw", Decimal("0"))
    add("talent_commission", "达人佣金",
        f"达人佣金 = 结算账单达人佣金按子订单匹配后汇总 = {agg['talent_commission']}（原始合计 {tc_raw}）",
        {"source_tables": ["结算账单"], "source_fields": ["达人佣金", "子订单号"], "match_key": "子订单编号",
         "formula": "结算账单达人佣金按子订单编号匹配后汇总并取绝对值",
         "raw_value": s(tc_raw), "matched_value": s(stats.get("talent_matched_sum", 0)),
         "included_value": s(agg["talent_commission"]), "written_value": s(agg["talent_commission"])})

    # 退货损耗
    add("return_loss", "退货损耗",
        f"退货损耗 = 退款订单数 = {agg['return_loss']}",
        {"formula": "退款订单数", "refund_order_count": agg["refund_order_count"],
         "included_value": s(agg["return_loss"]), "written_value": s(agg["return_loss"])})

    # 运费 / 包装费 / 运费险 / 推广 / 货值损耗
    add("freight_amount", "运费",
        f"运费 = 运费表总金额 = {agg['freight_amount']}",
        {"source_tables": ["运费"], "formula": "运费表金额列汇总",
         "amount_column": raws.get("freight_col"),
         "included_value": s(agg["freight_amount"]), "written_value": s(agg["freight_amount"])})
    add("package_fee", "包装费",
        f"包装费 = 发货订单数({agg['shipped_order_count']}) × 0.5 = {agg['package_fee']}",
        {"formula": "发货订单数 × 0.5", "shipped_order_count": agg["shipped_order_count"],
         "included_value": s(agg["package_fee"]), "written_value": s(agg["package_fee"])})
    add("freight_insurance", "运费险",
        f"运费险 = 运费险表总金额 = {agg['freight_insurance']}",
        {"source_tables": ["运费险"], "formula": "运费险表金额列汇总",
         "amount_column": raws.get("freight_insurance_col"),
         "included_value": s(agg["freight_insurance"]), "written_value": s(agg["freight_insurance"])})
    add("ad_cost", "推广消耗",
        f"推广消耗 = 广告费表总金额 = {agg['ad_cost']}",
        {"source_tables": ["广告费"], "formula": "广告费表金额列汇总",
         "amount_column": raws.get("ad_cost_col"),
         "included_value": s(agg["ad_cost"]), "written_value": s(agg["ad_cost"])})
    add("goods_loss", "货值损耗",
        f"货值损耗 = 发货订单数({agg['shipped_order_count']}) × 1 = {agg['goods_loss']}",
        {"formula": "发货订单数 × 1", "included_value": s(agg["goods_loss"]), "written_value": s(agg["goods_loss"])})

    # 费用合计
    add("total_fee", "费用合计",
        f"费用合计 = {agg['total_fee']}",
        {"formula": "成本 + 平台服务费 + 达人佣金 + 退货损耗 + 运费 + 包装费 + 运费险 + 赔付 + 小额打款 + 客服 + 推广 + 工资 + 房租水电 + 其他支出 + 税费",
         "components": {
             "实际销售货值": s(agg["actual_product_cost"]),
             "平台服务费": s(agg["platform_service_fee"]),
             "达人佣金": s(agg["talent_commission"]),
             "退货损耗": s(agg["return_loss"]),
             "运费": s(agg["freight_amount"]),
             "包装费": s(agg["package_fee"]),
             "运费险": s(agg["freight_insurance"]),
             "赔付": s(agg["compensation_amount"]),
             "小额打款": s(agg.get("small_payment_amount", 0)),
             "外包客服费用": s(agg["customer_service_fee"]),
             "推广消耗": s(agg["ad_cost"]),
             "人员工资": s(agg.get("salary_fee", 0)),
             "房租水电": s(agg.get("rent_utility_fee", 0)),
             "本月其他支出": s(agg.get("other_monthly_expense", 0)),
             "税费": s(agg["tax_fee"]),
         },
         "included_value": s(agg["total_fee"]), "written_value": s(agg["total_fee"])})

    # 毛利
    add("gross_profit", "毛利",
        f"毛利 = 实际销售额({asa}) - 费用合计({agg['total_fee']}) + 订单理赔({agg['order_claim']}) - 货值损耗({agg['goods_loss']}) = {agg['gross_profit']}",
        {"formula": "实际销售额 - 费用合计 + 订单理赔 - 货值损耗",
         "actual_sales_amount": s(asa), "total_fee": s(agg["total_fee"]),
         "order_claim": s(agg["order_claim"]), "goods_loss": s(agg["goods_loss"]),
         "included_value": s(agg["gross_profit"]), "written_value": s(agg["gross_profit"])})

    # 净利润
    add("net_profit", "净利润",
        f"净利润 = 毛利({agg['gross_profit']}) + 返佣返点({agg['rebate_amount']}) - 保证金充值({agg['deposit_recharge']}) - 其他扣减项({agg['other_deduction']}) = {agg['net_profit']}",
        {"formula": "毛利 + 返佣返点 - 保证金充值 - 其他扣减项",
         "gross_profit": s(agg["gross_profit"]), "rebate_amount": s(agg["rebate_amount"]),
         "deposit_recharge": s(agg["deposit_recharge"]), "other_deduction": s(agg["other_deduction"]),
         "included_value": s(agg["net_profit"]), "written_value": s(agg["net_profit"])})

    # 净利润率
    add("net_profit_rate", "净利润率",
        f"净利润率 = 净利润 / 实际销售额 = {agg['net_profit_rate']}",
        {"formula": "净利润 / 实际销售额（实际销售额为0时为0）",
         "net_profit": s(agg["net_profit"]), "actual_sales_amount": s(asa),
         "included_value": s(agg["net_profit_rate"]), "written_value": s(agg["net_profit_rate"])})

    return logs


async def add_calc_log(
    batch_id: int, task_id: int | None, store_name: str | None,
    level: str, stage: str, stage_name: str | None, message: str,
    detail_json: dict | None = None,
    row_count: int | None = None, success_count: int | None = None,
    failed_count: int | None = None, duration_ms: int | None = None,
    field: str | None = None, field_name: str | None = None,
) -> None:
    """
    写一条业务计算日志（独立 session，失败不影响主任务）。
    只写阶段汇总 + 字段级 + 少量样例，绝不逐行写订单，避免日志爆炸。
    """
    try:
        async with AsyncSessionLocal() as db:
            db.add(FinSalesMonthlyCalcLog(
                batch_id=batch_id, task_id=task_id, store_name=store_name,
                level=level, stage=stage,
                stage_name=stage_name or CALC_STAGE_NAMES.get(stage, stage),
                message=message,
                detail_json=_jsonify(detail_json) if detail_json else None,
                row_count=row_count, success_count=success_count,
                failed_count=failed_count, duration_ms=duration_ms,
                field=field, field_name=field_name,
            ))
            await db.commit()
    except Exception:
        logger.warning("[calc_log] 写计算日志失败（不影响主任务）", exc_info=True)


async def get_calc_logs(
    db: AsyncSession, batch_id: int, *,
    task_id: int | None = None, store_name: str | None = None,
    level: str | None = None, stage: str | None = None, keyword: str | None = None,
    field: str | None = None,
    page: int = 1, page_size: int = 50,
) -> tuple[list, int]:
    q = select(FinSalesMonthlyCalcLog).where(FinSalesMonthlyCalcLog.batch_id == batch_id)
    if task_id:
        q = q.where(FinSalesMonthlyCalcLog.task_id == task_id)
    if store_name:
        q = q.where(FinSalesMonthlyCalcLog.store_name == store_name)
    if level:
        q = q.where(FinSalesMonthlyCalcLog.level == level)
    if stage:
        q = q.where(FinSalesMonthlyCalcLog.stage == stage)
    if field:
        q = q.where(FinSalesMonthlyCalcLog.field == field)
    if keyword:
        q = q.where(FinSalesMonthlyCalcLog.message.ilike(f"%{keyword}%"))
    from sqlalchemy import func
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    q = q.order_by(FinSalesMonthlyCalcLog.id.asc()).limit(page_size).offset((page - 1) * page_size)
    items = (await db.execute(q)).scalars().all()
    return list(items), total
