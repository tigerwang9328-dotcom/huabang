"""Synchronize Baison transfer arrivals used by FIFO inventory ageing."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_INVENTORY_CODES
from app.integrations.baison.client import BaisonClient
from app.integrations.baison.services.product_inbound_service import (
    _date,
    _decimal,
    _response_body,
    _text,
    _total,
)


HEADER_METHOD = "drp.dbd.get_list"
DETAIL_METHOD = "drp.dbd.get_detail"
TRANSFER_TYPES = (3, 9, 10)


def normalize_transfer_inbound_line(header: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    record_code = _text(header.get("djbh")) or _text(header.get("record_code"))
    record_date = _date(header.get("rq")) or _date(header.get("ysrq"))
    warehouse_code = (_text(header.get("in_ckdm")) or "").upper()
    product_code = _text(detail.get("goods_sn")) or _text(detail.get("goods_code"))
    if not record_code or not record_date or not warehouse_code or not product_code:
        raise ValueError("Baison transfer line misses record, date, destination, or product")

    received = _decimal(detail.get("sl2"))
    quantity = received if received > 0 else _decimal(detail.get("sl"))
    cost_unit = _decimal(detail.get("bzj"))
    identity = "|".join(filter(None, [
        "transfer", record_code, warehouse_code, product_code,
        _text(detail.get("color_code")), _text(detail.get("size_code")),
        _text(detail.get("barcode")),
    ]))
    return {
        "line_key": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "record_code": record_code,
        "record_date": record_date,
        "transfer_type": int(header.get("ywlx") or 0),
        "source_warehouse_code": (_text(header.get("out_ckdm")) or "").upper() or None,
        "warehouse_code": warehouse_code,
        "warehouse_name": _text(header.get("in_ckmc")),
        "product_code": product_code,
        "product_name": _text(detail.get("goods_name")),
        "sku_code": _text(detail.get("sku")),
        "color_code": _text(detail.get("color_code")),
        "size_code": _text(detail.get("size_code")),
        "barcode": _text(detail.get("barcode")),
        "quantity": quantity,
        "cost_unit": cost_unit if cost_unit > 0 else None,
        "cost_amount": quantity * cost_unit,
        "raw_json": json.dumps({"header": header, "detail": detail}, ensure_ascii=False, default=str),
    }


def merge_transfer_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for line in lines:
        key = line["line_key"]
        if key not in merged:
            merged[key] = line.copy()
            continue
        merged[key]["quantity"] = _decimal(merged[key]["quantity"]) + _decimal(line["quantity"])
        merged[key]["cost_amount"] = _decimal(merged[key]["cost_amount"]) + _decimal(line["cost_amount"])
    return list(merged.values())


class BaisonProductTransferInboundService:
    def __init__(self, client: BaisonClient | None = None, page_size: int = 100):
        self.client = client or BaisonClient()
        self.page_size = page_size

    def _fetch_headers(self, start_date: date, end_date: date, transfer_type: int) -> list[dict[str, Any]]:
        headers: list[dict[str, Any]] = []
        page = 1
        total: int | None = None
        while total is None or len(headers) < total:
            body = _response_body(self.client.request(HEADER_METHOD, {
                "rq_start": f"{start_date.isoformat()} 00:00:00",
                "rq_end": f"{end_date.isoformat()} 23:59:59",
                "page": page,
                "page_size": self.page_size,
                "opt_user_code": "admin",
                "status": "4,6",
                "ywlx": transfer_type,
            }))
            page_rows = body.get("data") or []
            if not isinstance(page_rows, list):
                page_rows = []
            headers.extend(row for row in page_rows if isinstance(row, dict))
            total = _total(body, len(headers))
            if not page_rows or len(page_rows) < self.page_size:
                break
            page += 1
        return headers

    def _fetch_details(self, record_code: str) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []
        page = 1
        total: int | None = None
        while total is None or len(details) < total:
            body = _response_body(self.client.request(DETAIL_METHOD, {
                "record_code": record_code,
                "page": page,
                "page_size": self.page_size,
                "opt_user_code": "admin",
            }))
            page_rows = body.get("out") or []
            if not isinstance(page_rows, list):
                page_rows = []
            details.extend(row for row in page_rows if isinstance(row, dict))
            filter_data = body.get("out_filter") or {}
            total = _total(filter_data, len(details)) if isinstance(filter_data, dict) else len(details)
            if not page_rows or len(page_rows) < self.page_size:
                break
            page += 1
        return details

    def fetch_inbound_lines(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for transfer_type in TRANSFER_TYPES:
            for header in self._fetch_headers(start_date, end_date, transfer_type):
                warehouse_code = (_text(header.get("in_ckdm")) or "").upper()
                if warehouse_code not in ALLOWED_INVENTORY_CODES:
                    continue
                header = {**header, "ywlx": transfer_type}
                record_code = _text(header.get("djbh"))
                if not record_code:
                    continue
                for detail in self._fetch_details(record_code):
                    try:
                        line = normalize_transfer_inbound_line(header, detail)
                    except ValueError:
                        continue
                    if _decimal(line["quantity"]) > 0:
                        lines.append(line)
        return merge_transfer_lines(lines)


async def sync_product_transfer_inbound(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    lines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if lines is None:
        lines = await asyncio.to_thread(
            BaisonProductTransferInboundService().fetch_inbound_lines, start_date, end_date
        )
    lines = merge_transfer_lines(lines)
    upsert = text("""
        INSERT INTO dwd.dwd_baison_transfer_inbound (
          line_key, record_code, record_date, transfer_type, source_warehouse_code,
          warehouse_code, warehouse_name, product_code, product_name, sku_code,
          color_code, size_code, barcode, quantity, cost_unit, cost_amount,
          raw_json, synced_at
        ) VALUES (
          :line_key, :record_code, :record_date, :transfer_type, :source_warehouse_code,
          :warehouse_code, :warehouse_name, :product_code, :product_name, :sku_code,
          :color_code, :size_code, :barcode, :quantity, :cost_unit, :cost_amount,
          CAST(:raw_json AS jsonb), now()
        ) ON CONFLICT (line_key) DO UPDATE SET
          quantity=EXCLUDED.quantity, cost_unit=EXCLUDED.cost_unit,
          cost_amount=EXCLUDED.cost_amount, raw_json=EXCLUDED.raw_json, synced_at=now()
    """)
    for offset in range(0, len(lines), 1000):
        await db.execute(upsert, lines[offset:offset + 1000])
    await db.flush()
    return {"ok": True, "line_count": len(lines), "start_date": start_date, "end_date": end_date}
