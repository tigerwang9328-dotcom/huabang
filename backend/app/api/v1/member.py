"""会员运营接口。

当前会员档案和回访名单表可能为空；页面先展示百胜小票中可识别的会员线索，
等会员主档同步后再自然启用档案和回访数据。
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.data_scope import get_data_scope
from app.core.database import get_db
from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.models.sys import SysUser

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


@router.get("/overview")
async def member_overview(
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """会员运营概览：档案表、回访表、小票会员线索三个层面的状态。"""
    try:
        store_codes = await _allowed_store_codes(db, current_user)
        if not store_codes:
            return {"success": True, "data": {"summary": {}, "data_status": {"has_store_access": False}}}

        dim_members = await _table_count(db, "dim", "dim_member")
        ods_members = await _table_count(db, "ods", "ods_baison_member")

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
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """会员档案分页。"""
    try:
        conditions = ["1=1"]
        params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
        if keyword and keyword.strip():
            params["kw"] = f"%{keyword.strip()}%"
            conditions.append("(m.member_no ILIKE :kw OR m.member_name ILIKE :kw OR m.phone ILIKE :kw)")
        if member_level:
            params["member_level"] = member_level
            conditions.append("m.member_level = :member_level")
        if status:
            params["status"] = status
            conditions.append("m.status = :status")
        where_sql = " AND ".join(conditions)
        total = (await db.execute(text(f"SELECT COUNT(*) FROM dim.dim_member m WHERE {where_sql}"), params)).scalar() or 0
        rows = (await db.execute(text(f"""
            SELECT m.member_no, m.member_name, m.phone, m.gender, m.birthday,
                   m.register_date, m.register_store, COALESCE(s.store_name, m.register_store) AS register_store_name,
                   m.member_level, m.total_amount, m.total_count, m.last_consume_date,
                   m.last_consume_store, m.rfm_score, m.rfm_segment, m.status, m.updated_at
            FROM dim.dim_member m
            LEFT JOIN dim.dim_store s ON s.store_code = m.register_store
            WHERE {where_sql}
            ORDER BY m.last_consume_date DESC NULLS LAST, m.total_amount DESC NULLS LAST, m.member_no
            LIMIT :limit OFFSET :offset
        """), params)).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            item["phone"] = _mask_member_key(item.get("phone"))
            item["total_amount"] = round(_num(item.get("total_amount")), 2)
            item["rfm_score"] = round(_num(item.get("rfm_score")), 2)
            item["birthday"] = _date_str(item.get("birthday"))
            item["register_date"] = _date_str(item.get("register_date"))
            item["last_consume_date"] = _date_str(item.get("last_consume_date"))
            item["updated_at"] = _time_str(item.get("updated_at"))
            items.append(item)
        return {"success": True, "data": {"items": items, "total": int(total), "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("member list error")
        return {"success": False, "message": "会员档案查询失败，请查看服务日志"}


@router.get("/visits")
async def list_member_visits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    visit_status: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("sales:store:view")),
    db: AsyncSession = Depends(get_db),
):
    """会员回访名单分页。"""
    try:
        conditions = ["1=1"]
        params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
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
            item["phone"] = _mask_member_key(item.get("phone"))
            item["visit_date"] = _date_str(item.get("visit_date"))
            item["last_consume_date"] = _date_str(item.get("last_consume_date"))
            item["visited_at"] = _time_str(item.get("visited_at"))
            item["conversion_amount"] = round(_num(item.get("conversion_amount")), 2)
            items.append(item)
        return {"success": True, "data": {"items": items, "total": int(total), "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("member visits error")
        return {"success": False, "message": "会员回访查询失败，请查看服务日志"}
