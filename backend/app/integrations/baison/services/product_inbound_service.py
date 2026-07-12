"""Synchronize Baison purchase receipts for product lifecycle diagnosis."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_INVENTORY_CODES
from app.integrations.baison.client import BaisonClient


HEADER_METHOD = "pms.spjhd.get_list"
DETAIL_METHOD = "pms.spjhd.mx_get_list"


def _text(value: Any) -> str | None:
    if isinstance(value, list):
        value = next((item for item in value if str(item or "").strip()), "")
    value = str(value or "").strip()
    return value or None


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _date(value: Any) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _response_body(response: Any) -> dict[str, Any]:
    payload = response.data or {}
    if not isinstance(payload, dict):
        raise RuntimeError("Baison purchase response is not an object")
    if str(payload.get("flag", "")).upper() != "SUCCESS" and str(payload.get("code", "")) not in {"1", "200"}:
        raise RuntimeError(str(payload.get("message") or "Baison purchase request failed"))
    body = payload.get("data") or {}
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise RuntimeError("Baison purchase data is not an object")
    return body


def _rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("data", "list", "rows", "result", "record", "mx"):
        value = body.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = _rows(value)
            if nested:
                return nested
    return []


def _total(body: dict[str, Any], fallback: int) -> int:
    for key in ("total", "count", "records", "totalCount", "record_count"):
        value = body.get(key)
        if value is not None:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                pass
    for value in body.values():
        if isinstance(value, dict):
            nested = _total(value, -1)
            if nested >= 0:
                return nested
    return fallback


def normalize_inbound_line(header: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    record_code = _text(header.get("record_code")) or _text(header.get("djbh"))
    product_code = _text(detail.get("goods_code")) or _text(detail.get("spdm"))
    record_date = _date(header.get("record_time")) or _date(header.get("service_time"))
    if not record_code or not product_code or not record_date:
        raise ValueError("Baison purchase line misses record, product, or date")
    warehouse_code = (_text(header.get("store_code")) or _text(header.get("ckdm")) or "").upper()
    sku_code = _text(detail.get("sku")) or _text(detail.get("barcode"))
    identity = "|".join(filter(None, [
        record_code, sku_code, product_code, _text(detail.get("spec1_code")),
        _text(detail.get("spec2_code")), _text(detail.get("barcode")),
    ]))
    return {
        "line_key": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "record_code": record_code,
        "record_date": record_date,
        "warehouse_code": warehouse_code,
        "warehouse_name": _text(header.get("store_name")),
        "supplier_code": _text(header.get("supplier_code")),
        "supplier_name": _text(header.get("supplier_name")),
        "product_code": product_code,
        "product_name": _text(detail.get("goods_name")),
        "sku_code": sku_code,
        "color_code": _text(detail.get("spec1_code")),
        "color_name": _text(detail.get("spec1_name")),
        "size_code": _text(detail.get("spec2_code")),
        "size_name": _text(detail.get("spec2_name")),
        "barcode": _text(detail.get("barcode")),
        "quantity": _decimal(detail.get("finish_num") if detail.get("finish_num") is not None else detail.get("num")),
        "purchase_price": _decimal(detail.get("price")),
        "purchase_amount": _decimal(detail.get("money")),
        "raw_json": json.dumps({"header": header, "detail": detail}, ensure_ascii=False, default=str),
    }


def merge_inbound_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine repeated SKU rows within one receipt instead of overwriting quantities."""
    merged: dict[str, dict[str, Any]] = {}
    for line in lines:
        key = line["line_key"]
        if key not in merged:
            merged[key] = line.copy()
            continue
        current = merged[key]
        current["quantity"] = _decimal(current.get("quantity")) + _decimal(line.get("quantity"))
        current["purchase_amount"] = _decimal(current.get("purchase_amount")) + _decimal(line.get("purchase_amount"))
        if current["quantity"]:
            current["purchase_price"] = current["purchase_amount"] / current["quantity"]
    return list(merged.values())


class BaisonProductInboundService:
    def __init__(self, client: BaisonClient | None = None, page_size: int = 100):
        self.client = client or BaisonClient()
        self.page_size = page_size

    def fetch_inbound_lines(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        headers: list[dict[str, Any]] = []
        page = 1
        total: int | None = None
        while total is None or len(headers) < total:
            response = self.client.request(HEADER_METHOD, {
                "record_time_start": start_date.isoformat(),
                "record_time_end": (end_date + timedelta(days=1)).isoformat(),
                "page": page,
                "page_size": self.page_size,
            })
            body = _response_body(response)
            page_rows = _rows(body)
            headers.extend(page_rows)
            total = _total(body, len(headers))
            if not page_rows or len(page_rows) < self.page_size:
                break
            page += 1

        lines: list[dict[str, Any]] = []
        for header in headers:
            warehouse_code = (_text(header.get("store_code")) or "").upper()
            if warehouse_code not in ALLOWED_INVENTORY_CODES:
                continue
            header_date = _date(header.get("record_time")) or _date(header.get("service_time"))
            if not header_date or header_date < start_date or header_date > end_date:
                continue
            record_code = _text(header.get("record_code"))
            if not record_code:
                continue
            details: list[dict[str, Any]] = []
            detail_page = 1
            detail_total: int | None = None
            while detail_total is None or len(details) < detail_total:
                detail_body = _response_body(self.client.request(DETAIL_METHOD, {
                    "record_code": record_code, "page": detail_page, "page_size": self.page_size,
                }))
                page_details = _rows(detail_body)
                details.extend(page_details)
                detail_total = _total(detail_body, len(details))
                if not page_details or len(page_details) < self.page_size:
                    break
                detail_page += 1
            for detail in details:
                try:
                    lines.append(normalize_inbound_line(header, detail))
                except ValueError:
                    continue
        return lines


async def sync_product_inbound(
    db: AsyncSession,
    start_date: date | None = None,
    end_date: date | None = None,
    lines: list[dict[str, Any]] | None = None,
    history_start_date: date | None = None,
) -> dict[str, Any]:
    end_date = end_date or date.today()
    start_date = start_date or end_date - timedelta(days=13)
    history_start_date = history_start_date or start_date
    if lines is None:
        lines = await asyncio.to_thread(BaisonProductInboundService().fetch_inbound_lines, start_date, end_date)
    fetched_line_count = len(lines)
    lines = merge_inbound_lines(lines)

    upsert = text("""
        INSERT INTO dwd.dwd_baison_purchase_inbound (
          line_key, record_code, record_date, warehouse_code, warehouse_name,
          supplier_code, supplier_name, product_code, product_name, sku_code,
          color_code, color_name, size_code, size_name, barcode,
          quantity, purchase_price, purchase_amount, raw_json, synced_at
        ) VALUES (
          :line_key, :record_code, :record_date, :warehouse_code, :warehouse_name,
          :supplier_code, :supplier_name, :product_code, :product_name, :sku_code,
          :color_code, :color_name, :size_code, :size_name, :barcode,
          :quantity, :purchase_price, :purchase_amount, CAST(:raw_json AS jsonb), now()
        ) ON CONFLICT (line_key) DO UPDATE SET
          quantity=EXCLUDED.quantity, purchase_price=EXCLUDED.purchase_price,
          purchase_amount=EXCLUDED.purchase_amount, raw_json=EXCLUDED.raw_json, synced_at=now()
    """)
    for offset in range(0, len(lines), 1000):
        await db.execute(upsert, lines[offset:offset + 1000])

    await db.execute(text("""
        INSERT INTO dws.dws_product_inbound_summary (
          product_code, first_inbound_date, last_inbound_date, total_inbound_quantity,
          total_inbound_amount, last_purchase_price, receipt_count, history_start_date, updated_at
        )
        SELECT product_code, min(record_date), max(record_date), sum(quantity), sum(purchase_amount),
          (array_agg(purchase_price ORDER BY record_date DESC, synced_at DESC))[1],
          count(DISTINCT record_code), :history_start_date, now()
        FROM dwd.dwd_baison_purchase_inbound
        GROUP BY product_code
        ON CONFLICT (product_code) DO UPDATE SET
          first_inbound_date=EXCLUDED.first_inbound_date, last_inbound_date=EXCLUDED.last_inbound_date,
          total_inbound_quantity=EXCLUDED.total_inbound_quantity, total_inbound_amount=EXCLUDED.total_inbound_amount,
          last_purchase_price=EXCLUDED.last_purchase_price, receipt_count=EXCLUDED.receipt_count,
          history_start_date=LEAST(dws.dws_product_inbound_summary.history_start_date, EXCLUDED.history_start_date),
          updated_at=now()
    """), {"history_start_date": history_start_date})
    await db.flush()
    return {"ok": True, "line_count": fetched_line_count, "stored_line_count": len(lines), "start_date": start_date, "end_date": end_date}
