"""百胜仓库档案（base.warehouse_list_get，读取类）服务。

链路：base.warehouse_list_get -> ods.ods_baison_warehouse_api -> dim.dim_warehouse -> 库存预警中心/仓库档案。

结构：page/page_size 分页；code=="1" 判成功；内层 data 二次 json.loads；
列表字段 data；分页 filter.{page,page_size,page_count,record_count}。仓库档案≠库存余额，不计算库存数量。
"""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.baison.client import BaisonClient
from app.models.baison_ods import OdsBaisonWarehouseApi
from app.models.dim import DimWarehouse
from app.models.log import LogDataSync, LogDataQuality

logger = logging.getLogger("baison.warehouse_service")

WAREHOUSE_LIST_METHOD = "base.warehouse_list_get"
SOURCE_SYSTEM = "baison"
_CLOSED_HINTS = ("已撤", "停用", "关闭", "作废")


def _s(x):
    if isinstance(x, str) and x.strip() == "":
        return None
    return x


def _trim(x):
    if x is None:
        return None
    t = str(x).strip()
    return t or None


def _hash(raw: dict) -> str:
    return hashlib.md5(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _build_biz(page, page_size, opt_user_code="000", ckdm="", qddm="", pt_type="") -> dict:
    return {"page": str(page), "page_size": str(page_size), "opt_user_code": opt_user_code or "000",
            "ckdm": ckdm or "", "qddm": qddm or "", "pt_type": pt_type or ""}


def _parse_response(data) -> dict:
    out = {"ok": False, "message": "", "filter": {}, "warehouses": []}
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
        out["filter"] = payload.get("filter") or {}
        wl = payload.get("data")
        if isinstance(wl, list):
            out["warehouses"] = wl
    out["ok"] = success and isinstance(payload, dict)
    out["message"] = data.get("message") or data.get("msg") or ("成功" if out["ok"] else str(data)[:200])
    return out


def fetch_warehouse_page(page=1, page_size=20, opt_user_code="000",
                         client: Optional[BaisonClient] = None, **filters) -> dict:
    client = client or BaisonClient()
    resp = client.request(WAREHOUSE_LIST_METHOD, _build_biz(page, page_size, opt_user_code, **filters))
    parsed = _parse_response(resp.data)
    return {
        "method": WAREHOUSE_LIST_METHOD, "status_code": resp.status_code,
        "request_params": resp.request_params, "raw_response": resp.raw_response,
        "ok": parsed["ok"], "message": parsed["message"],
        "filter": parsed["filter"], "warehouses": parsed["warehouses"],
    }


def _status_from_ty(ty):
    t = str(ty)
    if t == "0":
        return "active", True
    if t == "1":
        return "disabled", False
    return "unknown", None


def _ods_row(raw, batch_no, now):
    code = _trim(raw.get("ckdm"))
    return {
        "batch_no": batch_no, "source_system": SOURCE_SYSTEM, "api_method": WAREHOUSE_LIST_METHOD,
        "source_warehouse_code": raw.get("ckdm"), "warehouse_code": code,
        "warehouse_name": _trim(raw.get("ckmc")), "raw_data": raw, "source_hash": _hash(raw),
        "synced_at": now, "updated_at": now,
    }


def _dim_row(raw, now):
    status, is_enabled = _status_from_ty(raw.get("ty"))
    return {
        "warehouse_code": _trim(raw.get("ckdm")),
        "warehouse_name": _trim(raw.get("ckmc")),
        "channel_code": _s(raw.get("qddm")),
        "region_name": _s(raw.get("qy_id_name")),
        "warehouse_nature": _s(raw.get("ckxz")),
        "warehouse_category_code": _s(raw.get("cklb")),
        "warehouse_category_name": _s(raw.get("cklb_name")),
        "default_location_code": _s(raw.get("defaultkwdm")),
        "default_location_name": _s(raw.get("defaultkwmc")),
        "status": status, "is_enabled": is_enabled,
        "source_system": SOURCE_SYSTEM, "synced_at": now, "updated_at": now,
    }


_Q_KEYS = ("ckdm_empty", "ckmc_empty", "ty_abnormal", "region_undefined",
           "category_undefined", "default_loc_code_empty", "default_loc_name_empty", "closed_name_hint")


async def _upsert_warehouses(db, warehouses, batch_no, now) -> dict:
    q = {k: 0 for k in _Q_KEYS}
    ods_ins = ods_upd = dim_ins = dim_upd = skipped = 0
    rows = []
    for raw in warehouses:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        code = _trim(raw.get("ckdm"))
        if not _trim(raw.get("ckmc")):
            q["ckmc_empty"] += 1
        if str(raw.get("ty")) not in ("0", "1"):
            q["ty_abnormal"] += 1
        rn = _s(raw.get("qy_id_name"))
        if not rn or rn == "未定义":
            q["region_undefined"] += 1
        cn = _s(raw.get("cklb_name"))
        if not cn or cn == "未定义":
            q["category_undefined"] += 1
        if not _s(raw.get("defaultkwdm")):
            q["default_loc_code_empty"] += 1
        if not _s(raw.get("defaultkwmc")):
            q["default_loc_name_empty"] += 1
        nm = str(raw.get("ckmc") or "")
        if str(raw.get("ty")) == "0" and any(h in nm for h in _CLOSED_HINTS):
            q["closed_name_hint"] += 1
        if not code:
            q["ckdm_empty"] += 1
            skipped += 1
            continue
        rows.append(raw)

    codes = [_trim(r.get("ckdm")) for r in rows]
    ods_exist = dim_exist = set()
    if codes:
        ods_exist = set((await db.execute(select(OdsBaisonWarehouseApi.warehouse_code).where(
            OdsBaisonWarehouseApi.warehouse_code.in_(codes), OdsBaisonWarehouseApi.source_system == SOURCE_SYSTEM))).scalars().all())
        dim_exist = set((await db.execute(select(DimWarehouse.warehouse_code).where(
            DimWarehouse.warehouse_code.in_(codes), DimWarehouse.source_system == SOURCE_SYSTEM))).scalars().all())
    seen_ods, seen_dim = set(ods_exist), set(dim_exist)
    for raw in rows:
        code = _trim(raw.get("ckdm"))
        if code in seen_ods:
            ods_upd += 1
        else:
            ods_ins += 1; seen_ods.add(code)
        ors = _ods_row(raw, batch_no, now)
        st = pg_insert(OdsBaisonWarehouseApi).values(**ors)
        st = st.on_conflict_do_update(constraint="uq_ods_baison_warehouse_api_code_source",
                                      set_={k: st.excluded[k] for k in ors if k not in ("warehouse_code", "source_system", "created_at")})
        await db.execute(st)
        if code in seen_dim:
            dim_upd += 1
        else:
            dim_ins += 1; seen_dim.add(code)
        drs = _dim_row(raw, now)
        st2 = pg_insert(DimWarehouse).values(**drs)
        st2 = st2.on_conflict_do_update(constraint="uq_dim_warehouse_code_source",
                                        set_={k: st2.excluded[k] for k in drs if k not in ("warehouse_code", "source_system", "created_at")})
        await db.execute(st2)
    return {"ods_inserted": ods_ins, "ods_updated": ods_upd, "dim_inserted": dim_ins,
            "dim_updated": dim_upd, "skipped": skipped, "quality": q}


async def _write_quality_log(db, batch_no, q, now):
    warn = sum(q.values())
    if warn == 0:
        return
    db.add(LogDataQuality(check_date=now.date(), check_code="baison_warehouse_sync",
                          check_name="百胜仓库档案同步数据质量", module="inventory",
                          result_status="warning", affected_count=warn,
                          detail={"batch_no": batch_no, **q}, ai_blocked=False))
    await db.flush()


def _new_batch():
    return "BAISON_WH_" + datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6].upper()


def _finish_log(log, status, r, start_at, total_rows=None):
    log.status = status
    log.success_rows = r.get("dim_inserted", 0) + r.get("dim_updated", 0)
    log.error_rows = r.get("skipped", 0)
    log.total_rows = total_rows if total_rows is not None else log.success_rows + log.error_rows
    log.end_at = datetime.now(timezone.utc)
    log.duration_seconds = int((log.end_at - start_at).total_seconds())


async def _fail(db, log, exc, start_at, batch_no):
    logger.warning("baison warehouse sync failed [%s]: %s", batch_no, exc.__class__.__name__)
    log.status = "failed"
    log.error_detail = [{"error": str(exc)[:300]}]
    log.end_at = datetime.now(timezone.utc)
    log.duration_seconds = int((log.end_at - start_at).total_seconds())
    await db.flush()
    return {"batch_no": batch_no, "ok": False, "status": "failed",
            "error": f"{exc.__class__.__name__}: {str(exc)[:300]}"}


async def import_warehouse_page(db, page=1, page_size=20, opt_user_code="000", operator_id=None, **filters) -> dict:
    batch_no = _new_batch()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="warehouse",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log); await db.flush()
    try:
        fetched = await asyncio.to_thread(fetch_warehouse_page, page, page_size, opt_user_code, None, **filters)
        if not fetched["ok"]:
            raise ValueError(f"百胜返回失败: {fetched['message']}")
        now = datetime.now(timezone.utc)
        r = await _upsert_warehouses(db, fetched["warehouses"], batch_no, now)
        await _write_quality_log(db, batch_no, r["quality"], now)
        await db.flush()
        filt = fetched["filter"]
        _finish_log(log, "success", r, start_at, total_rows=len(fetched["warehouses"]))
        await db.flush()
        return {"batch_no": batch_no, "ok": True, "status": "success", "method": WAREHOUSE_LIST_METHOD,
                "page_count": filt.get("page_count"), "record_count": filt.get("record_count"),
                "sample": [{k: w.get(k) for k in ("ckdm", "ckmc", "ckxz", "qy_id_name", "ty")} for w in fetched["warehouses"][:3]],
                **{k: r[k] for k in ("ods_inserted", "ods_updated", "dim_inserted", "dim_updated", "skipped")},
                "quality": r["quality"]}
    except Exception as exc:
        return await _fail(db, log, exc, start_at, batch_no)


async def import_all_warehouses(db, page_size=20, opt_user_code="000", operator_id=None, **filters) -> dict:
    batch_no = _new_batch()
    start_at = datetime.now(timezone.utc)
    log = LogDataSync(batch_no=batch_no, source_system="baison", data_type="warehouse",
                      sync_type="api", status="running", operator_id=operator_id)
    db.add(log); await db.flush()
    agg = {"ods_inserted": 0, "ods_updated": 0, "dim_inserted": 0, "dim_updated": 0, "skipped": 0}
    q_total = {k: 0 for k in _Q_KEYS}
    try:
        now = datetime.now(timezone.utc)
        first = await asyncio.to_thread(fetch_warehouse_page, 1, page_size, opt_user_code, None, **filters)
        if not first["ok"]:
            raise ValueError(f"百胜返回失败: {first['message']}")
        filt = first["filter"]
        page_count = int(filt.get("page_count") or 1)
        record_count = int(filt.get("record_count") or 0)

        def _accum(r):
            for k in agg:
                agg[k] += r[k]
            for k in q_total:
                q_total[k] += r["quality"][k]

        _accum(await _upsert_warehouses(db, first["warehouses"], batch_no, now))
        await db.flush()
        for pno in range(2, page_count + 1):
            fp = await asyncio.to_thread(fetch_warehouse_page, pno, page_size, opt_user_code, None, **filters)
            if not fp["ok"]:
                raise ValueError(f"第{pno}页返回失败: {fp['message']}")
            _accum(await _upsert_warehouses(db, fp["warehouses"], batch_no, now))
            await db.flush()

        await _write_quality_log(db, batch_no, q_total, now)
        _finish_log(log, "success", agg, start_at, total_rows=agg["dim_inserted"] + agg["dim_updated"] + agg["skipped"])
        await db.flush()
        return {"batch_no": batch_no, "ok": True, "status": "success", "method": WAREHOUSE_LIST_METHOD,
                "page_count": page_count, "record_count": record_count, **agg, "quality": q_total}
    except Exception as exc:
        res = await _fail(db, log, exc, start_at, batch_no)
        res.update(agg)
        return res
