"""Versioned business exception audit API."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.exception_rule_service import rebuild_exception_rules, rule_source_statuses


router = APIRouter(prefix="/audit", tags=["异常稽核"])


@router.get("/exceptions", response_model=ApiResponse)
async def list_exceptions(
    business_date: Optional[date] = None,
    rule_code: Optional[str] = None,
    severity: Optional[str] = None,
    store_code: Optional[str] = None,
    subject_type: Optional[str] = None,
    metric_status: Optional[str] = None,
    task_status: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: SysUser = Depends(require_permission("sales:warning:view")),
    db: AsyncSession = Depends(get_db),
):
    query_date = business_date or (
        await db.execute(text("SELECT MAX(audit_date) FROM dm.dm_exception_audit"))
    ).scalar()
    if not query_date:
        return ApiResponse.ok(data={"items": [], "total": 0, "page": page, "page_size": page_size})

    conditions = ["e.audit_date=:business_date"]
    params: dict[str, object] = {
        "business_date": query_date,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if rule_code:
        conditions.append("e.rule_code=:rule_code")
        params["rule_code"] = rule_code.upper()
    if severity:
        conditions.append("e.severity=:severity")
        params["severity"] = severity
    if store_code:
        conditions.append("UPPER(e.store_code)=:store_code")
        params["store_code"] = store_code.upper()
    if subject_type:
        conditions.append("e.subject_type=:subject_type")
        params["subject_type"] = subject_type
    if metric_status:
        conditions.append("e.metric_status=:metric_status")
        params["metric_status"] = metric_status
    if task_status == "converted":
        conditions.append("e.is_converted_to_task=true")
    elif task_status == "unconverted":
        conditions.append("COALESCE(e.is_converted_to_task,false)=false")
    if keyword:
        conditions.append("(e.description ILIKE :keyword OR e.subject_id ILIKE :keyword OR e.order_no ILIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    where_sql = " AND ".join(conditions)

    total = (await db.execute(text(f"""
        SELECT COUNT(*) FROM dm.dm_exception_audit e WHERE {where_sql}
    """), params)).scalar() or 0
    summary = (await db.execute(text(f"""
        SELECT COUNT(*) FILTER (WHERE e.severity IN ('critical','risk')) major_count,
               COUNT(*) FILTER (WHERE COALESCE(e.is_converted_to_task,false)=false) unconverted_count
        FROM dm.dm_exception_audit e WHERE {where_sql}
    """), params)).mappings().one()
    rows = (await db.execute(text(f"""
        SELECT e.id, e.audit_date, e.rule_code, e.rule_version, e.exception_type,
               e.severity, e.metric_status, e.subject_type, e.subject_id,
               e.store_code, COALESCE(s.store_name, wh.warehouse_name, e.store_code) store_name,
               e.product_code, e.sku_code, e.order_no, e.description, e.thresholds,
               e.data_snapshot, e.evidence_hash, e.source_name, e.source_updated_at,
               e.drilldown, e.responsibility_status, e.is_reviewed,
               e.is_converted_to_task, e.task_id, t.status task_status, e.generated_at
        FROM dm.dm_exception_audit e
        LEFT JOIN dim.dim_store s ON s.store_code=e.store_code AND s.source_system='baison'
        LEFT JOIN dim.dim_warehouse wh ON UPPER(wh.warehouse_code)=UPPER(e.store_code) AND wh.source_system='baison'
        LEFT JOIN app.app_action_task t ON t.id=e.task_id AND t.is_deleted=false
        WHERE {where_sql}
        ORDER BY CASE e.severity WHEN 'critical' THEN 1 WHEN 'risk' THEN 2 WHEN 'warning' THEN 3 ELSE 4 END,
                 e.generated_at DESC, e.id DESC
        LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
    return ApiResponse.ok(data={
        "items": [dict(row) for row in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "business_date": str(query_date),
        "summary": {
            "major_count": int(summary["major_count"] or 0),
            "unconverted_count": int(summary["unconverted_count"] or 0),
        },
    })


@router.get("/exceptions/{exception_id}", response_model=ApiResponse)
async def get_exception(
    exception_id: int,
    current_user: SysUser = Depends(require_permission("sales:warning:view")),
    db: AsyncSession = Depends(get_db),
):
    exception = (await db.execute(text("""
        SELECT e.*, v.rule_name, v.definition_hash, v.effective_from
        FROM dm.dm_exception_audit e
        LEFT JOIN dm.dm_exception_rule_version v
          ON v.rule_code=e.rule_code AND v.version=e.rule_version
        WHERE e.id=:exception_id
    """), {"exception_id": exception_id})).mappings().first()
    if not exception:
        return ApiResponse.fail("异常不存在", code=404)
    evidence = (await db.execute(text("""
        SELECT id, source_table, source_record_id, document_no, before_value, after_value,
               source_fields, evidence_hash, source_updated_at, created_at
        FROM dm.dm_exception_evidence WHERE exception_id=:exception_id ORDER BY id
    """), {"exception_id": exception_id})).mappings().all()
    return ApiResponse.ok(data={**dict(exception), "evidence_records": [dict(row) for row in evidence]})


@router.get("/rules/status", response_model=ApiResponse)
async def get_rule_source_statuses(
    current_user: SysUser = Depends(require_permission("sales:warning:view")),
):
    return ApiResponse.ok(data=rule_source_statuses())


@router.post("/rebuild", response_model=ApiResponse)
async def rebuild_exceptions(
    business_date: Optional[date] = None,
    current_user: SysUser = Depends(require_permission("diagnosis:overall:view")),
    db: AsyncSession = Depends(get_db),
):
    target_date = business_date or (date.today() - timedelta(days=1))
    result = await rebuild_exception_rules(db, target_date)
    return ApiResponse.ok(data=result, message="异常证据已幂等重算")
