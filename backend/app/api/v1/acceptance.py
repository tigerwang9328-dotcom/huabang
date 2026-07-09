"""Task 8 验收相关 API：导入验收 / 字段映射 / 指标对账 / 三天看板"""
import io
import json
import uuid
import logging
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from pydantic import BaseModel
import pandas as pd

from app.core.database import get_db
from app.api.v1.deps import require_permission
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.baison_import import FIELD_MAPPING

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/acceptance", tags=["验收管理"])

ALLOWED_TYPES_EXT = {
    "sales_order", "sales_detail", "return_order", "return_detail",
    "inventory", "member", "employee", "store", "product", "sku",
    "finance_expense", "finance_cash", "transfer",
}


# ── 1. 导入前验收（不入库，只校验）──────────────────────────────────────
@router.post("/validate-import", response_model=ApiResponse)
async def validate_import(
    data_type: str = Form(...),
    file: UploadFile = File(...),
    field_mapping_json: Optional[str] = Form(None, description="JSON字符串：{excel列名: 系统字段名}"),
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """上传Excel/CSV，执行11维校验，不写入数据库。返回完整验收报告。"""
    if data_type not in ALLOWED_TYPES_EXT:
        return ApiResponse.fail(f"不支持的数据类型: {data_type}")

    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in [".xlsx", ".xls", ".csv"]):
        return ApiResponse.fail("仅支持 .xlsx .xls .csv 格式")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        return ApiResponse.fail("文件不能超过50MB")

    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        return ApiResponse.fail(f"文件解析失败: {str(e)[:200]}")

    # 应用字段映射（优先使用参数，否则查DB模板）
    mapping = None
    if field_mapping_json:
        try:
            mapping = json.loads(field_mapping_json)
        except Exception:
            return ApiResponse.fail("field_mapping_json 不是有效JSON")
    else:
        tmpl_r = await db.execute(text("""
            SELECT excel_to_system FROM app.app_field_mapping_template
            WHERE data_type = :dt AND template_name = 'default' AND is_active = TRUE
            ORDER BY updated_at DESC LIMIT 1
        """), {"dt": data_type})
        row = tmpl_r.fetchone()
        if row:
            mapping = row[0]

    batch_no = f"VAL_{data_type.upper()}_{date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"

    from app.services.validation_service import ImportValidationService
    svc = ImportValidationService()
    result = svc.validate(df, data_type, batch_no, field_mapping=mapping)

    if "error" in result:
        return ApiResponse.fail(result["error"])

    # 写入验收日志（截取error_detail前50条）
    detail_for_db = json.dumps(result["error_detail"][:50], ensure_ascii=False, default=str)
    await db.execute(text("""
        INSERT INTO log.log_import_validation
            (batch_no, data_type, filename, total_rows, success_rows, duplicate_rows,
             error_rows, missing_required_count, type_error_count, biz_error_count,
             error_detail, allow_etl, block_report, data_quality_score, operator_id)
        VALUES (:bn, :dt, :fn, :total, :succ, :dup, :err,
                :miss, :type_e, :biz_e, :detail::jsonb,
                :allow_etl, :block, :score, :uid)
    """), {
        "bn": batch_no, "dt": data_type, "fn": filename,
        "total": result["total_rows"], "succ": result["success_rows"],
        "dup": result["duplicate_rows"], "err": result["error_rows"],
        "miss": result["missing_required_count"], "type_e": result["type_error_count"],
        "biz_e": result["biz_error_count"], "detail": detail_for_db,
        "allow_etl": result["allow_etl"], "block": result["block_report"],
        "score": result["data_quality_score"], "uid": current_user.id,
    })
    await db.commit()

    return ApiResponse.ok(data={
        **{k: v for k, v in result.items() if k != "error_detail"},
        "error_detail_count": len(result["error_detail"]),
        "error_download_url": f"/api/v1/acceptance/error-download/{batch_no}",
    }, message=f"验收完成：质量分{result['data_quality_score']}分，{'✅ 允许ETL' if result['allow_etl'] else '❌ 不允许ETL'}")


# ── 2. 错误明细下载 ─────────────────────────────────────────────────────
@router.get("/error-download/{batch_no}")
async def download_error_detail(
    batch_no: str,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """下载指定批次的错误明细CSV"""
    r = await db.execute(text("""
        SELECT data_type, error_detail FROM log.log_import_validation WHERE batch_no = :bn
    """), {"bn": batch_no})
    row = r.fetchone()
    if not row:
        return ApiResponse.fail(f"批次 {batch_no} 不存在")

    from app.services.validation_service import ImportValidationService
    svc = ImportValidationService()
    csv_bytes = svc.generate_error_csv({"error_detail": row[1] or []})

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename=errors_{batch_no}.csv"},
    )


# ── 3. 字段映射模板保存/读取 ────────────────────────────────────────────
class MappingTemplateBody(BaseModel):
    data_type: str
    template_name: str = "default"
    excel_to_system: dict
    source_columns: list = []


@router.post("/mapping/save", response_model=ApiResponse)
async def save_mapping_template(
    body: MappingTemplateBody,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """保存字段映射模板（同data_type+template_name覆盖更新）"""
    valid_count = sum(1 for v in body.excel_to_system.values() if v)
    coverage = round(valid_count / max(len(body.excel_to_system), 1) * 100, 1)
    await db.execute(text("""
        INSERT INTO app.app_field_mapping_template
            (data_type, template_name, excel_to_system, source_columns, coverage_rate, created_by, updated_by)
        VALUES (:dt, :tn, :mapping::jsonb, :cols::jsonb, :cov, :uid, :uid)
        ON CONFLICT (data_type, template_name) DO UPDATE SET
            excel_to_system = EXCLUDED.excel_to_system,
            source_columns  = EXCLUDED.source_columns,
            coverage_rate   = EXCLUDED.coverage_rate,
            updated_by      = EXCLUDED.updated_by,
            updated_at      = NOW()
    """), {
        "dt": body.data_type, "tn": body.template_name,
        "mapping": json.dumps(body.excel_to_system, ensure_ascii=False),
        "cols": json.dumps(body.source_columns, ensure_ascii=False),
        "cov": coverage, "uid": current_user.id,
    })
    await db.commit()
    return ApiResponse.ok(data={"coverage_rate": coverage}, message="字段映射模板已保存")


@router.get("/mapping/{data_type}", response_model=ApiResponse)
async def get_mapping_template(
    data_type: str,
    template_name: str = "default",
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """读取已保存的字段映射模板（含系统默认映射作为初始值）"""
    r = await db.execute(text("""
        SELECT excel_to_system, source_columns, coverage_rate, updated_at
        FROM app.app_field_mapping_template
        WHERE data_type = :dt AND template_name = :tn AND is_active = TRUE
        ORDER BY updated_at DESC LIMIT 1
    """), {"dt": data_type, "tn": template_name})
    row = r.fetchone()

    system_default = FIELD_MAPPING.get(data_type, {})
    if row:
        return ApiResponse.ok(data={
            "data_type": data_type,
            "template_name": template_name,
            "excel_to_system": row[0],
            "source_columns": row[1],
            "coverage_rate": float(row[2] or 0),
            "updated_at": str(row[3]) if row[3] else None,
            "has_saved_template": True,
            "system_default_mapping": system_default,
        })
    return ApiResponse.ok(data={
        "data_type": data_type,
        "template_name": template_name,
        "excel_to_system": system_default,
        "source_columns": list(system_default.keys()),
        "coverage_rate": 0,
        "has_saved_template": False,
        "system_default_mapping": system_default,
    })


# ── 4. 字段映射验收表输出 ──────────────────────────────────────────────
@router.get("/mapping-table/{data_type}", response_model=ApiResponse)
async def get_mapping_validation_table(
    data_type: str,
    current_user: SysUser = Depends(require_permission("sync:view")),
):
    """输出《百盛字段映射验收表》"""
    from app.services.validation_service import ImportValidationService
    svc = ImportValidationService()
    rows = svc.generate_field_mapping_table(data_type)
    total = len(rows)
    mapped = sum(1 for r in rows if r["is_mapped"])
    required_unmapped = [r["system_field"] for r in rows if r["required"] and not r["is_mapped"]]
    return ApiResponse.ok(data={
        "data_type": data_type,
        "total_fields": total,
        "mapped_count": mapped,
        "coverage_rate": round(mapped / max(total, 1) * 100, 1),
        "required_unmapped": required_unmapped,
        "can_import": len(required_unmapped) == 0,
        "rows": rows,
    })


# ── 5. 验收历史查询 ────────────────────────────────────────────────────
@router.get("/validate-history", response_model=ApiResponse)
async def get_validation_history(
    data_type: Optional[str] = None,
    limit: int = 20,
    current_user: SysUser = Depends(require_permission("sync:view")),
    db: AsyncSession = Depends(get_db),
):
    """查询导入验收历史"""
    where = "WHERE 1=1"
    params: dict = {"limit": limit}
    if data_type:
        where += " AND data_type = :dt"
        params["dt"] = data_type
    r = await db.execute(text(f"""
        SELECT batch_no, data_type, filename, total_rows, success_rows, error_rows,
               duplicate_rows, data_quality_score, allow_etl, block_report, validated_at
        FROM log.log_import_validation {where}
        ORDER BY validated_at DESC LIMIT :limit
    """), params)
    rows = r.fetchall()
    return ApiResponse.ok(data={"items": [{
        "batch_no": r[0], "data_type": r[1], "filename": r[2],
        "total_rows": r[3], "success_rows": r[4], "error_rows": r[5],
        "duplicate_rows": r[6], "data_quality_score": float(r[7] or 0),
        "allow_etl": bool(r[8]), "block_report": bool(r[9]),
        "validated_at": str(r[10]) if r[10] else None,
    } for r in rows], "total": len(rows)})


# ── 6. 指标对账：录入参考值 ────────────────────────────────────────────
class MetricsReferenceBody(BaseModel):
    ref_date: str
    store_code: str = "ALL"
    data_source: str = "manual"
    total_sales: Optional[float] = None
    offline_sales: Optional[float] = None
    online_sales: Optional[float] = None
    return_amount: Optional[float] = None
    net_sales: Optional[float] = None
    item_count: Optional[int] = None
    order_count: Optional[int] = None
    avg_order_value: Optional[float] = None
    items_per_order: Optional[float] = None
    inventory_qty: Optional[int] = None
    inventory_amount: Optional[float] = None
    gross_profit: Optional[float] = None
    gross_margin: Optional[float] = None
    notes: Optional[str] = None


@router.post("/reconcile/reference", response_model=ApiResponse)
async def submit_reference(
    body: MetricsReferenceBody,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """录入百盛原报表参考值（人工录入或API推送）"""
    await db.execute(text("""
        INSERT INTO app.app_metrics_reference
            (ref_date, store_code, data_source, total_sales, offline_sales, online_sales,
             return_amount, net_sales, item_count, order_count, avg_order_value,
             items_per_order, inventory_qty, inventory_amount, gross_profit, gross_margin,
             notes, submitted_by)
        VALUES (:rd, :sc, :ds, :ts, :os, :ons, :ra, :ns, :ic, :oc, :aov, :ipo,
                :iq, :ia, :gp, :gm, :notes, :uid)
        ON CONFLICT (ref_date, store_code) DO UPDATE SET
            total_sales=EXCLUDED.total_sales, offline_sales=EXCLUDED.offline_sales,
            online_sales=EXCLUDED.online_sales, return_amount=EXCLUDED.return_amount,
            net_sales=EXCLUDED.net_sales, item_count=EXCLUDED.item_count,
            order_count=EXCLUDED.order_count, avg_order_value=EXCLUDED.avg_order_value,
            items_per_order=EXCLUDED.items_per_order, inventory_qty=EXCLUDED.inventory_qty,
            inventory_amount=EXCLUDED.inventory_amount, gross_profit=EXCLUDED.gross_profit,
            gross_margin=EXCLUDED.gross_margin, notes=EXCLUDED.notes,
            data_source=EXCLUDED.data_source, submitted_by=EXCLUDED.submitted_by,
            updated_at=NOW()
    """), {
        "rd": date.fromisoformat(body.ref_date), "sc": body.store_code,
        "ds": body.data_source, "ts": body.total_sales, "os": body.offline_sales,
        "ons": body.online_sales, "ra": body.return_amount, "ns": body.net_sales,
        "ic": body.item_count, "oc": body.order_count, "aov": body.avg_order_value,
        "ipo": body.items_per_order, "iq": body.inventory_qty, "ia": body.inventory_amount,
        "gp": body.gross_profit, "gm": body.gross_margin,
        "notes": body.notes, "uid": current_user.id,
    })
    await db.commit()
    return ApiResponse.ok(data={"ref_date": body.ref_date, "store_code": body.store_code},
                          message="参考值已录入")


# ── 7. 指标对账：执行对账计算 ─────────────────────────────────────────
@router.post("/reconcile/run", response_model=ApiResponse)
async def run_reconciliation(
    reconcile_date: str,
    store_code: str = "ALL",
    current_user: SysUser = Depends(require_permission("system:dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """对比系统计算值与百盛原报参考值，生成对账结果"""
    d = date.fromisoformat(reconcile_date)

    # 拉系统值
    sys_r = await db.execute(text("""
        SELECT total_sales, offline_sales, online_sales, net_sales, order_count,
               item_count, avg_order_value, items_per_order, gross_profit, gross_margin
        FROM dm.dm_boss_daily_report WHERE report_date = :d
    """), {"d": d})
    sys_row = sys_r.fetchone()

    inv_r = await db.execute(text("""
        SELECT SUM(total_quantity), SUM(total_cost_amount)
        FROM dws.dws_inventory_daily WHERE stat_date = :d
    """), {"d": d})
    inv_row = inv_r.fetchone()

    ret_r = await db.execute(text("""
        SELECT SUM(return_amount) FROM dws.dws_store_daily WHERE stat_date = :d
    """), {"d": d})
    ret_val = float(ret_r.scalar() or 0)

    if not sys_row:
        return ApiResponse.fail(f"{reconcile_date} 系统日报数据未生成，请先运行ETL")

    # 拉参考值
    ref_r = await db.execute(text("""
        SELECT total_sales, offline_sales, online_sales, return_amount, net_sales,
               item_count, order_count, avg_order_value, items_per_order,
               inventory_qty, inventory_amount, gross_profit, gross_margin
        FROM app.app_metrics_reference WHERE ref_date = :d AND store_code = :sc
    """), {"d": d, "sc": store_code})
    ref_row = ref_r.fetchone()

    if not ref_row:
        return ApiResponse.fail(f"尚未录入 {reconcile_date} 的百盛参考值，请先调用 POST /reconcile/reference")

    # 对账规则
    THRESHOLDS = {
        "total_sales":      {"rate": 0.005, "name": "总销售额"},
        "offline_sales":    {"rate": 0.005, "name": "线下销售额"},
        "online_sales":     {"rate": 0.005, "name": "线上销售额"},
        "return_amount":    {"rate": 0.01,  "name": "退货金额"},
        "net_sales":        {"rate": 0.005, "name": "净销售额"},
        "item_count":       {"rate": 0.01,  "name": "销售件数"},
        "order_count":      {"rate": 0.01,  "name": "订单数"},
        "avg_order_value":  {"rate": 0.01,  "name": "客单价"},
        "items_per_order":  {"rate": 0.01,  "name": "连带率"},
        "inventory_qty":    {"rate": 0.01,  "name": "库存数量"},
        "inventory_amount": {"rate": 0.01,  "name": "库存金额"},
        "gross_profit":     {"rate": 0.02,  "name": "毛利额"},
        "gross_margin":     {"abs": 0.02,   "name": "毛利率"},
    }

    sys_values = {
        "total_sales": float(sys_row[0] or 0), "offline_sales": float(sys_row[1] or 0),
        "online_sales": float(sys_row[2] or 0), "net_sales": float(sys_row[3] or 0),
        "order_count": int(sys_row[4] or 0), "item_count": int(sys_row[5] or 0),
        "avg_order_value": float(sys_row[6] or 0), "items_per_order": float(sys_row[7] or 0),
        "gross_profit": float(sys_row[8] or 0), "gross_margin": float(sys_row[9] or 0),
        "return_amount": ret_val,
        "inventory_qty": int(inv_row[0] or 0) if inv_row else 0,
        "inventory_amount": float(inv_row[1] or 0) if inv_row else 0,
    }
    ref_values = {
        "total_sales": float(ref_row[0] or 0), "offline_sales": float(ref_row[1] or 0),
        "online_sales": float(ref_row[2] or 0), "return_amount": float(ref_row[3] or 0),
        "net_sales": float(ref_row[4] or 0), "item_count": int(ref_row[5] or 0),
        "order_count": int(ref_row[6] or 0), "avg_order_value": float(ref_row[7] or 0),
        "items_per_order": float(ref_row[8] or 0), "inventory_qty": int(ref_row[9] or 0),
        "inventory_amount": float(ref_row[10] or 0), "gross_profit": float(ref_row[11] or 0),
        "gross_margin": float(ref_row[12] or 0),
    }

    results = []
    has_blocking = False
    for metric, cfg in THRESHOLDS.items():
        sys_val = sys_values.get(metric, 0)
        ref_val = ref_values.get(metric, 0)
        diff = sys_val - ref_val

        if ref_val == 0:
            diff_rate = 0.0
            passed = True
            risk = "ok"
        elif "abs" in cfg:
            diff_rate = abs(diff)
            passed = diff_rate <= cfg["abs"]
            risk = "high" if not passed else "ok"
        else:
            diff_rate = abs(diff) / abs(ref_val) if ref_val != 0 else 0
            passed = diff_rate <= cfg["rate"]
            risk = "high" if not passed else "ok"

        is_blocking = risk == "high"
        if is_blocking:
            has_blocking = True

        suggestion = ""
        if not passed:
            if "sales" in metric:
                suggestion = f"差异超{cfg.get('rate', cfg.get('abs', 0))*100:.1f}%，建议核查是否有数据延迟或重复导入"
            elif "inventory" in metric:
                suggestion = "库存差异，建议核查快照日期和门店范围是否一致"
            elif "margin" in metric or "profit" in metric:
                suggestion = "毛利差异，建议确认成本数据是否完整录入"

        row_data = {
            "metric_name": metric, "metric_label": cfg["name"],
            "system_value": round(sys_val, 4), "reference_value": round(ref_val, 4),
            "diff_value": round(diff, 4), "diff_rate": round(diff_rate, 6),
            "is_passed": passed, "risk_level": risk,
            "is_blocking": is_blocking, "suggestion": suggestion,
        }
        results.append(row_data)

        await db.execute(text("""
            INSERT INTO app.app_metrics_reconciliation
                (reconcile_date, metric_name, system_value, reference_value,
                 diff_value, diff_rate, is_passed, risk_level, suggestion, is_blocking)
            VALUES (:rd, :mn, :sv, :rv, :dv, :dr, :ip, :rl, :sug, :ib)
            ON CONFLICT (reconcile_date, metric_name) DO UPDATE SET
                system_value=EXCLUDED.system_value, reference_value=EXCLUDED.reference_value,
                diff_value=EXCLUDED.diff_value, diff_rate=EXCLUDED.diff_rate,
                is_passed=EXCLUDED.is_passed, risk_level=EXCLUDED.risk_level,
                suggestion=EXCLUDED.suggestion, is_blocking=EXCLUDED.is_blocking,
                reconciled_at=NOW()
        """), {
            "rd": d, "mn": metric, "sv": sys_val, "rv": ref_val,
            "dv": diff, "dr": diff_rate, "ip": passed,
            "rl": risk, "sug": suggestion, "ib": is_blocking,
        })

    await db.commit()
    passed_count = sum(1 for r in results if r["is_passed"])
    return ApiResponse.ok(data={
        "reconcile_date": reconcile_date,
        "total_metrics": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "has_blocking": has_blocking,
        "all_passed": not has_blocking,
        "results": results,
    }, message=f"对账完成: {passed_count}/{len(results)}通过" + ("，存在阻断项！" if has_blocking else ""))


@router.get("/reconcile/result/{reconcile_date}", response_model=ApiResponse)
async def get_reconcile_result(
    reconcile_date: str,
    current_user: SysUser = Depends(require_permission("system:dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """查看指定日期的对账结果"""
    d = date.fromisoformat(reconcile_date)
    r = await db.execute(text("""
        SELECT metric_name, system_value, reference_value, diff_value, diff_rate,
               is_passed, risk_level, is_blocking, suggestion, reconciled_at
        FROM app.app_metrics_reconciliation WHERE reconcile_date = :d
        ORDER BY is_blocking DESC, is_passed ASC
    """), {"d": d})
    rows = r.fetchall()
    if not rows:
        return ApiResponse.fail(f"{reconcile_date} 尚无对账结果，请先执行 POST /reconcile/run")
    has_blocking = any(row[7] for row in rows)
    return ApiResponse.ok(data={
        "reconcile_date": reconcile_date,
        "has_blocking": has_blocking,
        "results": [{
            "metric_name": r[0], "system_value": float(r[1] or 0),
            "reference_value": float(r[2] or 0), "diff_value": float(r[3] or 0),
            "diff_rate": float(r[4] or 0), "is_passed": bool(r[5]),
            "risk_level": r[6], "is_blocking": bool(r[7]),
            "suggestion": r[8], "reconciled_at": str(r[9]),
        } for r in rows],
    })


# ── 8. 三天验收看板 ────────────────────────────────────────────────────
class ChecklistUpdateBody(BaseModel):
    check_date: str
    data_imported: Optional[bool] = None
    etl_success: Optional[bool] = None
    report_generated: Optional[bool] = None
    reconcile_done: Optional[bool] = None
    reconcile_passed: Optional[bool] = None
    rule_exceptions: Optional[int] = None
    task_drafts_created: Optional[int] = None
    task_feedback_done: Optional[bool] = None
    task_review_done: Optional[bool] = None
    dingtalk_test_sent: Optional[bool] = None
    issue_count: Optional[int] = None
    blocking_issue_count: Optional[int] = None
    notes: Optional[str] = None


@router.post("/checklist", response_model=ApiResponse)
async def update_checklist(
    body: ChecklistUpdateBody,
    current_user: SysUser = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
):
    """更新三天验收看板某天的状态"""
    d = date.fromisoformat(body.check_date)
    update_fields = {k: v for k, v in body.dict(exclude={"check_date"}).items() if v is not None}

    # 自动判断当天是否通过（所有关键项都完成且无阻断问题）
    existing_r = await db.execute(text("""
        SELECT data_imported, etl_success, report_generated, reconcile_done, reconcile_passed,
               dingtalk_test_sent, blocking_issue_count
        FROM app.app_acceptance_checklist WHERE check_date = :d
    """), {"d": d})
    existing = existing_r.fetchone()

    if existing:
        merged = {
            "data_imported": existing[0], "etl_success": existing[1],
            "report_generated": existing[2], "reconcile_done": existing[3],
            "reconcile_passed": existing[4], "dingtalk_test_sent": existing[5],
            "blocking_issue_count": existing[6] or 0,
        }
        merged.update({k: v for k, v in update_fields.items() if k in merged})
    else:
        merged = {**{
            "data_imported": False, "etl_success": False, "report_generated": False,
            "reconcile_done": False, "reconcile_passed": False,
            "dingtalk_test_sent": False, "blocking_issue_count": 0,
        }, **{k: v for k, v in update_fields.items() if k in ["data_imported","etl_success","report_generated","reconcile_done","reconcile_passed","dingtalk_test_sent","blocking_issue_count"]}}

    day_passed = (
        merged["data_imported"] and merged["etl_success"] and
        merged["report_generated"] and merged["reconcile_done"] and
        merged["reconcile_passed"] and merged["dingtalk_test_sent"] and
        (merged["blocking_issue_count"] or 0) == 0
    )
    update_fields["day_passed"] = day_passed
    update_fields["updated_by"] = current_user.id

    set_clause = ", ".join(f"{k} = :{k}" for k in update_fields)
    params = {"d": d, **update_fields}

    await db.execute(text(f"""
        INSERT INTO app.app_acceptance_checklist (check_date, {', '.join(update_fields.keys())})
        VALUES (:d, {', '.join(f':{k}' for k in update_fields.keys())})
        ON CONFLICT (check_date) DO UPDATE SET {set_clause}, updated_at = NOW()
    """), params)
    await db.commit()

    return ApiResponse.ok(data={"check_date": body.check_date, "day_passed": day_passed},
                          message=f"✅ {body.check_date} 验收状态已更新，当天{'通过' if day_passed else '未通过'}")


@router.get("/dashboard", response_model=ApiResponse)
async def get_acceptance_dashboard(
    current_user: SysUser = Depends(require_permission("system:dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """三天试运营验收看板"""
    r = await db.execute(text("""
        SELECT check_date, data_imported, etl_success, report_generated,
               reconcile_done, reconcile_passed, rule_exceptions, task_drafts_created,
               task_feedback_done, task_review_done, dingtalk_test_sent,
               issue_count, blocking_issue_count, day_passed, notes
        FROM app.app_acceptance_checklist
        ORDER BY check_date DESC LIMIT 10
    """))
    rows = r.fetchall()

    items = [{
        "check_date": str(r[0]), "data_imported": bool(r[1]), "etl_success": bool(r[2]),
        "report_generated": bool(r[3]), "reconcile_done": bool(r[4]),
        "reconcile_passed": bool(r[5]), "rule_exceptions": int(r[6] or 0),
        "task_drafts_created": int(r[7] or 0), "task_feedback_done": bool(r[8]),
        "task_review_done": bool(r[9]), "dingtalk_test_sent": bool(r[10]),
        "issue_count": int(r[11] or 0), "blocking_issue_count": int(r[12] or 0),
        "day_passed": bool(r[13]), "notes": r[14],
    } for r in rows]

    days_passed = sum(1 for i in items if i["day_passed"])
    mvp_accepted = days_passed >= 3

    return ApiResponse.ok(data={
        "days_recorded": len(items),
        "days_passed": days_passed,
        "mvp_accepted": mvp_accepted,
        "acceptance_status": "MVP Phase 1 业务验收通过 ✅" if mvp_accepted else f"进行中（{days_passed}/3天通过）",
        "items": items,
    })


@router.post("/sign-off", response_model=ApiResponse)
async def sign_off(
    notes: str = "",
    current_user: SysUser = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
):
    """最终验收签字（要求3天全通过）"""
    r = await db.execute(text("SELECT COUNT(*) FROM app.app_acceptance_checklist WHERE day_passed = TRUE"))
    passed = int(r.scalar() or 0)
    if passed < 3:
        return ApiResponse.fail(f"验收未完成：当前{passed}天通过，需3天全部通过")
    return ApiResponse.ok(data={
        "accepted_by": current_user.username,
        "accepted_at": str(date.today()),
        "status": "MVP Phase 1 业务验收通过",
        "notes": notes,
    }, message="🎉 MVP Phase 1 业务验收通过！")
