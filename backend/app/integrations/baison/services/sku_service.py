"""百胜商品 SKU/条码（prm.goods.sku_list_get，读取类）服务。

链路：prm.goods.sku_list_get -> ods.ods_baison_sku_api -> dim.dim_sku -> 商品经营中心/SKU档案。

要点：只传 pageNo/pageSize 即可全量（40944 条/2048 页）；带 goodsSn/时间筛选可能返回空，
增量口径待百胜确认，本服务默认不传筛选。code=="1" 判成功；内层 data 二次 json.loads；
列表字段 skuListGet；goodsSn/sku 可能带前导空格，标准字段 trim，raw_data 保留原始。
"""
import asyncio
import hashlib
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
from app.models.baison_ods import OdsBaisonSkuApi
from app.models.dim import DimSku, DimProduct
from app.models.log import LogDataSync, LogDataQuality

logger = logging.getLogger("baison.sku_service")

SKU_LIST_METHOD = "prm.goods.sku_list_get"
SOURCE_SYSTEM = "baison"
_BYTE_SENTINEL = "System.Byte[]"


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
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def _hash(raw: dict) -> str:
    return hashlib.md5(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _build_biz(page_no, page_size) -> dict:
    # 默认只传分页（带 goodsSn/时间会返回空，增量待百胜确认）
    return {"pageNo": str(page_no), "pageSize": str(page_size)}


def _parse_response(data) -> dict:
    out = {"ok": False, "message": "", "page": {}, "skus": []}
    if not isinstance(data, dict):
        out["message"] = "响应非JSON对象"
        return out
    success = (str(data.get("code")) == "1" and str(data.get("flag")).lower() == "success")
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
        out["page"] = payload.get("page") or {}
        skus = payload.get("skuListGet")
        if isinstance(skus, list):
            out["skus"] = skus
    out["ok"] = success and isinstance(payload, dict)
    out["message"] = data.get("message") or data.get("msg") or ("成功" if out["ok"] else str(data)[:200])
    return out


def fetch_sku_page(page_no=1, page_size=20, client: Optional[BaisonClient] = None) -> dict:
    client = client or BaisonClient()
    resp = client.request(SKU_LIST_METHOD, _build_biz(page_no, page_size))
    parsed = _parse_response(resp.data)
    return {
        "method": SKU_LIST_METHOD, "status_code": resp.status_code,
        "request_params": resp.request_params, "raw_response": resp.raw_response,
        "ok": parsed["ok"], "message": parsed["message"],
        "page": parsed["page"], "skus": parsed["skus"],
    }


def _ods_row(raw: dict, batch_no: str, now: datetime) -> dict:
    sku_code = _trim(raw.get("sku"))
    gb = _s(raw.get("gbBarcode")); s69 = _s(raw.get("sixNineCode"))
    return {
        "batch_no": batch_no, "source_system": SOURCE_SYSTEM, "api_method": SKU_LIST_METHOD,
        "source_goods_sn": raw.get("goodsSn"), "source_sku": raw.get("sku"),
        "goods_sn": _trim(raw.get("goodsSn")), "sku_code": sku_code,
        "barcode": gb or s69, "gb_barcode": gb, "six_nine_code": s69,
        "raw_data": raw, "source_hash": _hash(raw),
        "created_source_at": _s(raw.get("created")), "modified_source_at": _s(raw.get("modified")),
        "lastchanged": str(raw.get("lastchanged")) if raw.get("lastchanged") is not None else None,
        "synced_at": now, "updated_at": now,
    }


def _dim_row(raw: dict, now: datetime) -> dict:
    gb = _s(raw.get("gbBarcode")); s69 = _s(raw.get("sixNineCode"))
    ckj = raw.get("ckj")
    cbj = raw.get("cbj")
    standard_purchase_price = _num(raw.get("marketPrice"))
    if standard_purchase_price is not None and standard_purchase_price <= 0:
        standard_purchase_price = None
    return {
        "sku_code": _trim(raw.get("sku")),
        "product_code": _trim(raw.get("goodsSn")),
        "product_name": _s(raw.get("goodsName")),
        "short_name": _s(raw.get("goodsSname")),
        "barcode": gb or s69, "gb_barcode": gb, "six_nine_code": s69,
        "color": _s(raw.get("colorName")), "color_code": _s(raw.get("colorCode")), "color_name": _s(raw.get("colorName")),
        "size": _s(raw.get("sizeName")), "size_code": _s(raw.get("sizeCode")), "size_name": _s(raw.get("sizeName")),
        "brand_code": _s(raw.get("brandCode")), "brand_name": _s(raw.get("brandName")),
        "category_code": _s(raw.get("catCode")), "category_name": _s(raw.get("catName")),
        "season_code": _s(raw.get("seasonCode")), "season_name": _s(raw.get("seasonName")),
        "series_code": _s(raw.get("seriesCode")), "series_name": _s(raw.get("seriesName")),
        "tag_price": _num(raw.get("shopPrice") or ckj), "market_price": _num(raw.get("marketPrice")),
        "standard_purchase_price": standard_purchase_price,
        "cost_price": _num(cbj), "has_cost": _num(cbj) is not None,   # cbj=成本价，ckj/shopPrice=吊牌/售价
        "weight": _num(raw.get("goodsWeight")), "remark": _s(raw.get("remark")),
        "status": "active",   # 接口未返回状态，默认 active，待百胜确认
        "source_system": SOURCE_SYSTEM,
        "source_created_at": _s(raw.get("created")), "source_modified_at": _s(raw.get("modified")),
        "source_last_changed": str(raw.get("lastchanged")) if raw.get("lastchanged") is not None else None,
        "synced_at": now, "updated_at": now,
    }


_Q_KEYS = ("sku_empty", "goods_sn_empty", "product_not_found", "barcode_empty",
           "color_empty", "size_empty", "shop_price_empty", "standard_purchase_price_empty",
           "lastchanged_bytes", "has_space")


async def _load_product_codes(db: AsyncSession) -> set:
    return set((await db.execute(
        select(DimProduct.product_code).where(DimProduct.source_system == SOURCE_SYSTEM)
    )).scalars().all())


async def _upsert_skus(db: AsyncSession, skus: list, batch_no: str, now: datetime, product_codes: set) -> dict:
    q = {k: 0 for k in _Q_KEYS}
    ods_ins = ods_upd = dim_ins = dim_upd = skipped = linked = 0

    sku_codes = []
    rows = []
    for raw in skus:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        sku = _trim(raw.get("sku")); gsn = _trim(raw.get("goodsSn"))
        if raw.get("sku") != sku or raw.get("goodsSn") != gsn:
            q["has_space"] += 1
        if not _s(raw.get("gbBarcode")) and not _s(raw.get("sixNineCode")):
            q["barcode_empty"] += 1
        if not _s(raw.get("colorName")):
            q["color_empty"] += 1
        if not _s(raw.get("sizeName")):
            q["size_empty"] += 1
        sp = _num(raw.get("shopPrice"))
        if sp is None or sp == 0:
            q["shop_price_empty"] += 1
        standard_purchase_price = _num(raw.get("marketPrice"))
        if standard_purchase_price is None or standard_purchase_price <= 0:
            q["standard_purchase_price_empty"] += 1
        if str(raw.get("lastchanged")) == _BYTE_SENTINEL:
            q["lastchanged_bytes"] += 1
        if not sku:
            q["sku_empty"] += 1; skipped += 1; continue
        if not gsn:
            q["goods_sn_empty"] += 1; skipped += 1; continue
        if gsn not in product_codes:
            q["product_not_found"] += 1
        else:
            linked += 1
        rows.append(raw); sku_codes.append(sku)

    ods_exist = dim_exist = set()
    if sku_codes:
        ods_exist = set((await db.execute(select(OdsBaisonSkuApi.sku_code).where(
            OdsBaisonSkuApi.sku_code.in_(sku_codes), OdsBaisonSkuApi.source_system == SOURCE_SYSTEM))).scalars().all())
        dim_exist = set((await db.execute(select(DimSku.sku_code).where(
            DimSku.sku_code.in_(sku_codes), DimSku.source_system == SOURCE_SYSTEM))).scalars().all())

    seen_ods, seen_dim = set(ods_exist), set(dim_exist)
    for raw in rows:
        sku = _trim(raw.get("sku"))
        if sku in seen_ods:
            ods_upd += 1
        else:
            ods_ins += 1; seen_ods.add(sku)
        ors = _ods_row(raw, batch_no, now)
        st = pg_insert(OdsBaisonSkuApi).values(**ors)
        st = st.on_conflict_do_update(constraint="uq_ods_baison_sku_api_sku_source",
                                      set_={k: st.excluded[k] for k in ors if k not in ("sku_code", "source_system", "created_at")})
        await db.execute(st)
        if sku in seen_dim:
            dim_upd += 1
        else:
            dim_ins += 1; seen_dim.add(sku)
        drs = _dim_row(raw, now)
        st2 = pg_insert(DimSku).values(**drs)
        st2 = st2.on_conflict_do_update(constraint="uq_dim_sku_code_source",
                                        set_={k: st2.excluded[k] for k in drs if k not in ("sku_code", "source_system", "created_at")})
        await db.execute(st2)

    return {"ods_inserted": ods_ins, "ods_updated": ods_upd, "dim_inserted": dim_ins,
            "dim_updated": dim_upd, "skipped": skipped, "linked": linked, "quality": q}


async def _write_quality_log(db, batch_no, q, now):
    warn = sum(q.values())
    if warn == 0:
        return
    db.add(LogDataQuality(check_date=now.date(), check_code="baison_sku_sync",
                          check_name="百胜SKU档案同步数据质量", module="product",
                          result_status="warning", affected_count=warn,
                          detail={"batch_no": batch_no, **q}, ai_blocked=False))
    await db.flush()


def _new_batch():
    return "BAISON_SKU_" + datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6].upper()


def _finish_log(log, status, r, start_at, total_rows=None):
    log.status = status
    log.success_rows = r.get("dim_inserted", 0) + r.get("dim_updated", 0)
    log.error_rows = r.get("skipped", 0)
    log.total_rows = total_rows if total_rows is not None else log.success_rows + log.error_rows
    log.end_at = datetime.now(timezone.utc)
    log.duration_seconds = int((log.end_at - start_at).total_seconds())


async def _fail(db, log, exc, start_at, batch_no):
    logger.warning("baison sku sync failed [%s]: %s", batch_no, exc.__class__.__name__)
    log.status = "failed"
    log.error_detail = [{"error": str(exc)[:300]}]
    log.end_at = datetime.now(timezone.utc)
    log.duration_seconds = int((log.end_at - start_at).total_seconds())
    await db.flush()
    return {"batch_no": batch_no, "ok": False, "status": "failed",
            "error": f"{exc.__class__.__name__}: {str(exc)[:300]}"}


async def import_sku_page(db: AsyncSession, page_no=1, page_size=20, operator_id=None) -> dict:
    batch_no = _new_batch()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="sku",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log); await db.flush()
    try:
        fetched = await asyncio.to_thread(fetch_sku_page, page_no, page_size)
        if not fetched["ok"]:
            raise ValueError(f"百胜返回失败: {fetched['message']}")
        now = datetime.now(timezone.utc)
        pcodes = await _load_product_codes(db)
        r = await _upsert_skus(db, fetched["skus"], batch_no, now, pcodes)
        await _write_quality_log(db, batch_no, r["quality"], now)
        await db.flush()
        page = fetched["page"]
        _finish_log(log, "success", r, start_at, total_rows=len(fetched["skus"]))
        await db.flush()
        return {"batch_no": batch_no, "ok": True, "status": "success", "method": SKU_LIST_METHOD,
                "page_total": page.get("pageTotal"), "total_result": page.get("totalResult"),
                "linked": r["linked"], "quality": r["quality"],
                "sample": [{k: g.get(k) for k in ("goodsSn", "sku", "colorName", "sizeName", "gbBarcode")} for g in fetched["skus"][:3]],
                **{k: r[k] for k in ("ods_inserted", "ods_updated", "dim_inserted", "dim_updated", "skipped")}}
    except Exception as exc:
        return await _fail(db, log, exc, start_at, batch_no)


async def import_all_skus(db: AsyncSession, page_size=20, operator_id=None, max_pages=None) -> dict:
    """全量分页同步 SKU（pageNo=1..pageTotal）。max_pages 可限制页数（验证用）。"""
    batch_no = _new_batch()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="sku",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log); await db.flush()
    agg = {"ods_inserted": 0, "ods_updated": 0, "dim_inserted": 0, "dim_updated": 0, "skipped": 0, "linked": 0}
    q_total = {k: 0 for k in _Q_KEYS}
    try:
        now = datetime.now(timezone.utc)
        pcodes = await _load_product_codes(db)
        first = await asyncio.to_thread(fetch_sku_page, 1, page_size)
        if not first["ok"]:
            raise ValueError(f"百胜返回失败: {first['message']}")
        page = first["page"]
        page_total = int(page.get("pageTotal") or 1)
        total_result = int(page.get("totalResult") or 0)
        if max_pages:
            page_total = min(page_total, max_pages)

        def _accum(r):
            for k in agg:
                agg[k] += r[k]
            for k in q_total:
                q_total[k] += r["quality"][k]

        _accum(await _upsert_skus(db, first["skus"], batch_no, now, pcodes))
        await db.flush()
        for pno in range(2, page_total + 1):
            fp = await asyncio.to_thread(fetch_sku_page, pno, page_size)
            if not fp["ok"]:
                raise ValueError(f"第{pno}页返回失败: {fp['message']}")
            _accum(await _upsert_skus(db, fp["skus"], batch_no, now, pcodes))
            if pno % 50 == 0:
                await db.commit()
            else:
                await db.flush()

        await _write_quality_log(db, batch_no, q_total, now)
        _finish_log(log, "success", agg, start_at, total_rows=agg["dim_inserted"] + agg["dim_updated"] + agg["skipped"])
        await db.flush()
        return {"batch_no": batch_no, "ok": True, "status": "success", "method": SKU_LIST_METHOD,
                "page_total": page_total, "total_result": total_result, **agg, "quality": q_total}
    except Exception as exc:
        res = await _fail(db, log, exc, start_at, batch_no)
        res.update(agg)
        return res
