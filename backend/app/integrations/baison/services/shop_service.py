"""商店档案（base.shop.get_list）服务。

职责：调用百胜 -> 解析嵌套响应 -> 字段映射 -> upsert 落库 dim.dim_baison_shop -> 写同步日志。

百胜成功响应外层：{"code":"200","flag":"success","data":"<JSON字符串>"}
内层 data（再 json.loads 一层）：{"filter":{...分页...},"data":[{...门店...}]}
失败响应：{"status":"0","message":"接口未授权或授权过期","data":"1"}
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.baison.client import BaisonClient
from app.models.dim import DimBaisonShop
from app.models.log import LogDataSync

logger = logging.getLogger("baison.shop_service")

SHOP_LIST_METHOD = "base.shop.get_list"

SHOP_FIELD_MAP = {
    "sd_id": "shop_id", "sd_code": "shop_code", "sd_name": "shop_name",
    "sdxz": "shop_type", "online_name": "online_type",
    "qddm": "channel_code", "qdmc": "channel_name",
    "lbdm": "category_code", "lbmc": "category_name",
    "qydm": "area_code", "qymc": "area_name",
    "province": "province", "city": "city", "county": "county",
    "dz": "address", "zjf": "price_shop_code", "zk": "discount_rate",
    "ygdm": "employee_code", "lastchanged": "last_changed", "is_qy": "is_enabled",
}


def _build_business_params(page, page_size, start_modified, end_modified) -> dict:
    biz = {"page": str(page), "page_size": str(page_size)}
    if start_modified:
        biz["startModified"] = start_modified
    if end_modified:
        biz["endModified"] = end_modified
    return biz


def _parse_response(data) -> dict:
    out = {"ok": False, "message": "", "filter": {}, "shops": []}
    if not isinstance(data, dict):
        out["message"] = "响应非JSON对象"
        return out
    success_flag = (str(data.get("code")) == "200" and str(data.get("flag")).lower() == "success")
    inner = data.get("data")
    payload = None
    if isinstance(inner, str):
        try:
            payload = json.loads(inner)
        except (json.JSONDecodeError, ValueError):
            payload = None
    elif isinstance(inner, dict):
        payload = inner
    if isinstance(payload, dict):
        out["filter"] = payload.get("filter") or {}
        shops = payload.get("data")
        if isinstance(shops, list):
            out["shops"] = shops
    out["ok"] = success_flag and isinstance(payload, dict)
    out["message"] = data.get("message") or data.get("msg") or ("成功" if out["ok"] else str(data)[:200])
    return out


def fetch_shop_list(page=1, page_size=20, start_modified=None, end_modified=None, client=None) -> dict:
    """同步调用 base.shop.get_list 并解析（不落库）。"""
    client = client or BaisonClient()
    biz = _build_business_params(page, page_size, start_modified, end_modified)
    resp = client.request(SHOP_LIST_METHOD, biz)
    parsed = _parse_response(resp.data)
    return {
        "method": SHOP_LIST_METHOD,
        "status_code": resp.status_code,
        "request_params": resp.request_params,  # 已脱敏
        "raw_response": resp.raw_response,
        "ok": parsed["ok"], "message": parsed["message"],
        "filter": parsed["filter"], "shops": parsed["shops"],
    }


def sync_shop_list(page=1, page_size=20, start_modified=None, end_modified=None, client=None) -> dict:
    """向后兼容别名。"""
    return fetch_shop_list(page, page_size, start_modified, end_modified, client)


def _map_shop_row(raw: dict, now: datetime) -> dict:
    row = {}
    for src, col in SHOP_FIELD_MAP.items():
        val = raw.get(src)
        if isinstance(val, str) and val.strip() == "":
            val = None
        row[col] = val
    dr = row.get("discount_rate")
    if dr is not None:
        try:
            row["discount_rate"] = Decimal(str(dr))
        except (InvalidOperation, ValueError):
            row["discount_rate"] = None
    row["raw_data"] = raw
    row["synced_at"] = now
    row["updated_at"] = now
    return row


async def _upsert_shop_rows(db: AsyncSession, shops: list, now: datetime) -> dict:
    """对一页门店做 upsert（按 shop_code），返回 inserted/updated/skipped。"""
    inserted = updated = skipped = 0
    rows = []
    for raw in shops:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        row = _map_shop_row(raw, now)
        if not row.get("shop_code"):
            skipped += 1
            continue
        rows.append(row)

    codes = [r["shop_code"] for r in rows]
    existing = set()
    if codes:
        existing = set(
            (await db.execute(select(DimBaisonShop.shop_code).where(DimBaisonShop.shop_code.in_(codes)))).scalars().all()
        )
    for row in rows:
        if row["shop_code"] in existing:
            updated += 1
        else:
            inserted += 1
            existing.add(row["shop_code"])  # 防同批次重复计为insert
        stmt = pg_insert(DimBaisonShop).values(**row)
        update_cols = {c: stmt.excluded[c] for c in row.keys() if c not in ("shop_code", "created_at")}
        stmt = stmt.on_conflict_do_update(index_elements=["shop_code"], set_=update_cols)
        await db.execute(stmt)
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def _new_batch_no() -> str:
    return "BAISON_SHOP_" + datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6].upper()


async def import_shop_page(db: AsyncSession, page=1, page_size=20,
                           start_modified=None, end_modified=None, operator_id=None) -> dict:
    """同步单页并落库（写一条 log_data_sync）。"""
    batch_no = _new_batch_no()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="shop",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log)
    await db.flush()
    try:
        fetched = await asyncio.to_thread(fetch_shop_list, page, page_size, start_modified, end_modified)
        if not fetched["ok"]:
            raise ValueError(f"百胜返回失败: {fetched['message']}")
        now = datetime.now(timezone.utc)
        r = await _upsert_shop_rows(db, fetched["shops"], now)
        await db.flush()
        _finish_log(log, "success", r, start_at)
        await db.flush()
        sample = [{k: (s.get(k)) for k in ("sd_code", "sd_name", "sdxz", "qymc", "city", "is_qy")}
                  for s in fetched["shops"][:3]]
        return {"batch_no": batch_no, "ok": True, "status": "success",
                "filter": fetched["filter"], "message": fetched["message"],
                "total_rows": len(fetched["shops"]), **r, "sample": sample}
    except Exception as exc:
        return await _fail(db, log, exc, start_at, batch_no)


async def import_all_shops(db: AsyncSession, page_size=20,
                           start_modified=None, end_modified=None, operator_id=None) -> dict:
    """全量分页同步：page=1..page_count 逐页 upsert（一条 log_data_sync 覆盖整批）。"""
    batch_no = _new_batch_no()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="shop",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log)
    await db.flush()
    agg = {"inserted": 0, "updated": 0, "skipped": 0}
    per_page = []
    try:
        now = datetime.now(timezone.utc)
        first = await asyncio.to_thread(fetch_shop_list, 1, page_size, start_modified, end_modified)
        if not first["ok"]:
            raise ValueError(f"百胜返回失败: {first['message']}")
        filt = first["filter"] or {}
        page_count = int(filt.get("page_count") or 1)
        record_count = int(filt.get("record_count") or 0)

        r1 = await _upsert_shop_rows(db, first["shops"], now)
        for k in agg:
            agg[k] += r1[k]
        per_page.append({"page": 1, **r1})
        await db.flush()

        for p in range(2, page_count + 1):
            fp = await asyncio.to_thread(fetch_shop_list, p, page_size, start_modified, end_modified)
            if not fp["ok"]:
                raise ValueError(f"第{p}页返回失败: {fp['message']}")
            rp = await _upsert_shop_rows(db, fp["shops"], now)
            for k in agg:
                agg[k] += rp[k]
            per_page.append({"page": p, **rp})
            await db.flush()

        # 数据归位：百胜来源维(dim_baison_shop) -> 标准门店维(dim_store)
        from app.integrations.baison.services.store_mapping_service import map_baison_to_dim_store
        store_map = await map_baison_to_dim_store(db)

        _finish_log(log, "success", agg, start_at,
                    total_rows=agg["inserted"] + agg["updated"] + agg["skipped"])
        await db.flush()
        return {"batch_no": batch_no, "ok": True, "status": "success",
                "total_pages": page_count, "total_records": record_count,
                **agg, "dim_store_mapped": store_map, "per_page": per_page}
    except Exception as exc:
        res = await _fail(db, log, exc, start_at, batch_no)
        res.update(agg)
        res["per_page"] = per_page
        return res


def _finish_log(log: LogDataSync, status: str, counts: dict, start_at: datetime, total_rows=None):
    log.status = status
    log.success_rows = counts.get("inserted", 0) + counts.get("updated", 0)
    log.error_rows = counts.get("skipped", 0)
    log.total_rows = total_rows if total_rows is not None else log.success_rows + log.error_rows
    log.end_at = datetime.now(timezone.utc)
    log.duration_seconds = int((log.end_at - start_at).total_seconds())


async def _fail(db, log, exc, start_at, batch_no) -> dict:
    logger.warning("baison shop sync failed [%s]: %s", batch_no, exc.__class__.__name__)
    log.status = "failed"
    log.error_detail = [{"error": str(exc)[:300]}]
    log.end_at = datetime.now(timezone.utc)
    log.duration_seconds = int((log.end_at - start_at).total_seconds())
    await db.flush()
    return {"batch_no": batch_no, "ok": False, "status": "failed",
            "error": f"{exc.__class__.__name__}: {str(exc)[:300]}"}
