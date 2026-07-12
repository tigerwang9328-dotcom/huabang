"""Synchronize Baison member deposit logs for stored-value diagnosis."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.integrations.baison.client import BaisonClient


DEPOSIT_METHOD = "crm.vip.get_deposit_list"
BEIJING = ZoneInfo("Asia/Shanghai")
BUSINESS_TYPES = {"0": "recharge", "2": "consume", "8": "adjustment"}


def _text(value: Any) -> str | None:
    result = str(value or "").strip()
    return result or None


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _datetime(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=BEIJING)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=BEIJING) if parsed.tzinfo is None else parsed.astimezone(BEIJING)
    except ValueError:
        return None


def _body(response: Any) -> dict[str, Any]:
    payload = response.data or {}
    if not isinstance(payload, dict):
        raise RuntimeError("Baison deposit response is not an object")
    if str(payload.get("flag", "")).lower() != "success" and str(payload.get("code", "")) not in {"1", "200"}:
        raise RuntimeError(str(payload.get("message") or "Baison deposit request failed"))
    body = payload.get("data") or {}
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise RuntimeError("Baison deposit data is not an object")
    return body


def normalize_deposit_log(raw: dict[str, Any]) -> dict[str, Any]:
    occurred_at = _datetime(raw.get("init_time") or raw.get("is_add_time"))
    source_log_id = _text(raw.get("customer_deposit_log_id"))
    member_no = _text(raw.get("vip_code")) or _text(raw.get("customer_code"))
    store_code = (_text(raw.get("shop_code")) or "").upper()
    change_type = _text(raw.get("change_type")) or "unknown"
    if not occurred_at or not member_no or not store_code:
        raise ValueError("Baison deposit log misses member, store, or time")
    identity = source_log_id or "|".join([
        member_no, store_code, change_type, occurred_at.isoformat(),
        str(raw.get("money_change") or ""), _text(raw.get("record_code")) or "",
    ])
    return {
        "line_key": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "source_log_id": source_log_id,
        "member_no": member_no,
        "customer_code": _text(raw.get("customer_code")),
        "customer_phone": _text(raw.get("customer_tel")),
        "store_code": store_code,
        "store_name": _text(raw.get("shop_name")),
        "change_type": change_type,
        "business_type": BUSINESS_TYPES.get(change_type, "other"),
        "money_before": _decimal(raw.get("money_before")),
        "money_change": _decimal(raw.get("money_change") if raw.get("money_change") is not None else raw.get("ZJE")),
        "money_after": _decimal(raw.get("money_after")),
        "record_code": _text(raw.get("record_code")),
        "occurred_at": occurred_at,
        "biz_date": occurred_at.date(),
        "remark": _text(raw.get("remark")),
        "raw_json": json.dumps(raw, ensure_ascii=False, default=str),
    }


class BaisonMemberDepositService:
    def __init__(self, client: BaisonClient | None = None, page_size: int = 100):
        self.client = client or BaisonClient()
        self.page_size = page_size

    def fetch_logs(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        logs: list[dict[str, Any]] = []
        page = 1
        fetched = 0
        total: int | None = None
        while total is None or fetched < total:
            response = self.client.request(DEPOSIT_METHOD, {
                "pageNum": str(page),
                "num": str(self.page_size),
                "start_time": datetime.combine(start_date, time.min).strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": datetime.combine(end_date, time.max).strftime("%Y-%m-%d %H:%M:%S"),
            }, timeout=30)
            rows = _body(response).get("data") or []
            if not isinstance(rows, list):
                raise RuntimeError("Baison deposit list is not an array")
            if rows and total is None:
                total = int(float(rows[0].get("tCount") or len(rows)))
            fetched += len(rows)
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                if (_text(raw.get("shop_code")) or "").upper() not in ALLOWED_STORE_CODES:
                    continue
                try:
                    logs.append(normalize_deposit_log(raw))
                except ValueError:
                    continue
            if not rows or len(rows) < self.page_size:
                break
            page += 1
        return logs


async def sync_member_deposits(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    logs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if logs is None:
        logs = await asyncio.to_thread(BaisonMemberDepositService().fetch_logs, start_date, end_date)
    logs = [log for log in logs if log.get("store_code") in ALLOWED_STORE_CODES]
    upsert = text("""
      INSERT INTO dwd.dwd_baison_member_deposit_log (
        line_key, source_log_id, member_no, customer_code, customer_phone,
        store_code, store_name, change_type, business_type,
        money_before, money_change, money_after, record_code,
        occurred_at, biz_date, remark, raw_json, synced_at
      ) VALUES (
        :line_key, :source_log_id, :member_no, :customer_code, :customer_phone,
        :store_code, :store_name, :change_type, :business_type,
        :money_before, :money_change, :money_after, :record_code,
        :occurred_at, :biz_date, :remark, CAST(:raw_json AS jsonb), now()
      ) ON CONFLICT (line_key) DO UPDATE SET
        member_no=EXCLUDED.member_no, store_code=EXCLUDED.store_code,
        change_type=EXCLUDED.change_type, business_type=EXCLUDED.business_type,
        money_before=EXCLUDED.money_before, money_change=EXCLUDED.money_change,
        money_after=EXCLUDED.money_after, raw_json=EXCLUDED.raw_json, synced_at=now()
    """)
    for offset in range(0, len(logs), 1000):
        await db.execute(upsert, logs[offset:offset + 1000])
    await db.execute(text("DELETE FROM dws.dws_member_deposit_daily WHERE biz_date BETWEEN :start_date AND :end_date"), {"start_date": start_date, "end_date": end_date})
    await db.execute(text("""
      INSERT INTO dws.dws_member_deposit_daily (
        biz_date, store_code, recharge_count, recharge_member_count, recharge_amount,
        avg_recharge_amount, consume_count, consume_member_count, consume_amount,
        adjustment_amount, updated_at
      )
      SELECT biz_date, store_code,
        count(*) FILTER (WHERE change_type='0'),
        count(DISTINCT member_no) FILTER (WHERE change_type='0'),
        coalesce(sum(money_change) FILTER (WHERE change_type='0'),0),
        coalesce(avg(money_change) FILTER (WHERE change_type='0'),0),
        count(*) FILTER (WHERE change_type='2'),
        count(DISTINCT member_no) FILTER (WHERE change_type='2'),
        coalesce(sum(abs(money_change)) FILTER (WHERE change_type='2'),0),
        coalesce(sum(money_change) FILTER (WHERE change_type NOT IN ('0','2')),0), now()
      FROM dwd.dwd_baison_member_deposit_log
      WHERE biz_date BETWEEN :start_date AND :end_date
      GROUP BY biz_date, store_code
    """), {"start_date": start_date, "end_date": end_date})
    await db.flush()
    return {"ok": True, "log_count": len(logs), "start_date": start_date, "end_date": end_date}
