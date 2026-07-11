"""Synchronize Baison CRM member profiles into Huabang member tables."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from typing import Any
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.integrations.baison.client import BaisonClient


MEMBER_METHOD = "crm.vip.get_list"
MEMBER_FIELDS = (
    "vip_code,customer_code,tel,level_code,vip_integral,consume_money,"
    "shop_code,last_consume_time"
)


def _text(value: Any) -> str | None:
    result = str(value or "").strip()
    return result or None


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _date(value: Any) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def normalize_member(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Baison's legacy CRM field names to Huabang's member schema."""
    member_no = _text(raw.get("DM")) or _text(raw.get("GKDM"))
    if not member_no:
        raise ValueError("Baison member number is missing")
    status_code = _text(raw.get("STATUS"))
    return {
        "member_no": member_no,
        "member_name": _text(raw.get("customer_name")) or _text(raw.get("MC")),
        "phone": _text(raw.get("SJ")) or _text(raw.get("YSJ")),
        "gender": _text(raw.get("SEX")),
        "birthday": _date(raw.get("SR")),
        "register_date": _date(raw.get("JDRQ")),
        "register_store": _text(raw.get("CKDM")),
        "member_level": _text(raw.get("KLDM")) or _text(raw.get("XLDM")),
        "total_amount": _number(raw.get("XFJE")),
        "total_count": _integer(raw.get("XFCS")),
        "last_consume_date": _date(raw.get("ZJRQ")) or _date(raw.get("SCRQ")),
        "last_consume_store": _text(raw.get("ZJSD")) or _text(raw.get("SCSD")),
        "status": "active" if status_code in (None, "1") else "inactive",
        "raw_json": raw,
    }


def deduplicate_members(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one deterministic current record per Baison member number."""
    current: dict[str, dict[str, Any]] = {}

    def rank(member: dict[str, Any]) -> tuple[str, str]:
        raw = member.get("raw_json") or {}
        changed = _text(raw.get("XGRQ")) or ""
        consumed = str(member.get("last_consume_date") or "")
        return changed, consumed

    for member in members:
        member_no = member["member_no"]
        existing = current.get(member_no)
        if existing is None or rank(member) >= rank(existing):
            current[member_no] = member
    return [current[key] for key in sorted(current)]


def _response_body(response: Any) -> dict[str, Any]:
    payload = response.data or {}
    if not isinstance(payload, dict):
        raise RuntimeError("Baison member response is not an object")
    if str(payload.get("flag", "")).upper() != "SUCCESS" and str(payload.get("code", "")) not in {"1", "200"}:
        raise RuntimeError(str(payload.get("message") or "Baison member request failed"))
    body = payload.get("data") or {}
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise RuntimeError("Baison member data is not an object")
    return body


class BaisonMemberService:
    def __init__(self, client: BaisonClient | None = None, page_size: int = 200):
        self.client = client or BaisonClient()
        self.page_size = page_size

    def fetch_all_members(self) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        page = 1
        expected_total: int | None = None
        while expected_total is None or len(members) < expected_total:
            response = self.client.request(
                MEMBER_METHOD,
                {"fields": MEMBER_FIELDS, "pageNum": page, "num": self.page_size},
            )
            body = _response_body(response)
            rows = body.get("vip") or []
            if not isinstance(rows, list):
                raise RuntimeError("Baison member list is not an array")
            expected_total = _integer(body.get("count"))
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                try:
                    members.append(normalize_member(raw))
                except ValueError:
                    continue
            if not rows or len(rows) < self.page_size:
                break
            page += 1
        return members


async def sync_members(
    db: AsyncSession,
    members: list[dict[str, Any]] | None = None,
    page_size: int = 200,
) -> dict[str, Any]:
    """Fetch and upsert Baison members into ODS and DIM in one transaction."""
    if members is None:
        service = BaisonMemberService(page_size=page_size)
        members = await asyncio.to_thread(service.fetch_all_members)
    members = deduplicate_members(members)
    batch_no = "BAISON_MEMBER_" + datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6].upper()

    rows = []
    for member in members:
        rows.append({
            **{key: value for key, value in member.items() if key != "raw_json"},
            "raw_json": json.dumps(member.get("raw_json") or {}, ensure_ascii=False, default=str),
            "batch_no": batch_no,
        })

    ods_sql = text("""
        INSERT INTO ods.ods_baison_member (
            batch_no, member_no, member_name, phone, gender, birthday,
            register_date, register_store, member_level, total_amount,
            total_count, last_consume_date, last_consume_store,
            raw_json, source, imported_at, created_at
        ) VALUES (
            :batch_no, :member_no, :member_name, :phone, :gender, :birthday,
            :register_date, :register_store, :member_level, :total_amount,
            :total_count, :last_consume_date, :last_consume_store,
            :raw_json, 'baison', now(), now()
        )
        ON CONFLICT (member_no, batch_no) DO UPDATE SET
            member_name = EXCLUDED.member_name,
            phone = EXCLUDED.phone,
            total_amount = EXCLUDED.total_amount,
            total_count = EXCLUDED.total_count,
            last_consume_date = EXCLUDED.last_consume_date,
            last_consume_store = EXCLUDED.last_consume_store,
            raw_json = EXCLUDED.raw_json,
            imported_at = now()
    """)
    dim_sql = text("""
        INSERT INTO dim.dim_member (
            member_no, member_name, phone, gender, birthday,
            register_date, register_store, member_level, total_amount,
            total_count, last_consume_date, last_consume_store,
            status, updated_at
        ) VALUES (
            :member_no, :member_name, :phone, :gender, :birthday,
            :register_date, :register_store, :member_level, :total_amount,
            :total_count, :last_consume_date, :last_consume_store,
            :status, now()
        )
        ON CONFLICT (member_no) DO UPDATE SET
            member_name = EXCLUDED.member_name,
            phone = EXCLUDED.phone,
            gender = EXCLUDED.gender,
            birthday = EXCLUDED.birthday,
            register_date = EXCLUDED.register_date,
            register_store = EXCLUDED.register_store,
            member_level = EXCLUDED.member_level,
            total_amount = EXCLUDED.total_amount,
            total_count = EXCLUDED.total_count,
            last_consume_date = EXCLUDED.last_consume_date,
            last_consume_store = EXCLUDED.last_consume_store,
            status = EXCLUDED.status,
            updated_at = now()
    """)
    for offset in range(0, len(rows), 1000):
        chunk = rows[offset:offset + 1000]
        await db.execute(ods_sql, chunk)
        await db.execute(dim_sql, chunk)
    if rows:
        await db.execute(
            text("DELETE FROM ods.ods_baison_member WHERE batch_no <> :batch_no"),
            {"batch_no": batch_no},
        )
    await db.flush()
    return {"ok": True, "batch_no": batch_no, "member_count": len(rows)}


async def rebuild_member_visits(
    db: AsyncSession,
    store_codes: list[str] | None = None,
    limit_per_store: int = 50,
) -> dict[str, Any]:
    """Build a bounded daily follow-up pool from high-value sleeping members."""
    stores = sorted(set(store_codes or ALLOWED_STORE_CODES))
    await db.execute(
        text("""
            DELETE FROM dm.dm_member_visit_list
            WHERE visit_date = CURRENT_DATE
              AND visit_status = 'pending'
              AND store_code = ANY(:store_codes)
        """),
        {"store_codes": stores},
    )
    result = await db.execute(
        text("""
            INSERT INTO dm.dm_member_visit_list (
                visit_date, member_no, store_code, visit_reason, priority,
                last_consume_date, sleep_days, ai_suggestion,
                visit_status, is_converted, conversion_amount, generated_at
            )
            WITH candidates AS (
                SELECT
                    m.member_no,
                    COALESCE(m.last_consume_store, m.register_store) AS store_code,
                    m.last_consume_date,
                    CASE WHEN m.last_consume_date IS NULL THEN 9999
                         ELSE CURRENT_DATE - m.last_consume_date END AS sleep_days,
                    COALESCE(m.total_amount, 0) AS total_amount,
                    ROW_NUMBER() OVER (
                        PARTITION BY COALESCE(m.last_consume_store, m.register_store)
                        ORDER BY COALESCE(m.total_amount, 0) DESC,
                                 m.last_consume_date ASC NULLS FIRST,
                                 m.member_no
                    ) AS store_rank
                FROM dim.dim_member m
                WHERE m.status = 'active'
                  AND COALESCE(m.last_consume_store, m.register_store) = ANY(:store_codes)
                  AND (m.last_consume_date < CURRENT_DATE - INTERVAL '90 day'
                       OR m.last_consume_date IS NULL)
                  AND NOT EXISTS (
                      SELECT 1 FROM dm.dm_member_visit_list v
                      WHERE v.visit_date = CURRENT_DATE
                        AND v.member_no = m.member_no
                  )
            )
            SELECT
                CURRENT_DATE,
                member_no,
                store_code,
                CASE WHEN sleep_days = 9999 THEN '长期未消费会员'
                     ELSE CONCAT('沉睡', sleep_days, '天会员') END,
                CASE WHEN total_amount >= 5000 OR sleep_days >= 365 THEN 1
                     WHEN total_amount >= 2000 OR sleep_days >= 180 THEN 2
                     ELSE 3 END,
                last_consume_date,
                sleep_days,
                CASE WHEN total_amount >= 5000
                     THEN '优先由店长回访，结合新品、生日或储值权益定向唤醒。'
                     ELSE '由原消费门店回访，确认尺码偏好并推荐近期适配商品。' END,
                'pending', false, 0, now()
            FROM candidates
            WHERE store_rank <= :limit_per_store
        """),
        {"store_codes": stores, "limit_per_store": limit_per_store},
    )
    await db.flush()
    return {"ok": True, "visit_count": max(result.rowcount, 0), "store_count": len(stores)}
