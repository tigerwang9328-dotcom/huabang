"""百胜实物库存（stock.goods_sscx，读取类）服务。

链路：stock.goods_sscx -> ods.ods_baison_inventory_api -> dwd.dwd_inventory_balance -> 库存预警中心/库存余额。

要点（已与用户确认）：
- store_code 必填，逐店全量（无可靠时间游标，不做增量）；空参数省略不传；
- code=="1" 判成功；内层 data 二次 json.loads；列表字段 data；分页 filter.page_count/record_count；
- barcode 是数组 -> 展开，一条码一行（空数组 -> 一行 barcode=None）；
- 可用库存 available_qty = num - lock_num；零库存(num=0)照存；库存金额本接口无（后续 join 成本）。
"""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.baison.client import BaisonClient
from app.models.baison_ods import OdsBaisonInventoryApi, DwdInventoryBalance
from app.models.log import LogDataSync, LogDataQuality

logger = logging.getLogger("baison.inventory_service")

STOCK_METHOD = "stock.goods_sscx"
SOURCE_SYSTEM = "baison"


def _s(x):
    if isinstance(x, str) and x.strip() == "":
        return None
    return x


def _trim(x):
    if x is None:
        return None
    t = str(x).strip()
    return t or None


def _num(x):
    if x is None or x == "":
        return Decimal(0)
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _hash(raw: dict) -> str:
    return hashlib.md5(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _line_hash(store, goods, color, size, barcode) -> str:
    key = "|".join([str(store or ""), str(goods or ""), str(color or ""), str(size or ""), str(barcode or "")])
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def fetch_inventory_page(store_code, page_no=1, page_size=20, client: Optional[BaisonClient] = None) -> dict:
    client = client or BaisonClient()
    biz = {"pageNo": str(page_no), "pageSize": str(page_size), "store_code": store_code}
    resp = client.request(STOCK_METHOD, biz)
    data = resp.data if isinstance(resp.data, dict) else {}
    ok = str(data.get("code")) == "1" and str(data.get("flag")).lower() == "success"
    inner = data.get("data")
    payload = None
    if isinstance(inner, str):
        try:
            payload = json.loads(inner)
        except (json.JSONDecodeError, ValueError):
            payload = None
    elif isinstance(inner, dict):
        payload = inner
    filt = (payload or {}).get("filter") or {}
    rows = (payload or {}).get("data") or []
    return {"ok": ok and isinstance(payload, dict), "message": data.get("message"),
            "filter": filt, "rows": rows, "request_params": resp.request_params}


def _barcodes(raw: dict):
    bc = raw.get("barcode")
    out = []
    if isinstance(bc, list):
        out = [str(b).strip() for b in bc if b is not None and str(b).strip() != ""]
    elif bc is not None and str(bc).strip() != "":
        out = [str(bc).strip()]
    return out or [None]


def _expand(raw: dict):
    """一条百胜库存行 -> 多条(按 barcode 展开)标准行(ODS+DWD 字段)。"""
    store = _trim(raw.get("store_code"))
    goods = _trim(raw.get("goods_code"))
    color = _s(raw.get("color_code"))
    size = _s(raw.get("size_code"))
    sku = _trim(raw.get("sku"))
    num = _num(raw.get("num"))
    lock = _num(raw.get("lock_num"))
    road = _num(raw.get("road_num"))
    avail = num - lock
    for bc in _barcodes(raw):
        lh = _line_hash(store, goods, color, size, bc)
        yield {
            "line_hash": lh, "store_code": store, "goods_code": goods, "sku": sku,
            "barcode": bc, "color_code": color, "size_code": size,
            "warehouse_name": _s(raw.get("ck_name")), "goods_name": _s(raw.get("goods_name")),
            "color_name": _s(raw.get("color_name")), "size_name": _s(raw.get("size_name")),
            "location_name": _s(raw.get("kw_name")),
            "num": num, "lock": lock, "road": road, "avail": avail,
        }


_Q_KEYS = ("goods_code_empty", "sku_empty", "negative_available", "zero_qty_rows", "multi_barcode_rows")


async def _list_store_codes(db: AsyncSession) -> list:
    rows = (await db.execute(text(
        "select warehouse_code from dim.dim_warehouse where source_system='baison' and warehouse_code is not null order by warehouse_code"
    ))).scalars().all()
    return list(rows)


async def _upsert_lines(db, lines, batch_no, now) -> dict:
    ods_ins = ods_upd = dwd_ins = dwd_upd = 0
    hashes = [ln["line_hash"] for ln, raw in lines]
    ods_exist = dwd_exist = set()
    if hashes:
        ods_exist = set((await db.execute(select(OdsBaisonInventoryApi.line_hash).where(
            OdsBaisonInventoryApi.line_hash.in_(hashes), OdsBaisonInventoryApi.source_system == SOURCE_SYSTEM))).scalars().all())
        dwd_exist = set((await db.execute(select(DwdInventoryBalance.line_hash).where(
            DwdInventoryBalance.line_hash.in_(hashes), DwdInventoryBalance.source_system == SOURCE_SYSTEM))).scalars().all())
    seen_o, seen_d = set(ods_exist), set(dwd_exist)
    for ln, raw in lines:
        lh = ln["line_hash"]
        if lh in seen_o:
            ods_upd += 1
        else:
            ods_ins += 1; seen_o.add(lh)
        ors = {"batch_no": batch_no, "source_system": SOURCE_SYSTEM, "api_method": STOCK_METHOD,
               "line_hash": lh, "store_code": ln["store_code"], "goods_code": ln["goods_code"],
               "sku": ln["sku"], "barcode": ln["barcode"], "color_code": ln["color_code"],
               "size_code": ln["size_code"], "raw_data": raw, "source_hash": _hash(raw),
               "synced_at": now, "updated_at": now}
        st = pg_insert(OdsBaisonInventoryApi).values(**ors)
        st = st.on_conflict_do_update(constraint="uq_ods_baison_inventory_api_line_source",
                                      set_={k: st.excluded[k] for k in ors if k not in ("line_hash", "source_system", "created_at")})
        await db.execute(st)
        if lh in seen_d:
            dwd_upd += 1
        else:
            dwd_ins += 1; seen_d.add(lh)
        drs = {"batch_no": batch_no, "source_system": SOURCE_SYSTEM, "line_hash": lh,
               "warehouse_code": ln["store_code"], "warehouse_name": ln["warehouse_name"],
               "product_code": ln["goods_code"], "sku_code": ln["sku"], "barcode": ln["barcode"],
               "goods_name": ln["goods_name"], "color_code": ln["color_code"], "color_name": ln["color_name"],
               "size_code": ln["size_code"], "size_name": ln["size_name"], "location_name": ln["location_name"],
               "qty": ln["num"], "lock_qty": ln["lock"], "road_qty": ln["road"], "available_qty": ln["avail"],
               "synced_at": now, "updated_at": now}
        st2 = pg_insert(DwdInventoryBalance).values(**drs)
        st2 = st2.on_conflict_do_update(constraint="uq_dwd_inventory_balance_line_source",
                                        set_={k: st2.excluded[k] for k in drs if k not in ("line_hash", "source_system", "created_at")})
        await db.execute(st2)
    return {"ods_inserted": ods_ins, "ods_updated": ods_upd, "dwd_inserted": dwd_ins, "dwd_updated": dwd_upd}


def _quality(raw, expanded, q):
    if not _trim(raw.get("goods_code")):
        q["goods_code_empty"] += 1
    if not _trim(raw.get("sku")):
        q["sku_empty"] += 1
    if (_num(raw.get("num")) - _num(raw.get("lock_num"))) < 0:
        q["negative_available"] += 1
    if _num(raw.get("num")) == 0:
        q["zero_qty_rows"] += 1
    if len(expanded) > 1:
        q["multi_barcode_rows"] += 1


def _new_batch():
    return "BAISON_INV_" + datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6].upper()


async def import_all_inventory(db: AsyncSession, page_size=20, operator_id=None, store_limit=None) -> dict:
    """逐店全量同步实物库存。store_limit 可限制门店数（验证用）。"""
    batch_no = _new_batch()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="inventory",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log); await db.flush()
    agg = {"ods_inserted": 0, "ods_updated": 0, "dwd_inserted": 0, "dwd_updated": 0}
    q_total = {k: 0 for k in _Q_KEYS}
    stores_with_data = stores_empty = stores_done = 0
    try:
        now = datetime.now(timezone.utc)
        stores = await _list_store_codes(db)
        if store_limit:
            stores = stores[:store_limit]
        for sc in stores:
            first = await asyncio.to_thread(fetch_inventory_page, sc, 1, page_size)
            if not first["ok"]:
                raise ValueError(f"门店{sc}返回失败: {first['message']}")
            pc = int((first["filter"] or {}).get("page_count") or 0)
            rc = int((first["filter"] or {}).get("record_count") or 0)
            if rc == 0:
                stores_empty += 1; stores_done += 1; continue
            stores_with_data += 1

            async def _do(rows):
                lines = []
                for raw in rows:
                    exp = list(_expand(raw))
                    _quality(raw, exp, q_total)
                    for ln in exp:
                        lines.append((ln, raw))
                r = await _upsert_lines(db, lines, batch_no, now)
                for k in agg:
                    agg[k] += r[k]

            await _do(first["rows"])
            for pno in range(2, pc + 1):
                fp = await asyncio.to_thread(fetch_inventory_page, sc, pno, page_size)
                if not fp["ok"]:
                    raise ValueError(f"门店{sc}第{pno}页失败: {fp['message']}")
                await _do(fp["rows"])
            await db.commit()
            stores_done += 1

        if sum(q_total.values()) > 0:
            db.add(LogDataQuality(check_date=now.date(), check_code="baison_inventory_sync",
                                  check_name="百胜库存余额同步数据质量", module="inventory",
                                  result_status="warning", affected_count=sum(q_total.values()),
                                  detail={"batch_no": batch_no, **q_total,
                                          "stores_with_data": stores_with_data, "stores_empty": stores_empty}, ai_blocked=False))
        log.status = "success"
        log.success_rows = agg["dwd_inserted"] + agg["dwd_updated"]
        log.total_rows = agg["dwd_inserted"] + agg["dwd_updated"]
        log.end_at = datetime.now(timezone.utc)
        log.duration_seconds = int((log.end_at - start_at).total_seconds())
        await db.commit()
        return {"batch_no": batch_no, "ok": True, "status": "success", "method": STOCK_METHOD,
                "stores_total": len(stores), "stores_with_data": stores_with_data, "stores_empty": stores_empty,
                **agg, "quality": q_total}
    except Exception as exc:
        logger.warning("baison inventory sync failed [%s]: %s", batch_no, exc.__class__.__name__)
        log.status = "failed"
        log.error_detail = [{"error": str(exc)[:300]}]
        log.end_at = datetime.now(timezone.utc)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
        return {"batch_no": batch_no, "ok": False, "status": "failed",
                "error": f"{exc.__class__.__name__}: {str(exc)[:300]}", **agg}
