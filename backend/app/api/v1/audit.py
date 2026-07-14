"""Versioned business exception and performance-attribution audit API."""

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.exception_rule_service import rebuild_exception_rules, rule_source_statuses
from app.services.exception_rule_service import persist_rule_findings
from app.services.performance_attribution_service import (
    attribution_source_contract,
    build_adjudication_snapshot,
    build_attribution_exception_finding,
    build_rule_version as build_attribution_rule_version,
    evaluate_attribution,
)


router = APIRouter(prefix="/audit", tags=["异常稽核"])


class AttributionEvaluationRequest(BaseModel):
    business_date: date
    case: dict[str, Any] = Field(default_factory=dict)


class AttributionAdjudicationRequest(BaseModel):
    selected_owner_id: str = Field(min_length=1, max_length=64)
    selected_owner_type: str = Field(default="guide", pattern="^(guide|store|team)$")
    reason: str = Field(min_length=2, max_length=500)
    decision_evidence: dict[str, Any] = Field(default_factory=dict)


async def _attribution_source_statuses(db: AsyncSession, business_date: date) -> dict[str, dict[str, Any]]:
    row = (await db.execute(text("""
        SELECT
          (SELECT MAX(synced_at) FROM dwd.dwd_pos_ticket
           WHERE biz_date=:business_date) transaction_updated_at,
          (SELECT completed_at FROM ods.ods_baison_pos_ticket_sync_run
           WHERE status='success'
             AND biz_start_time<=CAST(:business_date AS date)
             AND biz_end_time>=CAST(:business_date AS date)+INTERVAL '1 day'-INTERVAL '1 second'
           ORDER BY started_at DESC, id DESC LIMIT 1) sync_updated_at,
          (SELECT MAX(balance_updated_at) FROM dim.dim_member) member_updated_at
    """), {"business_date": business_date})).mappings().one()
    transaction_updated_at = (
        row["transaction_updated_at"] or row["sync_updated_at"]
    ) if row["sync_updated_at"] else None
    return attribution_source_contract(
        transaction_updated_at=transaction_updated_at,
        refund_updated_at=row["sync_updated_at"],
        member_updated_at=row["member_updated_at"],
    )


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


@router.get("/attribution/status", response_model=ApiResponse)
async def get_attribution_status(
    business_date: Optional[date] = None,
    current_user: SysUser = Depends(require_permission("sales:warning:view")),
    db: AsyncSession = Depends(get_db),
):
    target_date = business_date or (
        await db.execute(text("SELECT MAX(biz_date) FROM dwd.dwd_pos_ticket"))
    ).scalar() or (date.today() - timedelta(days=1))
    sources = await _attribution_source_statuses(db, target_date)
    return ApiResponse.ok(data={
        "business_date": str(target_date),
        "rule_version": build_attribution_rule_version(),
        "all_sources_ready": all(item["status"] == "ready" for item in sources.values()),
        "sources": sources,
    })


@router.post("/attribution/evaluate", response_model=ApiResponse)
async def evaluate_performance_attribution(
    body: AttributionEvaluationRequest,
    current_user: SysUser = Depends(require_permission("diagnosis:overall:view")),
    db: AsyncSession = Depends(get_db),
):
    sources = await _attribution_source_statuses(db, body.business_date)
    case = {**body.case, "business_date": str(body.business_date)}
    result = evaluate_attribution(case, sources)
    finding = build_attribution_exception_finding(case, result)
    persisted = await persist_rule_findings(db, body.business_date, [finding]) if finding else 0
    return ApiResponse.ok(data={**result, "exception_persisted": bool(persisted)})


@router.post("/exceptions/{exception_id}/adjudicate", response_model=ApiResponse)
async def adjudicate_performance_attribution(
    exception_id: int,
    body: AttributionAdjudicationRequest,
    current_user: SysUser = Depends(require_permission("diagnosis:overall:view")),
    db: AsyncSession = Depends(get_db),
):
    if not body.decision_evidence:
        return ApiResponse.fail("人工裁决必须附带证据")
    row = (await db.execute(text("""
        SELECT id, exception_type, data_snapshot
        FROM dm.dm_exception_audit
        WHERE id=:exception_id
        FOR UPDATE
    """), {"exception_id": exception_id})).mappings().first()
    if not row:
        return ApiResponse.fail("异常不存在", code=404)
    if row["exception_type"] != "performance_attribution_conflict":
        return ApiResponse.fail("只有业绩归属冲突可执行归属裁决")

    decided_at = datetime.now(timezone.utc)
    snapshot = build_adjudication_snapshot(
        row["data_snapshot"] or {},
        selected_owner_id=body.selected_owner_id,
        selected_owner_type=body.selected_owner_type,
        reason=body.reason,
        decision_evidence=body.decision_evidence,
        decided_by=int(current_user.id),
        decided_at=decided_at,
    )
    await db.execute(text("""
        UPDATE dm.dm_exception_audit
        SET data_snapshot=CAST(:snapshot AS jsonb),
            is_reviewed=true,
            reviewed_by=:reviewed_by,
            reviewed_at=:reviewed_at,
            review_note=:review_note,
            responsibility_status='adjudicated'
        WHERE id=:exception_id
    """), {
        "exception_id": exception_id,
        "snapshot": json.dumps(snapshot, ensure_ascii=False, default=str),
        "reviewed_by": int(current_user.id),
        "reviewed_at": decided_at,
        "review_note": body.reason,
    })
    return ApiResponse.ok(data={
        "exception_id": exception_id,
        "responsibility_status": "adjudicated",
        "adjudication": snapshot["adjudication"],
        "history_count": len(snapshot.get("adjudication_history") or []),
    }, message="归属裁决已保存，原始交易未被修改")


@router.post("/rebuild", response_model=ApiResponse)
async def rebuild_exceptions(
    business_date: Optional[date] = None,
    current_user: SysUser = Depends(require_permission("diagnosis:overall:view")),
    db: AsyncSession = Depends(get_db),
):
    target_date = business_date or (date.today() - timedelta(days=1))
    result = await rebuild_exception_rules(db, target_date)
    return ApiResponse.ok(data=result, message="异常证据已幂等重算")
