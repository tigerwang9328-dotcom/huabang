"""Synchronize Baison monthly store sales targets."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.integrations.baison.client import BaisonClient

METHOD = "pos.storefx.store_yj_get"


def _decimal(value: Any) -> Decimal:
    try: return Decimal(str(value or 0))
    except Exception: return Decimal("0")


def normalize_store_target(raw: dict[str, Any], month_date: date, snapshot_date: date | None = None) -> dict[str, Any]:
    code = str(raw.get("zddm") or "").strip()
    if not code: raise ValueError("store code missing")
    rate_raw = str(raw.get("dbl") or "0").strip().rstrip("%")
    return {"snapshot_date": snapshot_date or date.today(), "month_date": month_date, "store_code": code, "store_name": str(raw.get("zdmc") or code),
            "target_amount": _decimal(raw.get("ydzb")), "actual_amount": _decimal(raw.get("ydxs")),
            "achievement_rate": _decimal(rate_raw) / Decimal("100"), "raw_json": json.dumps(raw, ensure_ascii=False, default=str)}


class BaisonStoreTargetService:
    def __init__(self, client: BaisonClient | None = None): self.client = client or BaisonClient()
    def fetch_targets(self, year: int, month: int, snapshot_date: date | None = None) -> list[dict[str, Any]]:
        result = []
        month_date = date(year, month, 1)
        for code in sorted(ALLOWED_STORE_CODES):
            response = self.client.request(METHOD, {"zddm": code, "year": year, "month": month})
            payload = response.data or {}
            if str(payload.get("code")) != "1": raise RuntimeError(str(payload.get("message") or "target request failed"))
            rows = payload.get("data") or []
            if isinstance(rows, str): rows = json.loads(rows)
            for raw in rows if isinstance(rows, list) else []:
                row = normalize_store_target(raw, month_date, snapshot_date=snapshot_date)
                if row["store_code"] in ALLOWED_STORE_CODES: result.append(row)
        return result


async def sync_store_targets(db: AsyncSession, year: int, month: int, rows=None, snapshot_date: date | None = None) -> dict[str, Any]:
    if rows is None:
        fetch = BaisonStoreTargetService().fetch_targets
        rows = await asyncio.to_thread(fetch, year, month, snapshot_date) if snapshot_date else await asyncio.to_thread(fetch, year, month)
    sql = text("""INSERT INTO dws.dws_store_target_monthly(snapshot_date,month_date,store_code,store_name,target_amount,actual_amount,achievement_rate,raw_json,updated_at)
      VALUES(:snapshot_date,:month_date,:store_code,:store_name,:target_amount,:actual_amount,:achievement_rate,CAST(:raw_json AS jsonb),now())
      ON CONFLICT(snapshot_date,month_date,store_code) DO UPDATE SET store_name=excluded.store_name,target_amount=excluded.target_amount,
      actual_amount=excluded.actual_amount,achievement_rate=excluded.achievement_rate,raw_json=excluded.raw_json,updated_at=now()""")
    if rows: await db.execute(sql, rows)
    await db.flush()
    return {"ok": True, "store_count": len(rows), "year": year, "month": month}
