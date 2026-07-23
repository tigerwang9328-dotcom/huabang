"""
退货数据统计（下单时间口径） — 供 /finance/settings/daily-ad-costs 页「退货数据」模块用。
口径与本项目退款率表一致：
- 下单时间(order_date) 窗口，按 shop_id 分组（显示最新店名），按店铺名(店号自然序)排序
- 已发货 = status Sent；已退 = 关联退款单 status Confirmed；待退 = WaitConfirm；排除 换货/补发
- 预估退款率 = (已发货待退款 + 已发货已退款) / 订单总数
- 仅退款率   = (订单总数 - 已发货) / 订单总数

数据源：中台已同步 ODS（ods_jst_orders_raw + ods_jst_refunds_raw）。
⚠️ 返回两个时间：computed_at=计算时刻；data_as_of=ODS 最后同步时刻(真实数据新鲜度)。两者差得大 = 数据偏旧。
⚠️ 计算需解析百万级 JSON（CPU 密集），必须用同步引擎在【线程】里跑（asyncio.to_thread），不能直接占 Web async 事件循环。
"""
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text
from app.config.settings import settings

_TYPES = {"普通退货", "仅退款", "拒收退货"}
_SEQ_RE = re.compile(r"([A-Z]\d+-\d+)\s*$")
_NUM_RE = re.compile(r"\s*([0-9]+(?:\.[0-9]+)?)")


def _seq(name: str) -> str:
    m = _SEQ_RE.search(name or "")
    return m.group(1) if m else ""


# 下单日期抽取表达式：与函数式索引 ix_ods_jst_orders_raw_order_date 必须逐字一致，否则不会走索引。
_ORDER_DATE_EXPR = r'''substring(raw_json from '"order_date":\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})')'''


def compute_return_stats_sync(start_date: str, end_date_excl: str) -> dict:
    """同步函数（在线程中执行）。start_date <= order_date < end_date_excl，均 'YYYY-MM-DD'。"""
    engine = create_engine(settings.SYNC_DATABASE_URL)
    data_as_of = None
    try:
        oinfo, sname, smod = {}, {}, {}
        with engine.connect().execution_options(stream_results=True) as c:
            # 用 substring 正则从 raw_json 文本直接抽取下单日期(YYYY-MM-DD)，避免逐行 ::json 全文解析；
            # 表达式与 ix_ods_jst_orders_raw_order_date 完全一致，使该范围查询走索引(原为全表 1.7M 行 JSON 解析→超时)。
            res = c.execute(text(
                f"SELECT raw_json FROM ods_jst_orders_raw WHERE {_ORDER_DATE_EXPR} >= :s AND {_ORDER_DATE_EXPR} < :e"
            ), {"s": start_date, "e": end_date_excl})
            for (raw,) in res.yield_per(5000):
                try:
                    j = json.loads(raw)
                except Exception:
                    continue
                oid = j.get("o_id"); sid = j.get("shop_id"); mod = j.get("modified") or ""
                oinfo[oid] = (sid, j.get("status") == "Sent")
                if mod >= smod.get(sid, ""):
                    smod[sid] = mod; sname[sid] = j.get("shop_name")

        oset = set(oinfo)
        oref = {}
        with engine.connect().execution_options(stream_results=True) as c:
            res = c.execute(text("SELECT raw_json FROM ods_jst_refunds_raw"))
            for (raw,) in res.yield_per(5000):
                try:
                    j = json.loads(raw)
                except Exception:
                    continue
                oid = j.get("o_id")
                if oid not in oset or j.get("type") not in _TYPES:
                    continue
                d = oref.setdefault(oid, {"c": False, "w": False})
                s = j.get("status")
                if s == "Confirmed":
                    d["c"] = True
                elif s == "WaitConfirm":
                    d["w"] = True

        # 聚水潭 shop_id -> 中台 store_id（store_code 即 JST shop_id），用于分组/写参数
        with engine.connect() as c:
            code2id = {str(r[1]): int(r[0]) for r in c.execute(text("SELECT id, store_code FROM biz_stores WHERE store_code IS NOT NULL")).fetchall()}
        # 数据新鲜度：取订单/退款表最后一次同步(updated_at)较早者 = 数据截至时间
        with engine.connect() as c:
            mo = c.execute(text("SELECT max(updated_at) FROM ods_jst_orders_raw")).scalar()
            mr = c.execute(text("SELECT max(updated_at) FROM ods_jst_refunds_raw")).scalar()
        cands = [x for x in (mo, mr) if x is not None]
        if cands:
            # DB updated_at 是 naive UTC，转北京时间与 computed_at 对齐
            _dt = min(cands).replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
            data_as_of = _dt.strftime("%Y-%m-%d %H:%M:%S")
    finally:
        engine.dispose()

    agg = {}
    for oid, (sid, sent) in oinfo.items():
        a = agg.setdefault(sid, {"total": 0, "shipped": 0, "rf": 0, "pd": 0})
        a["total"] += 1
        d = oref.get(oid)
        if sent:
            a["shipped"] += 1
            if d:
                if d["c"]:
                    a["rf"] += 1
                if d["w"]:
                    a["pd"] += 1

    def _name_key(sid):
        nm = sname.get(sid, str(sid)) or ""
        m = _NUM_RE.match(nm)
        return (0, float(m.group(1)), nm) if m else (1, 0.0, nm)

    rows = []
    for sid in sorted(agg.keys(), key=_name_key):
        a = agg[sid]
        nm = sname.get(sid, str(sid))
        tot = a["total"]
        rows.append({
            "store_id": code2id.get(str(sid)),
            "shop_id": sid,
            "seq": _seq(nm),
            "store_name": nm,
            "pending_refund": a["pd"],
            "refunded": a["rf"],
            "shipped": a["shipped"],
            "total": tot,
            "est_refund_rate": round((a["pd"] + a["rf"]) / tot, 6) if tot else 0,
            "only_refund_rate": round((tot - a["shipped"]) / tot, 6) if tot else 0,
        })

    return {
        "computed_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
        "data_as_of": data_as_of,
        "start_date": start_date,
        "end_date_excl": end_date_excl,
        "rows": rows,
        "totals": {
            "total": sum(a["total"] for a in agg.values()),
            "shipped": sum(a["shipped"] for a in agg.values()),
            "refunded": sum(a["rf"] for a in agg.values()),
            "pending_refund": sum(a["pd"] for a in agg.values()),
        },
    }


# ───────────────────────────────────────────────────────────────────────────
# 款式(SPU)退货退款统计 —— 与 compute_return_stats_sync 完全同口径，仅维度由「店铺」改为「款式」。
#   计数单位：按订单数（窗口内含该款的去重订单数）
#   退款归属：整单归属（一个含多款的订单若发生退款，计入它所含的每个款式 —— 同原页订单级口径）
#   已退=订单有 Confirmed 退款；待退=订单有 WaitConfirm 退款；二者仅在「已发货(Sent)」订单中计；
#   退款类型仅 {普通退货,仅退款,拒收退货}；退款锚定下单订单(不按退款时间过滤)，一切按下单时间。
# 数据源走 DWD：dwd_sales_order_items(带 spu_id) + dwd_refund_orders(order_no 关联) + ods 取退款 type。
# ───────────────────────────────────────────────────────────────────────────
_SPU_RETURN_SQL = '''
WITH win_items AS (
    SELECT DISTINCT oi.order_no, oi.spu_id, oi.order_status
    FROM dwd_sales_order_items oi
    WHERE oi.order_date >= :s AND oi.order_date < :e
      AND oi.is_gift = false
      AND oi.spu_id IS NOT NULL AND oi.spu_id <> ''
),
win_orders AS (SELECT DISTINCT order_no FROM win_items),
ref AS (
    SELECT d.order_no,
           bool_or(d.status = 'Confirmed')   AS hc,
           bool_or(d.status = 'WaitConfirm') AS hw
    FROM dwd_refund_orders d
    JOIN win_orders w ON w.order_no = d.order_no
    JOIN ods_jst_refunds_raw o ON o.refund_no = d.refund_no
    WHERE (o.raw_json::json->>'type') IN ('普通退货', '仅退款', '拒收退货')
    GROUP BY d.order_no
),
joined AS (
    SELECT wi.spu_id,
           (wi.order_status = 'Sent') AS sent,
           COALESCE(r.hc, false)      AS hc,
           COALESCE(r.hw, false)      AS hw
    FROM win_items wi
    LEFT JOIN ref r ON r.order_no = wi.order_no
),
agg AS (
    SELECT spu_id,
           count(*)                                AS total,
           count(*) FILTER (WHERE sent)            AS shipped,
           count(*) FILTER (WHERE sent AND hc)     AS refunded,
           count(*) FILTER (WHERE sent AND hw)     AS pending,
           count(*) FILTER (WHERE hc)              AS rc_all,
           count(*) FILTER (WHERE hw)              AS rw_all
    FROM joined
    GROUP BY spu_id
)
SELECT a.spu_id, p.spu_name, a.total, a.shipped, a.refunded, a.pending, a.rc_all, a.rw_all
FROM agg a
LEFT JOIN dim_product_spu p ON p.spu_id = a.spu_id
ORDER BY a.total DESC, a.spu_id
'''


def compute_spu_return_stats_sync(start_date: str, end_date_excl: str) -> dict:
    '''同步函数（在线程中执行）。start_date <= order_date < end_date_excl，均 YYYY-MM-DD。'''
    engine = create_engine(settings.SYNC_DATABASE_URL)
    data_as_of = None
    try:
        with engine.connect() as c:
            rows = c.execute(text(_SPU_RETURN_SQL), {'s': start_date, 'e': end_date_excl}).fetchall()
            mo = c.execute(text('SELECT max(updated_at) FROM ods_jst_orders_raw')).scalar()
            mr = c.execute(text('SELECT max(updated_at) FROM ods_jst_refunds_raw')).scalar()
        cands = [x for x in (mo, mr) if x is not None]
        if cands:
            _dt = min(cands).replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Shanghai'))
            data_as_of = _dt.strftime('%Y-%m-%d %H:%M:%S')
    finally:
        engine.dispose()

    out = []
    t_total = t_shipped = t_rf = t_pd = t_incl = 0
    for r in rows:
        tot = int(r.total or 0)
        sh = int(r.shipped or 0)
        rf = int(r.refunded or 0)
        pd = int(r.pending or 0)
        # 含未发货：不限发货状态的已退/待退（用于「总退款率」）
        refund_incl = int(r.rc_all or 0) + int(r.rw_all or 0)
        t_total += tot; t_shipped += sh; t_rf += rf; t_pd += pd; t_incl += refund_incl
        out.append({
            'spu_id': r.spu_id,
            'spu_name': r.spu_name,
            'spu_name_missing': (r.spu_name is None or r.spu_name == ''),
            'pending_refund': pd,
            'refunded': rf,
            'shipped': sh,
            'total': tot,
            'refund_incl': refund_incl,
            'est_refund_rate': round((pd + rf) / tot, 6) if tot else 0,
            'only_refund_rate': round((tot - sh) / tot, 6) if tot else 0,
            'total_refund_rate': round(refund_incl / tot, 6) if tot else 0,
        })

    return {
        'computed_at': datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'),
        'data_as_of': data_as_of,
        'start_date': start_date,
        'end_date_excl': end_date_excl,
        'rows': out,
        'totals': {'total': t_total, 'shipped': t_shipped, 'refunded': t_rf, 'pending_refund': t_pd, 'refund_incl': t_incl},
    }


# ───────────────────────────────────────────────────────────────────────────
# 款式退货退款 —— 每日定时预算 + 磁盘缓存（页面常态直接读缓存，无需点「计算」）。
# 默认滚动窗口：前 20 ~ 前 10 天（含两端，按 CST 业务日期）。
# 缓存落盘（参考 snapshot_service 落盘约定），避免新增 DB 表 / alembic 迁移。
# ───────────────────────────────────────────────────────────────────────────
import os as _os
import json as _json
import tempfile as _tempfile

_SPU_RETURN_CACHE_PATH = '/srv/mumaren_ai_platform/data/cache/spu_return_latest.json'
_SPU_DEFAULT_FROM_DAYS = 20   # 窗口起：前 20 天
_SPU_DEFAULT_TO_DAYS = 10     # 窗口止：前 10 天


def _spu_default_window():
    '''返回默认滚动窗口 (date_from_incl, date_to_incl, end_excl) 字符串，按 CST 当天。'''
    from datetime import timedelta
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    d0 = today - timedelta(days=_SPU_DEFAULT_FROM_DAYS)
    d1 = today - timedelta(days=_SPU_DEFAULT_TO_DAYS)
    return d0.isoformat(), d1.isoformat(), (d1 + timedelta(days=1)).isoformat()


def compute_and_cache_spu_return_default() -> dict:
    '''计算默认滚动窗口的款式退货退款并原子落盘缓存。供每日定时任务调用。'''
    d_from, d_to, end_excl = _spu_default_window()
    payload = compute_spu_return_stats_sync(d_from, end_excl)
    # 补充展示用窗口（含两端）+ 缓存生成标记
    payload['date_from'] = d_from
    payload['date_to'] = d_to
    payload['window_days'] = f'{_SPU_DEFAULT_FROM_DAYS}~{_SPU_DEFAULT_TO_DAYS}'
    payload['cached'] = True

    _os.makedirs(_os.path.dirname(_SPU_RETURN_CACHE_PATH), exist_ok=True)
    fd, tmp = _tempfile.mkstemp(dir=_os.path.dirname(_SPU_RETURN_CACHE_PATH), suffix='.tmp')
    try:
        with _os.fdopen(fd, 'w', encoding='utf-8') as f:
            _json.dump(payload, f, ensure_ascii=False)
        _os.replace(tmp, _SPU_RETURN_CACHE_PATH)   # 原子替换
    except Exception:
        try:
            _os.unlink(tmp)
        except OSError:
            pass
        raise
    return payload


def read_spu_return_cache() -> dict | None:
    '''读取磁盘缓存；不存在 / 损坏返回 None。'''
    try:
        with open(_SPU_RETURN_CACHE_PATH, encoding='utf-8') as f:
            return _json.load(f)
    except (FileNotFoundError, ValueError):
        return None


# ───────────────────────────────────────────────────────────────────────────
# 店铺级预估退货率缓存 —— 每日定时生成（下单时间口径），供 dashboard 读取
# ───────────────────────────────────────────────────────────────────────────
_STORE_RETURN_CACHE_PATH = '/srv/mumaren_ai_platform/data/cache/store_return_latest.json'


def compute_and_cache_store_return_default() -> dict:
    '''计算默认滚动窗口的店铺级预估退货率并原子落盘缓存。供每日定时任务调用。

    复用 compute_return_stats_sync（与退货退款查询页同口径），同时保留完整 rows
    供前端面板秒开展示，以及 rates 字典供 dashboard 快速覆盖 refund_rate。
    '''
    d_from, d_to, end_excl = _spu_default_window()
    payload = compute_return_stats_sync(d_from, end_excl)

    rates = {}
    for row in payload.get("rows", []):
        sid = row.get("store_id")
        if sid is not None:
            rates[str(sid)] = row.get("est_refund_rate", 0)

    cache = {
        "computed_at": payload.get("computed_at"),
        "data_as_of": payload.get("data_as_of"),
        "start_date": payload.get("start_date"),
        "end_date_excl": payload.get("end_date_excl"),
        "date_from": d_from,
        "date_to": d_to,
        "window_days": f'{_SPU_DEFAULT_FROM_DAYS}~{_SPU_DEFAULT_TO_DAYS}',
        "cached": True,
        "rates": rates,
        "rows": payload.get("rows", []),
        "totals": payload.get("totals", {}),
    }

    _os.makedirs(_os.path.dirname(_STORE_RETURN_CACHE_PATH), exist_ok=True)
    fd, tmp = _tempfile.mkstemp(dir=_os.path.dirname(_STORE_RETURN_CACHE_PATH), suffix='.tmp')
    try:
        with _os.fdopen(fd, 'w', encoding='utf-8') as f:
            _json.dump(cache, f, ensure_ascii=False)
        _os.replace(tmp, _STORE_RETURN_CACHE_PATH)
    except Exception:
        try:
            _os.unlink(tmp)
        except OSError:
            pass
        raise
    return cache


def read_store_return_cache() -> dict | None:
    '''读取店铺级预估退货率磁盘缓存；不存在 / 损坏返回 None。'''
    try:
        with open(_STORE_RETURN_CACHE_PATH, encoding='utf-8') as f:
            return _json.load(f)
    except (FileNotFoundError, ValueError):
        return None
