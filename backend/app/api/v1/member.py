"""会员运营接口。

当前会员档案和回访名单表可能为空；页面先展示百胜小票中可识别的会员线索，
等会员主档同步后再自然启用档案和回访数据。
"""
import csv
import io
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.data_scope import get_data_scope
from app.core.field_permissions import get_user_field_rules
from app.core.database import get_db
from app.core.store_whitelist import ALLOWED_INVENTORY_CODES, ALLOWED_STORE_CODES
from app.models.sys import SysOperationLog, SysUser
from app.services.member_segment_service import (
    get_member_segment_overview,
    list_member_segment_rows,
    rebuild_member_segments,
)
from app.services.member_sales_service import get_vip_sales_analysis
from app.services.member_action_service import (
    generate_member_action_drafts,
    get_member_action_overview,
    list_member_actions,
)

logger = logging.getLogger("member.api")

router = APIRouter(prefix="/member", tags=["会员运营"])

POS_MEMBER_BASE_SQL = """
    WITH ticket_base AS (
        SELECT t.biz_date,
               t.store_code,
               COALESCE(s.store_name, t.store_name, t.store_code) AS store_name,
               NULLIF(
                 BTRIM(COALESCE(NULLIF(t.vip_code::text, ''), NULLIF(t.customer_code::text, ''), '')),
                 ''
               ) AS member_key,
               COALESCE(t.sales_amount, 0) AS sales_amount,
               COALESCE(t.actual_pay_amount, 0) AS actual_pay_amount,
               t.sales_qty,
               t.ticket_no
        FROM dwd.dwd_pos_ticket t
        LEFT JOIN dim.dim_store s ON s.store_code = t.store_code
        WHERE t.biz_date >= CAST(:sd AS date)
          AND t.biz_date <= CAST(:ed AS date)
          AND t.store_code = ANY(:store_codes)
          AND COALESCE(t.is_void, false) = false
          AND COALESCE(t.is_pending, false) = false
    ), grouped AS (
        SELECT member_key,
               COUNT(*)::int AS order_count,
               COALESCE(SUM(sales_qty), 0) AS sales_qty,
               COALESCE(SUM(sales_amount), 0) AS total_sales,
               COALESCE(SUM(actual_pay_amount), 0) AS total_actual,
               MIN(biz_date) AS first_consume_date,
               MAX(biz_date) AS last_consume_date,
               (ARRAY_AGG(store_code ORDER BY biz_date DESC, ticket_no DESC))[1] AS last_store_code,
               (ARRAY_AGG(store_name ORDER BY biz_date DESC, ticket_no DESC))[1] AS last_store_name
        FROM ticket_base
        WHERE member_key IS NOT NULL
          AND (:kw = '' OR member_key ILIKE :kw OR store_code ILIKE :kw OR store_name ILIKE :kw)
        GROUP BY member_key
    )
"""


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_csv_cell(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


def _redact_member_fields(
    item: dict[str, Any],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    redacted = dict(item)
    for field in fields:
        redacted[field] = None
    redacted["sensitive_redacted"] = True
    return redacted


def _redact_segment_item(item: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(item)
    redacted["phone"] = _mask_member_key(redacted.get("phone"))
    for key in ("current_balance", "total_amount", "total_count", "last_consume_date"):
        redacted[key] = None
    for key in ("labels", "risks", "wakeup_reasons"):
        redacted[key] = [
            {field: value for field, value in entry.items() if field != "evidence"}
            for entry in (redacted.get(key) or [])
        ]
    redacted["metrics"] = {}
    redacted["preferences"] = []
    redacted["suggested_products"] = []
    redacted["candidate_guide_ids"] = []
    redacted["sensitive_redacted"] = True
    return redacted


def _date_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)[:10]


def _time_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value).replace("T", " ")[:19]


def _mask_member_key(value: Any) -> str:
    raw = str(value or "").strip()
    if len(raw) == 11 and raw.isdigit():
        return f"{raw[:3]}****{raw[-4:]}"
    if len(raw) >= 9:
        return f"{raw[:3]}****{raw[-3:]}"
    return raw


def _parse_date(value: Optional[str], fallback: date) -> date:
    if not value:
        return fallback
    return date.fromisoformat(value[:10])


async def _allowed_store_codes(db: AsyncSession, current_user: SysUser) -> list[str]:
    data_scope = await get_data_scope(db, current_user)
    if data_scope.is_limited_store:
        return sorted(set(data_scope.store_codes or []) & set(ALLOWED_STORE_CODES))
    return sorted(ALLOWED_STORE_CODES)


async def _allowed_member_codes(db: AsyncSession, current_user: SysUser) -> list[str]:
    """VIP assets use the confirmed 7 stores + 3 warehouse codes."""
    data_scope = await get_data_scope(db, current_user)
    allowed = {str(code).upper() for code in ALLOWED_INVENTORY_CODES}
    if data_scope.is_limited_store:
        return sorted({str(code).upper() for code in (data_scope.store_codes or [])} & allowed)
    return sorted(allowed)


async def _has_permission(
    db: AsyncSession,
    current_user: SysUser,
    permission_code: str,
) -> bool:
    if current_user.is_admin:
        return True
    return bool((await db.execute(text("""
        SELECT 1
        FROM sys.sys_user_role ur
        JOIN sys.sys_role_permission rp ON rp.role_id=ur.role_id
        JOIN sys.sys_permission p ON p.id=rp.permission_id
        WHERE ur.user_id=:user_id AND p.code=:permission_code
        LIMIT 1
    """), {"user_id": current_user.id, "permission_code": permission_code})).scalar())


async def _table_count(db: AsyncSession, schema: str, table: str) -> int:
    exists = (await db.execute(
        text("SELECT to_regclass(:name) IS NOT NULL AS exists"),
        {"name": f"{schema}.{table}"},
    )).scalar()
    if not exists:
        return 0
    return int((await db.execute(text(f"SELECT COUNT(*) FROM {schema}.{table}"))).scalar() or 0)


async def _latest_ticket_date(db: AsyncSession, store_codes: list[str]) -> Optional[date]:
    row = (await db.execute(text("""
        SELECT MAX(biz_date) AS latest_date
        FROM dwd.dwd_pos_ticket
        WHERE store_code = ANY(:store_codes)
          AND COALESCE(is_void, false) = false
          AND COALESCE(is_pending, false) = false
    """), {"store_codes": store_codes})).mappings().first()
    return row["latest_date"] if row else None


async def _can_view_sensitive_phone(
    db: AsyncSession,
    current_user: SysUser,
    include_sensitive: bool,
) -> bool:
    if not include_sensitive:
        return False
    if current_user.is_admin:
        return True
    rules = await get_user_field_rules(db, current_user, "sales")
    return rules.get("customer_phone") == "none"


async def _audit_sensitive_phone_view(
    db: AsyncSession,
    current_user: SysUser,
    target: str,
) -> None:
    db.add(SysOperationLog(
        user_id=current_user.id,
        username=current_user.username,
        module="member",
        action="sensitive_phone.view",
        target_type="member_phone",
        target_id=target,
        after_data={"field": "customer_phone", "access": "full"},
    ))


async def _audit_sensitive_data_access(
    db: AsyncSession,
    current_user: SysUser,
    action: str,
    target: str,
    fields: list[str],
) -> None:
    db.add(SysOperationLog(
        user_id=current_user.id,
        username=current_user.username,
        module="member",
        action=action,
        target_type="member_sensitive_data",
        target_id=target,
        after_data={"fields": fields, "access": "view" if not action.endswith(".export") else "export"},
    ))


@router.get("/overview")
async def member_overview(
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """会员运营概览：档案表、回访表、小票会员线索三个层面的状态。"""
    try:
        store_codes = await _allowed_store_codes(db, current_user)
        member_codes = await _allowed_member_codes(db, current_user)
        if not store_codes and not member_codes:
            return {"success": True, "data": {"summary": {}, "data_status": {"has_store_access": False}}}

        dim_members = int((await db.execute(text("""
            SELECT COUNT(*) FROM dim.dim_member
            WHERE UPPER(register_store)=ANY(:codes)
        """), {"codes": member_codes})).scalar() or 0)
        ods_members = int((await db.execute(text("""
            SELECT COUNT(*) FROM ods.ods_baison_member
            WHERE UPPER(register_store)=ANY(:codes)
        """), {"codes": member_codes})).scalar() or 0)

        ticket_row = (await db.execute(text("""
            WITH ticket_base AS (
                SELECT biz_date,
                       store_code,
                       NULLIF(
                         BTRIM(COALESCE(NULLIF(vip_code::text, ''), NULLIF(customer_code::text, ''), '')),
                         ''
                       ) AS member_key,
                       COALESCE(sales_amount, 0) AS sales_amount,
                       COALESCE(actual_pay_amount, 0) AS actual_pay_amount,
                       synced_at
                FROM dwd.dwd_pos_ticket
                WHERE store_code = ANY(:store_codes)
                  AND COALESCE(is_void, false) = false
                  AND COALESCE(is_pending, false) = false
            )
            SELECT COUNT(*)::int AS total_tickets,
                   COUNT(*) FILTER (WHERE member_key IS NOT NULL)::int AS member_tickets,
                   COUNT(DISTINCT member_key)::int AS member_clues,
                   COALESCE(SUM(sales_amount), 0) AS total_sales,
                   COALESCE(SUM(actual_pay_amount), 0) AS total_actual,
                   COALESCE(SUM(sales_amount) FILTER (WHERE member_key IS NOT NULL), 0) AS member_sales,
                   COALESCE(SUM(actual_pay_amount) FILTER (WHERE member_key IS NOT NULL), 0) AS member_actual,
                   MAX(biz_date) AS latest_date,
                   MAX(synced_at) AS updated_at
            FROM ticket_base
        """), {"store_codes": store_codes})).mappings().first() or {}

        visit_row = (await db.execute(text("""
            SELECT COUNT(*)::int AS total_visits,
                   COUNT(*) FILTER (WHERE visit_date = CURRENT_DATE)::int AS today_visits,
                   COUNT(*) FILTER (WHERE visit_status = 'pending')::int AS pending_visits,
                   COUNT(*) FILTER (WHERE visit_status IN ('visited', 'success'))::int AS done_visits
            FROM dm.dm_member_visit_list
        """))).mappings().first() or {}

        member_sales = _num(ticket_row.get("member_sales"))
        total_sales = _num(ticket_row.get("total_sales"))
        member_tickets = int(ticket_row.get("member_tickets") or 0)
        total_tickets = int(ticket_row.get("total_tickets") or 0)
        summary = {
            "profile_members": dim_members,
            "ods_members": ods_members,
            "member_clues": int(ticket_row.get("member_clues") or 0),
            "member_tickets": member_tickets,
            "total_tickets": total_tickets,
            "member_ticket_ratio": round(member_tickets / total_tickets, 4) if total_tickets else 0,
            "member_sales": round(member_sales, 2),
            "member_actual": round(_num(ticket_row.get("member_actual")), 2),
            "total_sales": round(total_sales, 2),
            "member_sales_ratio": round(member_sales / total_sales, 4) if total_sales else 0,
            "today_visits": int(visit_row.get("today_visits") or 0),
            "pending_visits": int(visit_row.get("pending_visits") or 0),
            "done_visits": int(visit_row.get("done_visits") or 0),
            "latest_ticket_date": _date_str(ticket_row.get("latest_date")),
            "updated_at": _time_str(ticket_row.get("updated_at")),
        }
        return {
            "success": True,
            "data": {
                "summary": summary,
                "data_status": {
                    "has_store_access": True,
                    "member_profile_synced": dim_members > 0,
                    "baison_member_ods_synced": ods_members > 0,
                    "visit_list_generated": int(visit_row.get("total_visits") or 0) > 0,
                    "source_note": "会员档案未同步时，先展示百胜小票中的会员线索。",
                },
            },
        }
    except Exception:
        logger.exception("member overview error")
        return {"success": False, "message": "会员概览查询失败，请查看服务日志"}


@router.get("/pos-members")
async def list_pos_member_clues(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """从百胜小票聚合会员线索。"""
    try:
        store_codes = await _allowed_store_codes(db, current_user)
        latest_date = await _latest_ticket_date(db, store_codes)
        if not store_codes or not latest_date:
            return {"success": True, "data": {"items": [], "total": 0, "page": page, "page_size": page_size}}
        sd = _parse_date(start_date, latest_date)
        ed = _parse_date(end_date, latest_date)
        kw = f"%{keyword.strip()}%" if keyword and keyword.strip() else ""
        params = {
            "store_codes": store_codes,
            "sd": sd,
            "ed": ed,
            "kw": kw,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        total = (await db.execute(text(POS_MEMBER_BASE_SQL + " SELECT COUNT(*) FROM grouped"), params)).scalar() or 0
        rows = (await db.execute(text(POS_MEMBER_BASE_SQL + """
            SELECT *
            FROM grouped
            ORDER BY total_sales DESC, last_consume_date DESC, member_key
            LIMIT :limit OFFSET :offset
        """), params)).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            item["member_key_masked"] = _mask_member_key(item.get("member_key"))
            item["member_key"] = item["member_key_masked"]
            item["order_count"] = int(item.get("order_count") or 0)
            item["sales_qty"] = _num(item.get("sales_qty"))
            item["total_sales"] = round(_num(item.get("total_sales")), 2)
            item["total_actual"] = round(_num(item.get("total_actual")), 2)
            item["avg_order_value"] = round(item["total_sales"] / item["order_count"], 2) if item["order_count"] else 0
            item["first_consume_date"] = _date_str(item.get("first_consume_date"))
            item["last_consume_date"] = _date_str(item.get("last_consume_date"))
            items.append(item)
        return {
            "success": True,
            "data": {
                "items": items,
                "total": int(total),
                "page": page,
                "page_size": page_size,
                "date_range": {"start_date": str(sd), "end_date": str(ed)},
                "latest_ticket_date": str(latest_date),
            },
        }
    except Exception:
        logger.exception("member pos clues error")
        return {"success": False, "message": "会员线索查询失败，请查看服务日志"}


@router.get("/list")
async def list_members(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    member_level: Optional[str] = None,
    status: Optional[str] = None,
    include_sensitive: bool = False,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """会员档案分页。"""
    try:
        member_codes = await _allowed_member_codes(db, current_user)
        if not member_codes:
            return {"success": True, "data": {"items": [], "total": 0, "page": page, "page_size": page_size, "phone_masked": True}}
        show_sensitive = await _can_view_sensitive_phone(db, current_user, include_sensitive)
        can_view_member_sensitive = await _has_permission(db, current_user, "member:sensitive:view")
        conditions = ["UPPER(m.register_store)=ANY(:member_codes)"]
        params: dict[str, Any] = {"member_codes": member_codes, "limit": page_size, "offset": (page - 1) * page_size}
        if keyword and keyword.strip():
            params["kw"] = f"%{keyword.strip()}%"
            phone_search = " OR m.phone ILIKE :kw" if show_sensitive else ""
            conditions.append(f"(m.member_no ILIKE :kw OR m.member_name ILIKE :kw{phone_search})")
        if member_level:
            params["member_level"] = member_level
            conditions.append("m.member_level = :member_level")
        if status:
            params["status"] = status
            conditions.append("m.status = :status")
        where_sql = " AND ".join(conditions)
        total = (await db.execute(text(f"SELECT COUNT(*) FROM dim.dim_member m WHERE {where_sql}"), params)).scalar() or 0
        order_sql = "m.last_consume_date DESC NULLS LAST, m.total_amount DESC NULLS LAST, m.member_no" if can_view_member_sensitive else "m.member_no"
        rows = (await db.execute(text(f"""
            SELECT m.member_no, m.member_name, m.phone, m.gender, m.birthday,
                   m.register_date, m.register_store, COALESCE(s.store_name, m.register_store) AS register_store_name,
                   m.member_level, m.total_amount, m.total_count, m.last_consume_date,
                   m.last_consume_store, m.rfm_score, m.rfm_segment, m.status, m.updated_at
            FROM dim.dim_member m
            LEFT JOIN dim.dim_store s ON s.store_code = m.register_store
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT :limit OFFSET :offset
        """), params)).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            if not show_sensitive:
                item["phone"] = _mask_member_key(item.get("phone"))
            item["total_amount"] = round(_num(item.get("total_amount")), 2)
            item["rfm_score"] = round(_num(item.get("rfm_score")), 2)
            item["birthday"] = _date_str(item.get("birthday"))
            item["register_date"] = _date_str(item.get("register_date"))
            item["last_consume_date"] = _date_str(item.get("last_consume_date"))
            item["updated_at"] = _time_str(item.get("updated_at"))
            if not can_view_member_sensitive:
                item = _redact_member_fields(item, ("birthday", "total_amount", "total_count", "last_consume_date", "last_consume_store", "rfm_score", "rfm_segment"))
            items.append(item)
        if show_sensitive:
            await _audit_sensitive_phone_view(db, current_user, "member/list")
        if can_view_member_sensitive:
            await _audit_sensitive_data_access(db, current_user, "sensitive_profile.view", "member/list", ["total_amount", "total_count", "last_consume_date"])
        return {"success": True, "data": {"items": items, "total": int(total), "page": page, "page_size": page_size, "phone_masked": not show_sensitive, "sensitive_redacted": not can_view_member_sensitive}}
    except Exception:
        logger.exception("member list error")
        return {"success": False, "message": "会员档案查询失败，请查看服务日志"}


@router.get("/visits")
async def list_member_visits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    visit_status: Optional[str] = None,
    include_sensitive: bool = False,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """会员回访名单分页。"""
    try:
        member_codes = await _allowed_member_codes(db, current_user)
        if not member_codes:
            return {"success": True, "data": {"items": [], "total": 0, "page": page, "page_size": page_size, "phone_masked": True}}
        show_sensitive = await _can_view_sensitive_phone(db, current_user, include_sensitive)
        can_view_member_sensitive = await _has_permission(db, current_user, "member:sensitive:view")
        conditions = ["UPPER(v.store_code)=ANY(:member_codes)"]
        params: dict[str, Any] = {"member_codes": member_codes, "limit": page_size, "offset": (page - 1) * page_size}
        if visit_status:
            params["visit_status"] = visit_status
            conditions.append("v.visit_status = :visit_status")
        where_sql = " AND ".join(conditions)
        total = (await db.execute(text(f"SELECT COUNT(*) FROM dm.dm_member_visit_list v WHERE {where_sql}"), params)).scalar() or 0
        rows = (await db.execute(text(f"""
            SELECT v.visit_date, v.member_no, m.member_name, m.phone,
                   v.store_code, COALESCE(s.store_name, v.store_code) AS store_name,
                   v.visit_reason, v.priority, v.last_consume_date, v.sleep_days,
                   v.ai_suggestion, v.visit_status, v.visited_by, v.visited_at,
                   v.visit_result, v.is_converted, v.conversion_amount
            FROM dm.dm_member_visit_list v
            LEFT JOIN dim.dim_member m ON m.member_no = v.member_no
            LEFT JOIN dim.dim_store s ON s.store_code = v.store_code
            WHERE {where_sql}
            ORDER BY v.visit_date DESC, v.priority ASC, v.member_no
            LIMIT :limit OFFSET :offset
        """), params)).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            if not show_sensitive:
                item["phone"] = _mask_member_key(item.get("phone"))
            item["visit_date"] = _date_str(item.get("visit_date"))
            item["last_consume_date"] = _date_str(item.get("last_consume_date"))
            item["visited_at"] = _time_str(item.get("visited_at"))
            item["conversion_amount"] = round(_num(item.get("conversion_amount")), 2)
            if not can_view_member_sensitive:
                item = _redact_member_fields(item, ("last_consume_date", "sleep_days", "ai_suggestion", "visit_result", "conversion_amount"))
            items.append(item)
        if show_sensitive:
            await _audit_sensitive_phone_view(db, current_user, "member/visits")
        if can_view_member_sensitive:
            await _audit_sensitive_data_access(db, current_user, "sensitive_visit.view", "member/visits", ["last_consume_date", "conversion_amount"])
        return {"success": True, "data": {"items": items, "total": int(total), "page": page, "page_size": page_size, "phone_masked": not show_sensitive, "sensitive_redacted": not can_view_member_sensitive}}
    except Exception:
        logger.exception("member visits error")
        return {"success": False, "message": "会员回访查询失败，请查看服务日志"}


@router.get("/assets/overview")
async def member_asset_overview(
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """VIP储值资产概览；当前余额以百胜会员主档CZ_DQJE为准。"""
    can_view_member_sensitive = await _has_permission(db, current_user, "member:sensitive:view")
    codes = await _allowed_member_codes(db, current_user)
    if not codes:
        return {"success": True, "data": {"summary": {}, "stores": [], "scope_codes": [], "balance_source": "百胜会员主档 CZ_DQJE", "sensitive_redacted": not can_view_member_sensitive}}
    summary = (await db.execute(text("""
        SELECT COUNT(*) member_count,
               COUNT(*) FILTER (WHERE current_balance>0) balance_member_count,
               COALESCE(SUM(GREATEST(COALESCE(current_balance,0),0)),0) total_balance,
               COUNT(*) FILTER (WHERE current_balance<0) negative_balance_count,
               COALESCE(SUM(ABS(current_balance)) FILTER (WHERE current_balance<0),0) negative_balance_amount,
               COALESCE(SUM(GREATEST(COALESCE(current_balance,0),0)) FILTER (
                   WHERE last_consume_date<CURRENT_DATE-90
               ),0) dormant_balance_90d,
               COUNT(*) FILTER (WHERE current_balance>0 AND last_consume_date<CURRENT_DATE-90) dormant_member_90d,
               MAX(balance_updated_at) updated_at
        FROM dim.dim_member
        WHERE UPPER(register_store)=ANY(:codes) AND COALESCE(status,'active')='active'
    """), {"codes": codes})).mappings().one()
    stores = (await db.execute(text("""
        SELECT UPPER(m.register_store) store_code,
               COALESCE(s.store_name,w.warehouse_name,m.register_store) store_name,
               COUNT(*) FILTER (WHERE m.current_balance>0) member_count,
               COALESCE(SUM(GREATEST(COALESCE(m.current_balance,0),0)),0) balance
        FROM dim.dim_member m
        LEFT JOIN dim.dim_store s ON s.store_code=m.register_store
        LEFT JOIN dim.dim_warehouse w ON w.warehouse_code=UPPER(m.register_store)
        WHERE UPPER(m.register_store)=ANY(:codes) AND COALESCE(m.status,'active')='active'
        GROUP BY UPPER(m.register_store),s.store_name,w.warehouse_name,m.register_store
        ORDER BY balance DESC
    """), {"codes": codes})).mappings().all()
    deposits = (await db.execute(text("""
        SELECT COALESCE(SUM(money_change) FILTER (WHERE business_type='recharge'),0) recharge_30d,
               COALESCE(SUM(ABS(money_change)) FILTER (WHERE business_type='consume'),0) consume_30d,
               COUNT(DISTINCT member_no) FILTER (WHERE business_type='recharge') recharge_member_30d,
               MAX(synced_at) updated_at
        FROM dwd.dwd_baison_member_deposit_log
        WHERE biz_date BETWEEN CURRENT_DATE-29 AND CURRENT_DATE AND UPPER(store_code)=ANY(:codes)
    """), {"codes": codes})).mappings().one()
    data = dict(summary)
    for key in ("total_balance", "negative_balance_amount", "dormant_balance_90d"):
        data[key] = round(_num(data.get(key)), 2)
    data["updated_at"] = _time_str(data.get("updated_at"))
    data["recharge_30d"] = round(_num(deposits.get("recharge_30d")), 2)
    data["consume_30d"] = round(_num(deposits.get("consume_30d")), 2)
    data["recharge_member_30d"] = int(deposits.get("recharge_member_30d") or 0)
    data["transaction_updated_at"] = _time_str(deposits.get("updated_at"))
    store_items = [
        {**dict(row), "member_count": int(row["member_count"] or 0), "balance": round(_num(row["balance"]), 2)}
        for row in stores
    ]
    if can_view_member_sensitive:
        await _audit_sensitive_data_access(db, current_user, "sensitive_balance.view", "member/assets/overview", ["current_balance"])
    else:
        data = _redact_member_fields(
            data,
            ("total_balance", "negative_balance_amount", "dormant_balance_90d", "recharge_30d", "consume_30d"),
        )
        store_items = [_redact_member_fields(item, ("balance",)) for item in store_items]
    return {"success": True, "data": {
        "summary": data,
        "stores": store_items,
        "scope_codes": codes,
        "balance_source": "百胜会员主档 CZ_DQJE",
        "sensitive_redacted": not can_view_member_sensitive,
    }}


@router.get("/segments/overview")
async def member_segment_overview(
    calc_date: Optional[date] = None,
    current_user: SysUser = Depends(require_permission("member:segment:view")),
    db: AsyncSession = Depends(get_db),
):
    codes = await _allowed_member_codes(db,current_user)
    data = await get_member_segment_overview(db,codes,calc_date)
    await _audit_sensitive_data_access(db,current_user,"sensitive_segment.view","member/segments/overview",["current_balance","total_amount","risks"])
    return {"success":True,"data":data}


async def _segment_list_response(
    db: AsyncSession,
    current_user: SysUser,
    *,
    kind: str,
    calc_date: Optional[date],
    page: int,
    page_size: int,
    keyword: Optional[str],
    label_code: Optional[str] = None,
    risk_code: Optional[str] = None,
) -> dict[str, Any]:
    codes = await _allowed_member_codes(db,current_user)
    data = await list_member_segment_rows(
        db,codes,calc_date=calc_date,kind=kind,page=page,page_size=page_size,
        keyword=keyword,label_code=label_code,risk_code=risk_code,
    )
    can_view_sensitive = await _has_permission(db, current_user, "member:sensitive:view")
    if can_view_sensitive:
        for item in data["items"]:
            item["phone"] = _mask_member_key(item.get("phone"))
            item["sensitive_redacted"] = False
        await _audit_sensitive_data_access(db,current_user,"sensitive_segment.view",f"member/segments/{kind}",["current_balance","total_amount","risks"])
    else:
        data["items"] = [_redact_segment_item(item) for item in data["items"]]
    return {"success":True,"data":data}


@router.get("/segments/list")
async def list_member_segments(
    calc_date: Optional[date] = None,
    page: int = Query(1,ge=1),
    page_size: int = Query(20,ge=1,le=200),
    keyword: Optional[str] = None,
    label_code: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("member:segment:view")),
    db: AsyncSession = Depends(get_db),
):
    return await _segment_list_response(db,current_user,kind="segments",calc_date=calc_date,page=page,page_size=page_size,keyword=keyword,label_code=label_code)


@router.get("/segments/risks")
async def list_member_risks(
    calc_date: Optional[date] = None,
    page: int = Query(1,ge=1),
    page_size: int = Query(20,ge=1,le=200),
    keyword: Optional[str] = None,
    risk_code: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("member:segment:view")),
    db: AsyncSession = Depends(get_db),
):
    return await _segment_list_response(db,current_user,kind="risks",calc_date=calc_date,page=page,page_size=page_size,keyword=keyword,risk_code=risk_code)


@router.get("/segments/wakeups")
async def list_member_wakeups(
    calc_date: Optional[date] = None,
    page: int = Query(1,ge=1),
    page_size: int = Query(20,ge=1,le=200),
    keyword: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("member:segment:view")),
    db: AsyncSession = Depends(get_db),
):
    return await _segment_list_response(db,current_user,kind="wakeups",calc_date=calc_date,page=page,page_size=page_size,keyword=keyword)


@router.post("/segments/rebuild")
async def rebuild_member_segment_snapshot(
    calc_date: Optional[date] = None,
    current_user: SysUser = Depends(require_permission("member:segment:rebuild")),
    db: AsyncSession = Depends(get_db),
):
    codes = await _allowed_member_codes(db,current_user)
    try:
        result = await rebuild_member_segments(db,calc_date=calc_date,store_codes=codes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(SysOperationLog(user_id=current_user.id,username=current_user.username,module="member",action="segment.rebuild",target_type="member_segment",target_id=result.get("calc_date"),after_data={key:value for key,value in result.items() if key!="member_nos"}))
    return {"success":True,"data":result}


@router.get("/segments/export")
async def export_member_segments(
    kind: str = Query("segments",pattern="^(segments|risks|wakeups)$"),
    calc_date: Optional[date] = None,
    keyword: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("member:sensitive:export")),
    db: AsyncSession = Depends(get_db),
):
    codes = await _allowed_member_codes(db,current_user)
    data = await list_member_segment_rows(db,codes,calc_date=calc_date,kind=kind,page=1,page_size=50000,keyword=keyword)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["计算日期","会员编号","会员姓名","手机号","门店编码","门店名称","当前余额","累计消费","最近消费","标签","风险","偏好","建议商品","责任状态"])
    for item in data["items"]:
        writer.writerow([
            _safe_csv_cell(item.get("calc_date")),_safe_csv_cell(item.get("member_no")),_safe_csv_cell(item.get("member_name")),_safe_csv_cell(item.get("phone")),
            _safe_csv_cell(item.get("store_code")),_safe_csv_cell(item.get("store_name")),item.get("current_balance"),item.get("total_amount"),
            _safe_csv_cell(item.get("last_consume_date")),_safe_csv_cell("、".join(value.get("name","") for value in item.get("labels") or [])),
            _safe_csv_cell("、".join(value.get("name","") for value in item.get("risks") or [])),
            _safe_csv_cell("、".join(value.get("name","") for value in item.get("preferences") or [])),
            _safe_csv_cell("、".join(value.get("product_name","") for value in item.get("suggested_products") or [])),
            _safe_csv_cell(item.get("responsibility_status")),
        ])
    await _audit_sensitive_data_access(db,current_user,"sensitive_member.export",f"member/segments/{kind}",["phone","current_balance","total_amount","risks"])
    payload=("\ufeff"+output.getvalue()).encode("utf-8")
    filename=f"member_{kind}_{data.get('calc_date') or 'empty'}.csv"
    return StreamingResponse(iter([payload]),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{filename}"'})


@router.get("/sales/analysis")
async def member_sales_analysis(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """VIP销售分析；不可靠的毛利和商品维度显式返回pending_data。"""
    store_codes = await _allowed_store_codes(db, current_user)
    latest_date = await _latest_ticket_date(db, store_codes)
    if not store_codes or not latest_date:
        return {"success": True, "data": {"summary": {}, "stores": [], "trend": [], "data_status": "pending_data"}}
    end = min(end_date or latest_date, latest_date)
    start = start_date or end - timedelta(days=29)
    if start > end:
        return {"success": False, "message": "开始日期不能晚于结束日期"}
    data = await get_vip_sales_analysis(db, start, end, store_codes)
    return {"success": True, "data": data}


@router.get("/assets/list")
async def list_member_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    store_code: Optional[str] = None,
    balance_status: Optional[str] = None,
    min_balance: float = Query(0, ge=0),
    include_sensitive: bool = False,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    show_sensitive = await _can_view_sensitive_phone(db, current_user, include_sensitive)
    can_view_member_sensitive = await _has_permission(db, current_user, "member:sensitive:view")
    if not can_view_member_sensitive and (balance_status or min_balance > 0):
        raise HTTPException(status_code=403, detail="无会员敏感数据查看权限")
    codes = await _allowed_member_codes(db,current_user)
    if not codes:
        return {"success":True,"data":{"items":[],"total":0,"page":page,"page_size":page_size,"phone_masked":True,"sensitive_redacted":not can_view_member_sensitive}}
    conditions = ["UPPER(m.register_store)=ANY(:codes)", "COALESCE(m.status,'active')='active'"]
    params: dict[str, Any] = {"codes": codes, "min_balance": min_balance, "limit": page_size, "offset": (page-1)*page_size}
    if keyword and keyword.strip():
        phone_search = " OR m.phone ILIKE :kw" if show_sensitive else ""
        conditions.append(f"(m.member_no ILIKE :kw OR m.member_name ILIKE :kw{phone_search})")
        params["kw"] = f"%{keyword.strip()}%"
    if store_code:
        if store_code.upper() not in codes:
            return {"success": False, "message": "门店不在VIP统计范围"}
        conditions.append("UPPER(m.register_store)=:store_code")
        params["store_code"] = store_code.upper()
    if can_view_member_sensitive:
        if balance_status == "positive":
            conditions.append("m.current_balance>=GREATEST(:min_balance,0.01)")
        elif balance_status == "negative":
            conditions.append("m.current_balance<0")
        elif balance_status == "dormant":
            conditions.extend(["m.current_balance>0", "m.last_consume_date<CURRENT_DATE-90"])
        elif balance_status == "high":
            conditions.append("m.current_balance>=5000")
        else:
            conditions.append("COALESCE(m.current_balance,0)>=:min_balance")
    where_sql = " AND ".join(conditions)
    total = (await db.execute(text(f"SELECT COUNT(*) FROM dim.dim_member m WHERE {where_sql}"), params)).scalar() or 0
    rows = (await db.execute(text(f"""
        SELECT m.member_no,m.member_name,m.phone,m.register_store,
               COALESCE(s.store_name,w.warehouse_name,m.register_store) register_store_name,
               m.member_level,m.current_balance,m.total_amount,m.total_count,
               m.last_consume_date,m.balance_updated_at,
               CASE WHEN m.current_balance<0 THEN 'negative'
                    WHEN m.current_balance>0 AND m.last_consume_date<CURRENT_DATE-90 THEN 'dormant'
                    WHEN m.current_balance>=5000 THEN 'high' ELSE 'normal' END balance_status
        FROM dim.dim_member m
        LEFT JOIN dim.dim_store s ON s.store_code=m.register_store
        LEFT JOIN dim.dim_warehouse w ON w.warehouse_code=UPPER(m.register_store)
        WHERE {where_sql}
        ORDER BY {"m.current_balance DESC NULLS LAST,m.last_consume_date NULLS FIRST,m.member_no" if can_view_member_sensitive else "m.member_no"}
        LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
    items=[]
    for row in rows:
        item=dict(row)
        if not show_sensitive: item["phone"]=_mask_member_key(item.get("phone"))
        item["current_balance"]=round(_num(item.get("current_balance")),2)
        item["total_amount"]=round(_num(item.get("total_amount")),2); item["last_consume_date"]=_date_str(item.get("last_consume_date")); item["balance_updated_at"]=_time_str(item.get("balance_updated_at"))
        if not can_view_member_sensitive:
            item = _redact_member_fields(item, ("current_balance", "total_amount", "total_count", "last_consume_date", "balance_updated_at", "balance_status"))
        items.append(item)
    if show_sensitive: await _audit_sensitive_phone_view(db,current_user,"member/assets/list")
    if can_view_member_sensitive:
        await _audit_sensitive_data_access(db,current_user,"sensitive_balance.view","member/assets/list",["current_balance","total_amount"])
    return {"success": True, "data": {"items": items,"total": int(total),"page": page,"page_size": page_size,"phone_masked": not show_sensitive,"sensitive_redacted":not can_view_member_sensitive}}


@router.get("/assets/transactions")
async def list_member_asset_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_code: Optional[str] = None,
    business_type: Optional[str] = None,
    keyword: Optional[str] = None,
    include_sensitive: bool = False,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    if not await _has_permission(db, current_user, "member:sensitive:view"):
        raise HTTPException(status_code=403, detail="无会员敏感数据查看权限")
    show_sensitive=await _can_view_sensitive_phone(db,current_user,include_sensitive)
    codes=await _allowed_member_codes(db,current_user)
    if not codes:
        return {"success":True,"data":{"items":[],"total":0,"page":page,"page_size":page_size,"phone_masked":True}}
    end=date.fromisoformat(end_date) if end_date else date.today(); start=date.fromisoformat(start_date) if start_date else end.replace(day=1)
    conditions=["l.biz_date BETWEEN :start AND :end","UPPER(l.store_code)=ANY(:codes)"]; params:dict[str,Any]={"start":start,"end":end,"codes":codes,"limit":page_size,"offset":(page-1)*page_size}
    if store_code:
        if store_code.upper() not in codes:
            return {"success":False,"message":"门店不在当前用户VIP数据范围"}
        conditions.append("UPPER(l.store_code)=:store_code"); params["store_code"]=store_code.upper()
    if business_type: conditions.append("l.business_type=:business_type"); params["business_type"]=business_type
    if keyword and keyword.strip():
        phone_search=" OR l.customer_phone ILIKE :kw" if show_sensitive else ""
        conditions.append(f"(l.member_no ILIKE :kw OR m.member_name ILIKE :kw{phone_search})"); params["kw"]=f"%{keyword.strip()}%"
    where_sql=" AND ".join(conditions); total=(await db.execute(text(f"SELECT COUNT(*) FROM dwd.dwd_baison_member_deposit_log l LEFT JOIN dim.dim_member m ON m.member_no=l.member_no WHERE {where_sql}"),params)).scalar() or 0
    rows=(await db.execute(text(f"""SELECT l.source_log_id,l.member_no,m.member_name,COALESCE(m.phone,l.customer_phone) phone,l.store_code,l.store_name,l.business_type,l.money_before,l.money_change,l.money_after,l.occurred_at,l.biz_date,l.remark FROM dwd.dwd_baison_member_deposit_log l LEFT JOIN dim.dim_member m ON m.member_no=l.member_no WHERE {where_sql} ORDER BY l.occurred_at DESC,l.id DESC LIMIT :limit OFFSET :offset"""),params)).mappings().all()
    items=[]
    for row in rows:
        item=dict(row)
        if not show_sensitive: item["phone"]=_mask_member_key(item.get("phone"))
        item["biz_date"]=_date_str(item.get("biz_date")); item["occurred_at"]=_time_str(item.get("occurred_at"))
        for key in ("money_before","money_change","money_after"): item[key]=round(_num(item.get(key)),2)
        items.append(item)
    if show_sensitive: await _audit_sensitive_phone_view(db,current_user,"member/assets/transactions")
    await _audit_sensitive_data_access(db,current_user,"sensitive_transaction.view","member/assets/transactions",["money_before","money_change","money_after"])
    return {"success":True,"data":{"items":items,"total":int(total),"page":page,"page_size":page_size,"date_range":{"start_date":str(start),"end_date":str(end)},"phone_masked":not show_sensitive}}


@router.get("/actions/overview")
async def member_action_overview(
    days: int = Query(30, ge=1, le=365),
    current_user: SysUser = Depends(require_permission("member:sensitive:view")),
    db: AsyncSession = Depends(get_db),
):
    codes = await _allowed_member_codes(db, current_user)
    data = await get_member_action_overview(db, store_codes=codes, days=days)
    await _audit_sensitive_data_access(
        db, current_user, "member_action.view", "member/actions/overview",
        ["member_no", "followup_result", "conversion_amount"],
    )
    return {"success": True, "data": data}


@router.get("/actions/list")
async def member_action_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(draft|pending|processing|feedback_submitted|review_passed|overdue|closed|cancelled)$"),
    keyword: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("member:sensitive:view")),
    db: AsyncSession = Depends(get_db),
):
    codes = await _allowed_member_codes(db, current_user)
    data = await list_member_actions(
        db, store_codes=codes, page=page, page_size=page_size, status=status, keyword=keyword,
    )
    await _audit_sensitive_data_access(
        db, current_user, "member_action.view", "member/actions/list",
        ["member_no", "contact_reason", "recommended_products"],
    )
    return {"success": True, "data": data}


@router.post("/actions/rebuild")
async def rebuild_member_actions(
    calc_date: Optional[date] = None,
    current_user: SysUser = Depends(require_permission("member:segment:rebuild")),
    db: AsyncSession = Depends(get_db),
):
    codes = await _allowed_member_codes(db, current_user)
    result = await generate_member_action_drafts(
        db, store_codes=codes, calc_date=calc_date, creator_id=int(current_user.id),
    )
    db.add(SysOperationLog(
        user_id=current_user.id,
        username=current_user.username,
        module="member",
        action="member_action.rebuild",
        target_type="member_action",
        target_id=result.get("calc_date"),
        after_data=result,
    ))
    return {"success": True, "data": result}
