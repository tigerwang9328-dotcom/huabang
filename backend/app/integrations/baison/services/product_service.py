"""百胜商品主档（prm.goods.list_get，读取类）服务。

链路：prm.goods.list_get -> ods.ods_baison_product_api -> dim.dim_product -> 商品经营中心/商品主档。

接口差异（与门店不同！）：
- 分页参数 pageNo/pageSize（不是 page/page_size）；
- 成功判定 code=="1" and flag=="success"；
- 内层 data 为字符串化 JSON，需二次 json.loads；
- 列表字段为 goodsListGet；分页在 page.{pageNo,pageSize,pageTotal,totalResult}。
"""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.baison.client import BaisonClient
from app.models.baison_ods import OdsBaisonProductApi
from app.models.dim import DimProduct
from app.models.log import LogDataSync, LogDataQuality

logger = logging.getLogger("baison.product_service")

GOODS_LIST_METHOD = "prm.goods.list_get"
SOURCE_SYSTEM = "baison"


def _s(x):
    if isinstance(x, str) and x.strip() == "":
        return None
    return x


def _num(x):
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(v):
    if not v:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(v), fmt).date()
        except ValueError:
            continue
    return None


def _hash(raw: dict) -> str:
    return hashlib.md5(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _build_biz(page_no, page_size, start_modified, end_modified, opt_user_code="000",
               goods_sn="", season_code="", brand_code="", cat_code="", year_code="") -> dict:
    """构造业务参数（与百胜测试工具确认的请求结构一致）。"""
    biz = {
        "pageNo": str(page_no),
        "pageSize": str(page_size),
        "opt_user_code": opt_user_code or "000",
        "goods_sn": goods_sn or "",
        "season_code": season_code or "",
        "brand_code": brand_code or "",
        "cat_code": cat_code or "",
        "year_code": year_code or "",
        "fjsx1": "", "fjsx2": "", "fjsx3": "", "fjsx4": "", "fjsx5": "", "fjsx6": "",
    }
    if start_modified:
        biz["startModified"] = start_modified
    if end_modified:
        biz["endModified"] = end_modified
    return biz


def _parse_response(data) -> dict:
    out = {"ok": False, "message": "", "page": {}, "goods": []}
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
        goods = payload.get("goodsListGet")
        if isinstance(goods, list):
            out["goods"] = goods
    out["ok"] = success and isinstance(payload, dict)
    out["message"] = data.get("message") or data.get("msg") or ("成功" if out["ok"] else str(data)[:200])
    return out


def fetch_goods_page(page_no=1, page_size=20, start_modified=None, end_modified=None,
                     opt_user_code="000", client: Optional[BaisonClient] = None, **filters) -> dict:
    """同步调用一页（不落库）。供 dry_run / 同步复用。"""
    client = client or BaisonClient()
    biz = _build_biz(page_no, page_size, start_modified, end_modified, opt_user_code, **filters)
    resp = client.request(GOODS_LIST_METHOD, biz)
    parsed = _parse_response(resp.data)
    return {
        "method": GOODS_LIST_METHOD, "status_code": resp.status_code,
        "request_params": resp.request_params,  # 已脱敏
        "raw_response": resp.raw_response,
        "ok": parsed["ok"], "message": parsed["message"],
        "page": parsed["page"], "goods": parsed["goods"],
    }


def _ods_row(raw: dict, batch_no: str, now: datetime) -> dict:
    gsn = raw.get("goodsSn")
    gid = raw.get("goods_id")
    return {
        "batch_no": batch_no, "source_system": SOURCE_SYSTEM, "api_method": GOODS_LIST_METHOD,
        "source_goods_sn": gsn, "source_goods_id": str(gid) if gid is not None else None,
        "goods_sn": gsn, "goods_name": _s(raw.get("goodsName")),
        "raw_data": raw, "source_hash": _hash(raw),
        "created_source_at": _s(raw.get("created")), "modified_source_at": _s(raw.get("modified")),
        "lastchanged": str(raw.get("lastchanged")) if raw.get("lastchanged") is not None else None,
        "is_delete": raw.get("is_delete"),
        "synced_at": now, "updated_at": now,
    }


def _dim_row(raw: dict, now: datetime) -> dict:
    yc = raw.get("yearCode")
    try:
        year = int(yc) if yc not in (None, "") else None
    except (ValueError, TypeError):
        year = None
    cat_code = _s(raw.get("catCode")) or _s(raw.get("fjsx3Code"))   # 临时品类映射，待业务确认
    cat_name = _s(raw.get("catName")) or _s(raw.get("fjsx3Name"))
    ckj = raw.get("ckj")
    gid = raw.get("goods_id")
    return {
        "product_code": raw.get("goodsSn"),
        "product_name": _s(raw.get("goodsName")),
        "category_code": cat_code, "category_name": cat_name,
        "top_category_code": _s(raw.get("topCatCode")), "top_category_name": _s(raw.get("topCatName")),
        "series_code": _s(raw.get("seriesCode")), "series_name": _s(raw.get("seriesName")),
        "brand": _s(raw.get("brandName")), "brand_code": _s(raw.get("brandCode")), "brand_name": _s(raw.get("brandName")),
        "season": _s(raw.get("seasonName")) or _s(raw.get("seasonCode")), "season_code": _s(raw.get("seasonCode")),
        "year": year,
        "supplier_code": _s(raw.get("ghsCode")), "supplier_name": _s(raw.get("ghsName")),
        "tag_price": _num(raw.get("shopPrice")), "market_price": _num(raw.get("marketPrice")),
        "cost_price": _num(ckj), "has_cost": ckj not in (None, "", 0, 0.0),
        "weight": _num(raw.get("goodsWeight")),
        "launch_date": _parse_date(raw.get("created")),
        "status": "disabled" if str(raw.get("is_delete")) == "1" else "active",
        "source_system": SOURCE_SYSTEM,
        "source_product_id": str(gid) if gid is not None else None,
        "source_last_modified": _s(raw.get("modified")),
        "source_last_changed": str(raw.get("lastchanged")) if raw.get("lastchanged") is not None else None,
        "synced_at": now, "updated_at": now,
    }


def _check_quality(raw: dict, q: dict):
    gsn = _s(raw.get("goodsSn"))
    if not gsn:
        q["goods_sn_empty"] += 1
        return
    if not _s(raw.get("goodsName")):
        q["goods_name_empty"] += 1
    if not _s(raw.get("brandName")):
        q["brand_empty"] += 1
    if not (_s(raw.get("catCode")) or _s(raw.get("catName"))):
        q["category_empty"] += 1
    sp = _num(raw.get("shopPrice"))
    if sp is None or sp == 0:
        q["shop_price_empty"] += 1
    if _num(raw.get("ckj")) is None:
        q["cost_price_empty"] += 1
    if str(raw.get("is_delete")) not in ("0", "1"):
        q["is_delete_abnormal"] += 1


async def _upsert_goods(db: AsyncSession, goods: list, batch_no: str, now: datetime) -> dict:
    """对一页商品 upsert 到 ODS + DIM，返回计数与质量统计。"""
    q = {k: 0 for k in ("goods_sn_empty", "goods_name_empty", "brand_empty", "category_empty",
                         "shop_price_empty", "cost_price_empty", "is_delete_abnormal")}
    ods_ins = ods_upd = dim_ins = dim_upd = skipped = 0
    valid = []
    for raw in goods:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        _check_quality(raw, q)
        if not _s(raw.get("goodsSn")):
            skipped += 1   # goodsSn 为空：跳过 DIM
            continue
        valid.append(raw)

    codes = [r.get("goodsSn") for r in valid]
    ods_exist = dim_exist = set()
    if codes:
        ods_exist = set((await db.execute(
            select(OdsBaisonProductApi.goods_sn).where(
                OdsBaisonProductApi.goods_sn.in_(codes), OdsBaisonProductApi.source_system == SOURCE_SYSTEM)
        )).scalars().all())
        dim_exist = set((await db.execute(
            select(DimProduct.product_code).where(
                DimProduct.product_code.in_(codes), DimProduct.source_system == SOURCE_SYSTEM)
        )).scalars().all())

    seen_ods, seen_dim = set(ods_exist), set(dim_exist)
    for raw in valid:
        gsn = raw.get("goodsSn")
        # ODS
        if gsn in seen_ods:
            ods_upd += 1
        else:
            ods_ins += 1
            seen_ods.add(gsn)
        ors = _ods_row(raw, batch_no, now)
        st = pg_insert(OdsBaisonProductApi).values(**ors)
        st = st.on_conflict_do_update(constraint="uq_ods_baison_product_api_sn_source",
                                      set_={k: st.excluded[k] for k in ors if k not in ("goods_sn", "source_system", "created_at")})
        await db.execute(st)
        # DIM
        if gsn in seen_dim:
            dim_upd += 1
        else:
            dim_ins += 1
            seen_dim.add(gsn)
        drs = _dim_row(raw, now)
        st2 = pg_insert(DimProduct).values(**drs)
        dim_update = {k: st2.excluded[k] for k in drs if k not in ("product_code", "source_system", "created_at")}
        dim_update["cost_price"] = func.coalesce(st2.excluded.cost_price, DimProduct.cost_price)
        dim_update["has_cost"] = case(
            (st2.excluded.cost_price.isnot(None), st2.excluded.has_cost),
            else_=DimProduct.has_cost,
        )
        st2 = st2.on_conflict_do_update(constraint="uq_dim_product_code_source",
                                        set_=dim_update)
        await db.execute(st2)

    return {"ods_inserted": ods_ins, "ods_updated": ods_upd,
            "dim_inserted": dim_ins, "dim_updated": dim_upd, "skipped": skipped, "quality": q}


async def _write_quality_log(db: AsyncSession, batch_no: str, q_total: dict, now: datetime):
    warn = sum(q_total.values())
    if warn == 0:
        return
    db.add(LogDataQuality(
        check_date=now.date(), check_code="baison_product_sync", check_name="百胜商品主档同步数据质量",
        module="product", result_status="warning", affected_count=warn,
        detail={"batch_no": batch_no, **q_total}, ai_blocked=False,
    ))
    await db.flush()


def _new_batch() -> str:
    return "BAISON_PRODUCT_" + datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6].upper()


async def import_goods_page(db: AsyncSession, page_no=1, page_size=20, start_modified=None,
                            end_modified=None, opt_user_code="000", operator_id=None, **filters) -> dict:
    """同步单页商品（ODS+DIM+log）。"""
    batch_no = _new_batch()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="product",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log)
    await db.flush()
    try:
        fetched = await asyncio.to_thread(fetch_goods_page, page_no, page_size, start_modified,
                                          end_modified, opt_user_code, None, **filters)
        if not fetched["ok"]:
            raise ValueError(f"百胜返回失败: {fetched['message']}")
        now = datetime.now(timezone.utc)
        r = await _upsert_goods(db, fetched["goods"], batch_no, now)
        await _write_quality_log(db, batch_no, r["quality"], now)
        await db.flush()
        page = fetched["page"]
        _finish_log(log, "success", r, start_at, total_rows=len(fetched["goods"]))
        await db.flush()
        return {"batch_no": batch_no, "ok": True, "status": "success", "method": GOODS_LIST_METHOD,
                "page_total": page.get("pageTotal"), "total_result": page.get("totalResult"),
                "sample": [{k: g.get(k) for k in ("goodsSn", "goodsName", "brandName", "yearCode", "seasonName")} for g in fetched["goods"][:3]],
                **{k: r[k] for k in ("ods_inserted", "ods_updated", "dim_inserted", "dim_updated", "skipped")},
                "quality": r["quality"]}
    except Exception as exc:
        return await _fail(db, log, exc, start_at, batch_no)


async def import_all_goods(db: AsyncSession, page_size=20, start_modified=None, end_modified=None,
                           opt_user_code="000", operator_id=None, **filters) -> dict:
    """全量分页同步商品（pageNo=1..pageTotal，一条 log 覆盖整批）。"""
    batch_no = _new_batch()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="product",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log)
    await db.flush()
    agg = {"ods_inserted": 0, "ods_updated": 0, "dim_inserted": 0, "dim_updated": 0, "skipped": 0}
    q_total = {k: 0 for k in ("goods_sn_empty", "goods_name_empty", "brand_empty", "category_empty",
                              "shop_price_empty", "cost_price_empty", "is_delete_abnormal")}
    try:
        now = datetime.now(timezone.utc)
        first = await asyncio.to_thread(fetch_goods_page, 1, page_size, start_modified, end_modified, opt_user_code, None, **filters)
        if not first["ok"]:
            raise ValueError(f"百胜返回失败: {first['message']}")
        page = first["page"]
        page_total = int(page.get("pageTotal") or 1)
        total_result = int(page.get("totalResult") or 0)

        def _accum(r):
            for k in agg:
                agg[k] += r[k]
            for k in q_total:
                q_total[k] += r["quality"][k]

        _accum(await _upsert_goods(db, first["goods"], batch_no, now))
        await db.flush()
        for pno in range(2, page_total + 1):
            fp = await asyncio.to_thread(fetch_goods_page, pno, page_size, start_modified, end_modified, opt_user_code, None, **filters)
            if not fp["ok"]:
                raise ValueError(f"第{pno}页返回失败: {fp['message']}")
            _accum(await _upsert_goods(db, fp["goods"], batch_no, now))
            await db.flush()

        await _write_quality_log(db, batch_no, q_total, now)
        _finish_log(log, "success", agg, start_at, total_rows=agg["dim_inserted"] + agg["dim_updated"] + agg["skipped"])
        await db.flush()
        return {"batch_no": batch_no, "ok": True, "status": "success", "method": GOODS_LIST_METHOD,
                "page_total": page_total, "total_result": total_result, **agg, "quality": q_total}
    except Exception as exc:
        res = await _fail(db, log, exc, start_at, batch_no)
        res.update(agg)
        return res


def _finish_log(log: LogDataSync, status: str, r: dict, start_at: datetime, total_rows=None):
    log.status = status
    log.success_rows = r.get("dim_inserted", 0) + r.get("dim_updated", 0)
    log.error_rows = r.get("skipped", 0)
    log.total_rows = total_rows if total_rows is not None else log.success_rows + log.error_rows
    log.end_at = datetime.now(timezone.utc)
    log.duration_seconds = int((log.end_at - start_at).total_seconds())


async def _fail(db, log, exc, start_at, batch_no) -> dict:
    logger.warning("baison product sync failed [%s]: %s", batch_no, exc.__class__.__name__)
    log.status = "failed"
    log.error_detail = [{"error": str(exc)[:300]}]
    log.end_at = datetime.now(timezone.utc)
    log.duration_seconds = int((log.end_at - start_at).total_seconds())
    await db.flush()
    return {"batch_no": batch_no, "ok": False, "status": "failed",
            "error": f"{exc.__class__.__name__}: {str(exc)[:300]}"}
