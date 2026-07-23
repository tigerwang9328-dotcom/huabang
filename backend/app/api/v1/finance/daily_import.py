"""
日报统一导入  /api/v1/finance/daily-import/*
一张表同时导入「月参数」(finance_store_daily_params, 按月) + 「广告费/赔付/广告费备注」(finance_store_daily_ad_costs, 按日)。
- 弹窗选一个日期：月参数写入该日期所在月份；广告费和赔付写入该日期当天。
- 模板格式与 dashboard 店铺经营日报「下载日报」一致：成员店按层级缩进、每个店铺组在块末有「组名 合计（N店）」行（平台列="组"），嵌套同序。
  · 在成员行填 → 应用到该店；在组「合计」行填 → 应用到全组（广告费和赔付按成员销售额拆分、参数复制到每家成员）。
  · 成员行优先级高于组行；子组优先级高于父组（更具体者覆盖）。
- 按 (店铺名, 平台) 匹配活跃店铺；留空=保持原样不修改（清零需显式填 0）。
"""
import io
import re
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User

router = APIRouter(prefix="/finance/daily-import")

PARAM_COLUMNS = [
    ("店铺",          "store_name",                    None,  None, None),
    ("平台",          "platform",                      None,  None, None),
    ("平台收入系数",  "platform_income_rate",          False, 0,    1.5),
    ("预估退货率",    "estimated_return_rate",         True,  0,    100),
    ("仅退款率",      "refund_only_rate",              True,  0,    100),
    ("运费险/件",     "freight_insurance_unit_cost",   False, 0,    100),
    ("快递费/件",     "express_unit_cost",             False, 0,    100),
    ("包装费/单",     "package_unit_cost",             False, 0,    100),
    ("推广单件",      "promotion_unit_cost",           False, 0,    1000),
    ("退货人工/件",   "return_labor_unit_cost",        False, 0,    100),
    ("货值损耗/件",   "goods_loss_unit_cost",          False, 0,    1000),
    ("退货率阈值",    "return_rate_warning_threshold", True,  0,    100),
    ("备注",          "remark",                        None,  None, None),
]
AD_COST_LABEL = "广告费"
COMPENSATION_LABEL = "发货赔付、其他赔付"
AD_REMARK_LABEL = "广告费备注"
GROUP_PLATFORM_TAG = "组"
ALL_HEADERS = [c[0] for c in PARAM_COLUMNS] + [AD_COST_LABEL, COMPENSATION_LABEL, AD_REMARK_LABEL]
HEADER_ALIASES = {
    "预估退货率": ["预估退货率(%)", "预计退货率", "预计退货率(%)"],
    "仅退款率": ["仅退款率(%)", "仅退货率", "仅退货率(%)"],
    "退货率阈值": ["退货率阈值(%)"],
}

_PARAM_NUMERIC = [c for c in PARAM_COLUMNS if c[2] is not None]
_PERCENT_FIELDS = {c[1] for c in PARAM_COLUMNS if c[2] is True}
_PARAM_FIELDS = [c[1] for c in PARAM_COLUMNS]
_GROUP_TOTAL_RE = re.compile(r"\s*合计[（(]\s*\d+\s*店[）)]\s*$")


async def _stores_with_sale(db: AsyncSession, biz_date):
    r = await db.execute(text("""
        SELECT s.id AS store_id, s.store_name, COALESCE(bp.name,'') AS platform,
               COALESCE(dm.sale_amount, 0) AS sale_amount
        FROM biz_stores s
        LEFT JOIN biz_platforms bp ON bp.id = s.platform_id
        LEFT JOIN dm_store_daily dm ON dm.store_id = s.id AND dm.biz_date = :dt
        WHERE s.is_active = true
        ORDER BY s.store_name
    """), {"dt": biz_date})
    return [dict(row) for row in r.mappings()]


def _parse_num(val, col):
    label, field, is_pct, lo, hi = col
    if val is None or str(val).strip() == "":
        return None, None
    raw = str(val).strip()
    try:
        n = float(raw.rstrip("%"))
    except ValueError:
        return None, f"【{label}】非数字：{val}"
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        return None, f"【{label}】超出范围 {lo}~{hi}：{n}"
    return n, None


def _subtree_ids(gid, children_of, members_of):
    ids = list(members_of.get(gid, []))
    for c in children_of.get(gid, []):
        ids += _subtree_ids(c, children_of, members_of)
    return ids


@router.get("/template")
async def template(
    biz_date: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """模板格式同 dashboard 日报：成员缩进 + 组「合计」行（平台列=组），嵌套同序、按销售额降序。"""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font
    from app.services.finance.store_report_group_util import load_group_tree

    dt = None
    if biz_date:
        try:
            dt = date.fromisoformat(str(biz_date))
        except (ValueError, TypeError):
            dt = None

    stores = await _stores_with_sale(db, dt)
    month = (dt or date.today()).strftime("%Y-%m")
    params_rows = await db.execute(text("""
        SELECT *
        FROM finance_store_daily_params
        WHERE month = :month
    """), {"month": month})
    params_by_store = {
        int(row["store_id"]): dict(row)
        for row in params_rows.mappings()
    }
    ad_rows = await db.execute(text("""
        SELECT store_id, ad_cost, compensation_amount, remark
        FROM finance_store_daily_ad_costs
        WHERE biz_date = :dt
    """), {"dt": dt})
    ad_by_store = {
        int(row["store_id"]): dict(row)
        for row in ad_rows.mappings()
    }
    groups_by_id, children_of, members_of = await load_group_tree(db)
    by_id = {int(s["store_id"]): s for s in stores}
    sale = lambda s: float(s.get("sale_amount") or 0)

    def group_sale(gid):
        return sum(sale(by_id[x]) for x in _subtree_ids(gid, children_of, members_of) if x in by_id)

    def group_count(gid):
        return len([x for x in _subtree_ids(gid, children_of, members_of) if x in by_id])

    # 构造有序行：(kind, level, payload)
    ordered = []

    def emit(gid, depth):
        entries = []
        for sid in members_of.get(gid, []):
            if sid in by_id:
                entries.append(("store", sale(by_id[sid]), sid))
        for cid in children_of.get(gid, []):
            entries.append(("group", group_sale(cid), cid))
        entries.sort(key=lambda e: e[1], reverse=True)
        for kind, _k, obj in entries:
            if kind == "store":
                ordered.append(("store", depth + 1, by_id[obj]))
            else:
                emit(obj, depth + 1)
        ordered.append(("group", depth, gid))

    grouped = set()
    for ids in members_of.values():
        grouped.update(ids)
    top = []
    for s in stores:
        if int(s["store_id"]) not in grouped:
            top.append(("store", sale(s), s))
    for gid in children_of.get(None, []):
        top.append(("group", group_sale(gid), gid))
    top.sort(key=lambda e: e[1], reverse=True)
    for kind, _k, obj in top:
        if kind == "store":
            ordered.append(("store", 0, obj))
        else:
            emit(obj, 0)

    wb = Workbook()
    ws = wb.active
    ws.title = "日报导入"
    ws.append(ALL_HEADERS)
    percent_col_indexes = [
        idx + 1
        for idx, (_label, _field, is_pct, _lo, _hi) in enumerate(PARAM_COLUMNS)
        if is_pct is True
    ]
    ad_cost_col = ALL_HEADERS.index(AD_COST_LABEL) + 1
    grp_fill = PatternFill("solid", fgColor="FFF3CD")
    bold = Font(bold=True)
    for kind, level, payload in ordered:
        row = [""] * len(ALL_HEADERS)
        indent = "　" * level
        if kind == "store":
            store_id = int(payload["store_id"])
            params = params_by_store.get(store_id, {})
            ad = ad_by_store.get(store_id, {})
            row[0] = indent + payload["store_name"]
            row[1] = payload["platform"]
            for col_idx, (_label, field, is_pct, _lo, _hi) in enumerate(PARAM_COLUMNS):
                if field in ("store_name", "platform"):
                    continue
                val = params.get(field)
                if val is None:
                    continue
                if is_pct is None:
                    row[col_idx] = val
                    continue
                val = float(val)
                row[col_idx] = round(val * 100, 4) if is_pct is True else val
            row[ALL_HEADERS.index(AD_COST_LABEL)] = float(ad["ad_cost"]) if ad.get("ad_cost") is not None else None
            row[ALL_HEADERS.index(COMPENSATION_LABEL)] = float(ad["compensation_amount"]) if ad.get("compensation_amount") is not None else None
            row[ALL_HEADERS.index(AD_REMARK_LABEL)] = ad.get("remark") or None
            ws.append(row)
            for col in percent_col_indexes:
                ws.cell(row=ws.max_row, column=col).number_format = "0"
            ws.cell(row=ws.max_row, column=ad_cost_col).number_format = "#,##0"
        else:
            g = groups_by_id[payload]
            row[0] = indent + f"{g['name']} 合计（{group_count(payload)}店）"
            row[1] = GROUP_PLATFORM_TAG
            ws.append(row)
            for col in range(1, len(ALL_HEADERS) + 1):
                c = ws.cell(row=ws.max_row, column=col)
                c.fill = grp_fill
                if col == 1:
                    c.font = bold

    buf = io.BytesIO()
    wb.save(buf)
    import urllib.parse
    fn = urllib.parse.quote("牧马人日报导入模板.xlsx")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"daily_import_template.xlsx\"; filename*=UTF-8''{fn}"},
    )


async def _load_groups_meta(db: AsyncSession):
    """{组名: {id, depth, member_ids(子树去重)}}（仅启用组）"""
    from app.services.finance.store_report_group_util import load_group_tree
    groups_by_id, children_of, members_of = await load_group_tree(db)
    depth_of = {}

    def compute(gid, d):
        depth_of[gid] = d
        for c in children_of.get(gid, []):
            compute(c, d + 1)
    for gid in children_of.get(None, []):
        compute(gid, 0)
    out = {}
    for gid, g in groups_by_id.items():
        ids = list(dict.fromkeys(_subtree_ids(gid, children_of, members_of)))
        out[g["name"].strip()] = {"id": gid, "depth": depth_of.get(gid, 0), "member_ids": ids}
    return out


def _split_ad(ad_val, member_ids, sale_map):
    alloc = {}
    tot = sum(sale_map.get(m, 0) for m in member_ids)
    if tot > 0:
        allocated = 0.0
        for i, m in enumerate(member_ids):
            share = round(ad_val - allocated, 2) if i == len(member_ids) - 1 else round(ad_val * sale_map.get(m, 0) / tot, 2)
            allocated += share
            alloc[m] = share if share > 0 else 0
    else:
        each = round(ad_val / len(member_ids), 2)
        for m in member_ids:
            alloc[m] = each
    return alloc


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    biz_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="仅支持 .xlsx 文件")
    try:
        bd = date.fromisoformat(str(biz_date))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="日期格式错误，须为 YYYY-MM-DD")
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception:
        raise HTTPException(status_code=422, detail="表格解析失败，请用下载的模板填写")
    if not rows:
        raise HTTPException(status_code=422, detail="表格为空")

    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    if "店铺" not in header:
        raise HTTPException(status_code=422, detail="缺少列：店铺")
    idx = {}
    for label in ALL_HEADERS:
        labels = [label] + HEADER_ALIASES.get(label, [])
        for candidate in labels:
            if candidate in header:
                idx[label] = header.index(candidate)
                break

    stores = await _stores_with_sale(db, bd)
    by_np, by_name, store_by_id, sale_map = {}, {}, {}, {}
    for s in stores:
        by_np[(s["store_name"].strip(), (s["platform"] or "").strip())] = s
        by_name.setdefault(s["store_name"].strip(), []).append(s)
        store_by_id[int(s["store_id"])] = s
        sale_map[int(s["store_id"])] = float(s.get("sale_amount") or 0)

    groups_meta = await _load_groups_meta(db)

    group_fills, store_fills, unmatched, errors = [], [], [], []

    for ri, raw in enumerate(rows[1:], start=2):
        def pcell(label):
            i = idx.get(label)
            if i is None:
                return None
            return raw[i] if i < len(raw) else None

        store_cell = pcell("店铺")
        store_text = str(store_cell).strip() if store_cell is not None else ""
        plat_cell = pcell("平台")
        plat_text = str(plat_cell).strip() if plat_cell is not None else ""

        def parse_row():
            vals, errs = {}, []
            for col in _PARAM_NUMERIC:
                nval, err = _parse_num(pcell(col[0]), col)
                if err:
                    errs.append(err)
                elif nval is not None:
                    vals[col[1]] = nval
            rm = pcell("备注")
            if rm is not None and str(rm).strip() != "":
                vals["remark"] = str(rm).strip()
            ad_val = None
            ad = pcell(AD_COST_LABEL)
            if ad is not None and str(ad).strip() != "":
                try:
                    v = float(str(ad).strip())
                    if v < 0:
                        errs.append(f"【广告费】不能为负：{v}")
                    else:
                        ad_val = v
                except ValueError:
                    errs.append(f"【广告费】非数字：{ad}")
            compensation_val = None
            comp = pcell(COMPENSATION_LABEL)
            if comp is not None and str(comp).strip() != "":
                try:
                    v = float(str(comp).strip())
                    if v < 0:
                        errs.append(f"【{COMPENSATION_LABEL}】不能为负：{v}")
                    else:
                        compensation_val = v
                except ValueError:
                    errs.append(f"【{COMPENSATION_LABEL}】非数字：{comp}")
            adr = pcell(AD_REMARK_LABEL)
            ad_remark = str(adr).strip() if (adr is not None and str(adr).strip() != "") else None
            return vals, ad_val, compensation_val, ad_remark, errs

        is_group_row = (plat_text == GROUP_PLATFORM_TAG) or bool(_GROUP_TOTAL_RE.search(store_text))
        if is_group_row:
            gname = _GROUP_TOTAL_RE.sub("", store_text).strip()
            g = groups_meta.get(gname)
            if not g:
                errors.append({"row": ri, "msg": f"未知店铺组：{gname or store_text}"})
                continue
            pvals, ad_val, compensation_val, ad_remark, errs = parse_row()
            for e in errs:
                errors.append({"row": ri, "msg": f"[{gname}] {e}"})
            if pvals or ad_val is not None or compensation_val is not None or ad_remark is not None:
                group_fills.append((g["depth"], gname, g["member_ids"], pvals, ad_val, compensation_val, ad_remark))
            continue

        if not store_text:
            continue
        store = by_np.get((store_text, plat_text))
        if store is None:
            cands = by_name.get(store_text, [])
            if len(cands) == 1:
                store = cands[0]
            elif len(cands) > 1:
                errors.append({"row": ri, "msg": f"店铺名「{store_text}」跨平台重名，请确认平台列"})
                continue
        if store is None:
            unmatched.append(store_text)
            continue
        pvals, ad_val, compensation_val, ad_remark, errs = parse_row()
        for e in errs:
            errors.append({"row": ri, "msg": e})
        if pvals or ad_val is not None or compensation_val is not None or ad_remark is not None:
            store_fills.append((store, pvals, ad_val, compensation_val, ad_remark))

    # 校验：laminar 下两个填写的组若成员有交集 => 存在上下级包含关系，只能填一层
    conflict = set()
    seen_pair = set()
    for i in range(len(group_fills)):
        for j in range(i + 1, len(group_fills)):
            gi, gj = group_fills[i][1], group_fills[j][1]
            if set(group_fills[i][2]) & set(group_fills[j][2]):
                conflict.add(gi); conflict.add(gj)
                key = tuple(sorted((gi, gj)))
                if key not in seen_pair:
                    seen_pair.add(key)
                    errors.append({"row": 0, "msg": f"店铺组「{gi}」与「{gj}」有上下级包含关系，不能同时填写，请只填其中一层"})

    # 合并：组行(浅→深) → 店铺行覆盖（更具体者优先）
    acc = {}

    def ensure(sid):
        s = store_by_id[sid]
        return acc.setdefault(sid, {"store_id": sid, "store_name": s["store_name"], "platform": s["platform"], "_group": None})

    for depth, gname, member_ids, pvals, ad_val, compensation_val, ad_remark in sorted(group_fills, key=lambda x: x[0]):
        if gname in conflict:
            continue
        mids = [m for m in member_ids if m in store_by_id]
        if not mids:
            errors.append({"row": 0, "msg": f"店铺组「{gname}」无可用成员店"})
            continue
        alloc = _split_ad(ad_val, mids, sale_map) if ad_val is not None else {}
        comp_alloc = _split_ad(compensation_val, mids, sale_map) if compensation_val is not None else {}
        for m in mids:
            it = ensure(m)
            it.update(pvals)
            if ad_val is not None:
                it["ad_cost"] = alloc.get(m, 0)
            if compensation_val is not None:
                it["compensation_amount"] = comp_alloc.get(m, 0)
            if ad_remark is not None:
                it["ad_remark"] = ad_remark
            it["_group"] = gname

    for store, pvals, ad_val, compensation_val, ad_remark in store_fills:
        it = ensure(int(store["store_id"]))
        it.update(pvals)
        if ad_val is not None:
            it["ad_cost"] = ad_val
        if compensation_val is not None:
            it["compensation_amount"] = compensation_val
        if ad_remark is not None:
            it["ad_remark"] = ad_remark
        it["_group"] = None

    matched = list(acc.values())
    return {"biz_date": biz_date, "month": biz_date[:7], "matched": matched,
            "unmatched": unmatched, "errors": errors}


@router.post("/commit")
async def commit(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    raw_date = body.get("biz_date")
    rows = body.get("rows") or []
    if not raw_date or not rows:
        raise HTTPException(status_code=422, detail="biz_date 和 rows 必填")
    try:
        biz_date = date.fromisoformat(str(raw_date))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="日期格式错误")
    month = biz_date.strftime("%Y-%m")

    param_count, ad_count, compensation_count = 0, 0, 0
    for row in rows:
        sid = row.get("store_id")
        if not sid:
            continue
        sid = int(sid)

        present = [f for f in _PARAM_FIELDS if f in row]
        param_value_fields = [f for f in present if f not in ("store_name", "platform")]
        if param_value_fields:
            vals = {"month": month, "store_id": sid, "updated_by": current_user.id}
            cols = []
            for f in present:
                v = row[f]
                if f in _PERCENT_FIELDS and v is not None:
                    v = float(v) / 100.0
                vals[f] = v
                cols.append(f)
            set_parts = ", ".join(f"{f}=:{f}" for f in cols)
            await db.execute(text(f"""
                INSERT INTO finance_store_daily_params (month, store_id, {', '.join(cols)}, updated_by)
                VALUES (:month, :store_id, {', '.join(':' + f for f in cols)}, :updated_by)
                ON CONFLICT (month, store_id) DO UPDATE SET
                    {set_parts}, updated_by=:updated_by, updated_at=NOW()
            """), vals)
            param_count += 1

        if "ad_cost" in row or "compensation_amount" in row or "ad_remark" in row:
            await db.execute(text("""
                INSERT INTO finance_store_daily_ad_costs (biz_date, store_id, ad_cost, compensation_amount, remark, updated_by)
                VALUES (:dt, :sid, COALESCE(:ad, 0), COALESCE(:compensation, 0), :remark, :uid)
                ON CONFLICT (biz_date, store_id) DO UPDATE SET
                    ad_cost = COALESCE(:ad, finance_store_daily_ad_costs.ad_cost),
                    compensation_amount = COALESCE(:compensation, finance_store_daily_ad_costs.compensation_amount),
                    remark = COALESCE(:remark, finance_store_daily_ad_costs.remark),
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
            """), {
                "dt": biz_date,
                "sid": sid,
                "ad": float(row["ad_cost"]) if "ad_cost" in row else None,
                "compensation": float(row["compensation_amount"]) if "compensation_amount" in row else None,
                "remark": row.get("ad_remark"),
                "uid": current_user.id,
            })
            if "ad_cost" in row:
                ad_count += 1
            if "compensation_amount" in row:
                compensation_count += 1

    await db.commit()
    return {"ok": True, "month": month, "biz_date": str(biz_date),
            "param_count": param_count, "ad_count": ad_count,
            "compensation_count": compensation_count}


# ─── 聚水潭「销售主题分析-财务-渠道」导入 ───────────────────────────────

JST_REQUIRED_HEADERS = ["渠道", "销售金额"]
JST_METRIC_HEADERS = [
    ("销售金额", "sale_amount", 0, 100000000),
    ("销售单数", "order_count", 0, 10000000),
    ("销售数量", "shipped_qty", 0, 10000000),
    ("销售成本", "sales_cogs", 0, 100000000),
    ("实发成本", "sale_cogs", 0, 100000000),
    ("当期实退金额", "refund_amount", 0, 100000000),
    ("当期实退数量", "refund_count", 0, 10000000),
    ("当期实退成本", "refund_cogs", 0, 100000000),
]
JST_IMPORT_FIELDS = [
    "sale_amount", "shipped_qty", "order_count", "sales_order_count",
    "sale_cogs", "sales_cogs", "refund_amount", "refund_count", "refund_cogs",
    "refund_rate", "operating_profit", "actual_order_count", "actual_product_qty",
    "source_channel",
]
JST_METRIC_VERSION = "jst_channel_finance_v1"


def _norm_store_key(value) -> str:
    s = str(value or "").strip()
    s = re.sub(r"^\s*\d+\s*[.．、]\s*", "", s)
    s = re.sub(r"[【\[].*?[】\]]", "", s)
    return re.sub(r"\s+", "", s).lower()


def _display_channel(value) -> str:
    return re.sub(r"^\s*\d+\s*[.．、]\s*", "", str(value or "").strip())


def _leading_store_no(value) -> str:
    m = re.match(r"^\s*(\d+)\s*[.．、]", str(value or "").strip())
    return m.group(1) if m else ""


def _shop_code(value) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    try:
        n = float(s.replace(",", ""))
        if n.is_integer():
            s = str(int(n))
    except ValueError:
        pass
    return s


def _platform_id_by_key(rows, key: str) -> int | None:
    for row in rows:
        if str(row.get("code") or "") == key:
            return int(row["id"])
    return None


async def _ensure_platform(db: AsyncSession, key: str, label: str) -> int:
    row = (await db.execute(text("""
        SELECT id
        FROM biz_platforms
        WHERE code = :key
    """), {"key": key})).mappings().first()
    if row:
        return int(row["id"])
    row = (await db.execute(text("""
        INSERT INTO biz_platforms (code, name, is_active, created_at, updated_at)
        VALUES (:key, :label, true, NOW(), NOW())
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            is_active = true,
            updated_at = NOW()
        RETURNING id
    """), {"key": key, "label": label})).mappings().first()
    return int(row["id"])


async def _ensure_jst_import_stores(db: AsyncSession, rows) -> list[dict]:
    """Create/reactivate stores that appear in a JST channel sheet but are missing locally."""
    idx = _header_index(rows)
    if "渠道" not in idx or "渠道编号" not in idx:
        return []

    platforms = (await db.execute(text("""
        SELECT id, code, name
        FROM biz_platforms
        WHERE is_active = true
    """))).mappings().all()

    from app.core.platform_resolver import resolve_store_platform

    created_or_updated = []
    seen_codes = set()
    for ri, raw in enumerate(rows[1:], start=2):
        channel = str(_cell_alias(raw, idx, ["渠道"]) or "").strip()
        code = _shop_code(_cell_alias(raw, idx, ["渠道编号"]))
        if not channel or not code or code in seen_codes:
            continue
        seen_codes.add(code)

        existing = (await db.execute(text("""
            SELECT s.id, s.store_name, s.is_active
            FROM biz_stores s
            WHERE s.store_code = :code
        """), {"code": code})).mappings().first()

        if existing:
            if existing["is_active"] is False:
                created_or_updated.append({
                    "row": ri,
                    "store_code": code,
                    "store_name": channel,
                    "status": "skipped_inactive",
                    "store_id": int(existing["id"]),
                    "reason": "本地店铺已停用，未自动启用",
                })
            continue

        if code == "0" or channel == "{线下}":
            platform_key = "other"
            platform_label = "其他"
        else:
            platform = resolve_store_platform(channel, None)
            platform_key = platform.key
            platform_label = platform.label

        platform_id = _platform_id_by_key(platforms, platform_key)
        if platform_id is None and platform_key == "other":
            platform_id = await _ensure_platform(db, platform_key, platform_label)
        if platform_id is None:
            created_or_updated.append({
                "row": ri,
                "store_code": code,
                "store_name": channel,
                "status": "skipped",
                "reason": f"平台「{platform_label}」未登记，无法自动建店",
            })
            continue

        new_store = (await db.execute(text("""
            INSERT INTO biz_stores (platform_id, store_code, store_name, is_active, created_at, updated_at)
            VALUES (:platform_id, :code, :name, true, NOW(), NOW())
            RETURNING id
        """), {"platform_id": platform_id, "code": code, "name": channel})).mappings().first()
        created_or_updated.append({
            "row": ri,
            "store_code": code,
            "store_name": channel,
            "status": "created",
            "store_id": int(new_store["id"]),
        })

    if created_or_updated:
        await db.commit()
    return created_or_updated


def _number_or_zero(value, label: str, lo: float, hi: float) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    try:
        n = float(str(value).replace(",", "").strip())
    except ValueError:
        raise ValueError(f"【{label}】非数字：{value}")
    if n < lo or n > hi:
        raise ValueError(f"【{label}】超出范围 {lo}~{hi}：{n}")
    return n


def _int_or_zero(value, label: str, lo: float, hi: float) -> int:
    return int(round(_number_or_zero(value, label, lo, hi)))


async def _active_store_matchers(db: AsyncSession):
    rows = await db.execute(text("""
        SELECT s.id AS store_id, s.store_code, s.store_name, COALESCE(bp.name,'') AS platform
        FROM biz_stores s
        LEFT JOIN biz_platforms bp ON bp.id = s.platform_id
        WHERE s.is_active = true
        ORDER BY s.store_name
    """))
    by_key, by_code, by_prefix = {}, {}, {}
    for row in rows.mappings():
        store = dict(row)
        code = _shop_code(store.get("store_code"))
        if code:
            by_code.setdefault(code, []).append(store)
        prefix = _leading_store_no(store["store_name"])
        if prefix:
            by_prefix.setdefault(prefix, []).append(store)
        keys = {
            _norm_store_key(store["store_name"]),
            _norm_store_key(f"{store['store_name']}【{store['platform']}】"),
        }
        for key in keys:
            if key:
                by_key.setdefault(key, []).append(store)
    return {"by_key": by_key, "by_code": by_code, "by_prefix": by_prefix}


def _pick_store(channel, matchers, shop_code=None):
    by_key = matchers.get("by_key", matchers)
    by_code = matchers.get("by_code", {})
    by_prefix = matchers.get("by_prefix", {})

    code = _shop_code(shop_code)
    if code:
        matches = by_code.get(code, [])
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"渠道编号「{code}」匹配到多家本地店铺，请检查店铺编码"

    prefix = _leading_store_no(channel)
    if prefix:
        matches = by_prefix.get(prefix, [])
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"店铺编号「{prefix}」匹配到多家本地店铺，请检查店铺名称"

    key = _norm_store_key(channel)
    matches = by_key.get(key, [])
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        from app.core.platform_resolver import resolve_store_platform
        hint = resolve_store_platform(str(channel), "").label
        if hint != "其他":
            narrowed = [
                m for m in matches
                if resolve_store_platform(m.get("store_name"), m.get("platform")).label == hint
            ]
            if len(narrowed) == 1:
                return narrowed[0], None
        return None, f"店铺名「{_display_channel(channel)}」匹配到多家本地店铺，请检查店铺名称"
    return None, None


def _parse_jst_rows(rows, matchers):
    if not rows:
        raise HTTPException(status_code=422, detail="表格为空")
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    for h in JST_REQUIRED_HEADERS:
        if h not in header:
            raise HTTPException(status_code=422, detail=f"缺少列：{h}")
    idx = {h: header.index(h) for h in header if h}
    matched, unmatched, errors = [], [], []

    def cell(raw, label):
        i = idx.get(label, -1)
        return raw[i] if i >= 0 and i < len(raw) else None

    for ri, raw in enumerate(rows[1:], start=2):
        channel = str(cell(raw, "渠道") or "").strip()
        if not channel:
            continue
        store, err = _pick_store(channel, matchers, cell(raw, "渠道编号"))
        if err:
            errors.append({"row": ri, "msg": err})
            continue
        if store is None:
            unmatched.append(_display_channel(channel))
            continue
        try:
            values = {}
            for label, field, lo, hi in JST_METRIC_HEADERS:
                if label not in idx:
                    continue
                if field in ("shipped_qty", "order_count", "sales_order_count", "refund_count"):
                    values[field] = _int_or_zero(cell(raw, label), label, lo, hi)
                else:
                    values[field] = _number_or_zero(cell(raw, label), label, lo, hi)
        except ValueError as e:
            errors.append({"row": ri, "msg": str(e)})
            continue

        if "sale_cogs" not in values:
            values["sale_cogs"] = float(values.get("sales_cogs") or 0)
        shipped_qty = int(values.get("shipped_qty") or 0)
        refund_count = int(values.get("refund_count") or 0)
        sale_amount = float(values.get("sale_amount") or 0)
        sale_cogs = float(values.get("sale_cogs") or 0)
        refund_amount = float(values.get("refund_amount") or 0)
        refund_cogs = float(values.get("refund_cogs") or 0)
        values["refund_rate"] = round(refund_count / shipped_qty, 6) if shipped_qty > 0 else 0
        values["operating_profit"] = round(sale_amount - sale_cogs - (refund_amount - refund_cogs), 2)
        values["source_channel"] = _display_channel(channel)
        values["store_id"] = int(store["store_id"])
        values["store_name"] = store["store_name"]
        values["platform"] = store["platform"]
        matched.append(values)

    return matched, unmatched, errors


def _header_index(rows):
    if not rows:
        raise HTTPException(status_code=422, detail="表格为空")
    return {str(h).strip(): i for i, h in enumerate(rows[0]) if h is not None and str(h).strip()}


def _cell_alias(raw, idx, labels):
    for label in labels:
        i = idx.get(label, -1)
        if i >= 0 and i < len(raw):
            return raw[i]
    return None


def _parse_jst_table_map(rows, matchers, table_label):
    idx = _header_index(rows)
    if "渠道" not in idx:
        raise HTTPException(status_code=422, detail=f"{table_label}缺少列：渠道")
    by_store, unmatched, errors = {}, [], []
    for ri, raw in enumerate(rows[1:], start=2):
        channel = str(_cell_alias(raw, idx, ["渠道"]) or "").strip()
        if not channel:
            continue
        store, err = _pick_store(channel, matchers, _cell_alias(raw, idx, ["渠道编号"]))
        if err:
            errors.append({"row": ri, "msg": f"{table_label}{err}"})
            continue
        if store is None:
            unmatched.append(_display_channel(channel))
            continue
        by_store[int(store["store_id"])] = {
            "row": raw,
            "idx": idx,
            "channel": _display_channel(channel),
            "store": store,
            "row_no": ri,
        }
    return by_store, unmatched, errors


def _num_alias(ctx, labels, field_label, default=0.0):
    val = _cell_alias(ctx["row"], ctx["idx"], labels)
    if val is None or str(val).strip() == "":
        return default
    return _number_or_zero(val, field_label, 0, 100000000)


def _int_alias(ctx, labels, field_label, default=0):
    val = _cell_alias(ctx["row"], ctx["idx"], labels)
    if val is None or str(val).strip() == "":
        return default
    return _int_or_zero(val, field_label, 0, 10000000)


def _parse_jst_two_tables(rows_one, rows_two, matchers):
    one_map, un1, err1 = _parse_jst_table_map(rows_one, matchers, "1表：")
    two_map, un2, err2 = _parse_jst_table_map(rows_two, matchers, "2表：")
    matched, errors = [], err1 + err2
    unmatched = list(dict.fromkeys(un1 + un2))

    for sid, one in one_map.items():
        store = one["store"]
        two = two_map.get(sid)
        try:
            sale_amount = _num_alias(one, ["销售金额"], "销售金额")
            order_count = _int_alias(one, ["销售单数"], "销售单数")
            shipped_qty = _int_alias(one, ["销售数量"], "销售数量")
            sale_cogs = _num_alias(one, ["产品成本", "销售成本", "实发成本"], "产品成本")
            refund_amount = _num_alias(one, ["当期实退金额", "退款金额"], "当期实退金额")
            refund_count = _int_alias(one, ["当期实退数量", "退货件数"], "当期实退数量")
            refund_cogs = _num_alias(one, ["当期实退成本", "退货成本冲回"], "当期实退成本")
            actual_order_count = _int_alias(two, ["实际订单数", "销售单数"], "实际订单数") if two else None
            actual_product_qty = _int_alias(two, ["产品件数", "销售数量"], "产品件数") if two else None
        except ValueError as e:
            errors.append({"row": one["row_no"], "msg": str(e)})
            continue

        refund_rate = round(refund_count / shipped_qty, 6) if shipped_qty > 0 else 0
        operating_profit = round(sale_amount - sale_cogs - (refund_amount - refund_cogs), 2)
        matched.append({
            "store_id": sid,
            "store_name": store["store_name"],
            "platform": store["platform"],
            "source_channel": one["channel"],
            "sale_amount": sale_amount,
            "order_count": order_count,
            "shipped_qty": shipped_qty,
            "sale_cogs": sale_cogs,
            "refund_amount": refund_amount,
            "refund_count": refund_count,
            "refund_cogs": refund_cogs,
            "refund_rate": refund_rate,
            "operating_profit": operating_profit,
            "actual_order_count": actual_order_count,
            "actual_product_qty": actual_product_qty,
            "source_mode": "jst_two_tables",
        })

    for sid, two in two_map.items():
        if sid not in one_map:
            unmatched.append(two["channel"])

    return matched, list(dict.fromkeys(unmatched)), errors


@router.post("/jst-channel/preview")
async def preview_jst_channel(
    file: UploadFile = File(...),
    biz_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="仅支持 .xlsx 文件")
    try:
        date.fromisoformat(str(biz_date))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="日期格式错误，须为 YYYY-MM-DD")
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True, read_only=True)
        rows = list(wb.active.iter_rows(values_only=True))
    except Exception:
        raise HTTPException(status_code=422, detail="表格解析失败，请上传聚水潭「销售主题分析-财务-渠道」xlsx")
    created_stores = await _ensure_jst_import_stores(db, rows)
    matched, unmatched, errors = _parse_jst_rows(rows, await _active_store_matchers(db))
    return {"biz_date": biz_date, "month": biz_date[:7], "matched": matched,
            "unmatched": unmatched, "errors": errors, "kind": "jst_channel",
            "created_stores": created_stores}


@router.post("/jst-channel/preview-two")
async def preview_jst_channel_two(
    file_one: UploadFile = File(...),
    file_two: UploadFile = File(...),
    biz_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not (file_one.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="1表仅支持 .xlsx 文件")
    if not (file_two.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="2表仅支持 .xlsx 文件")
    try:
        date.fromisoformat(str(biz_date))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="日期格式错误，须为 YYYY-MM-DD")
    try:
        from openpyxl import load_workbook
        wb1 = load_workbook(io.BytesIO(await file_one.read()), data_only=True, read_only=True)
        wb2 = load_workbook(io.BytesIO(await file_two.read()), data_only=True, read_only=True)
        rows_one = list(wb1.active.iter_rows(values_only=True))
        rows_two = list(wb2.active.iter_rows(values_only=True))
    except Exception:
        raise HTTPException(status_code=422, detail="表格解析失败，请上传聚水潭 xlsx")
    created_one = await _ensure_jst_import_stores(db, rows_one)
    created_two = await _ensure_jst_import_stores(db, rows_two)
    created_stores = created_one + [
        s for s in created_two
        if s.get("store_code") not in {x.get("store_code") for x in created_one}
    ]
    matched, unmatched, errors = _parse_jst_two_tables(rows_one, rows_two, await _active_store_matchers(db))
    return {"biz_date": biz_date, "month": biz_date[:7], "matched": matched,
            "unmatched": unmatched, "errors": errors, "kind": "jst_channel_two",
            "created_stores": created_stores}


@router.post("/jst-channel/commit")
async def commit_jst_channel(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    raw_date = body.get("biz_date")
    rows = body.get("rows") or []
    clear_missing = body.get("clear_missing") is True
    if not raw_date or not rows:
        raise HTTPException(status_code=422, detail="biz_date 和 rows 必填")
    try:
        biz_date = date.fromisoformat(str(raw_date))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="日期格式错误")

    imported = 0
    cleared_missing = 0
    imported_store_ids = []
    for row in rows:
        sid = row.get("store_id")
        if not sid:
            continue
        sid = int(sid)
        imported_store_ids.append(sid)
        vals = {f: row.get(f) for f in JST_IMPORT_FIELDS}
        await db.execute(text("""
            INSERT INTO dm_store_daily (
                store_id, biz_date, sale_amount, order_count, paid_qty, shipped_qty,
                actual_order_count, actual_product_qty,
                refund_amount, refund_count, refund_rate, ad_cost, roi,
                metric_version, sale_cogs, refund_cogs, operating_profit, missing_cost_skus,
                created_at, updated_at
            )
            VALUES (
                :sid, :dt, :sale_amount, :order_count, :shipped_qty, :shipped_qty,
                COALESCE(:actual_order_count, 0), COALESCE(:actual_product_qty, 0),
                :refund_amount, :refund_count, :refund_rate, 0, 0,
                :metric_version, :sale_cogs, :refund_cogs, :operating_profit, '[]'::jsonb,
                NOW(), NOW()
            )
            ON CONFLICT (store_id, biz_date) DO UPDATE SET
                sale_amount = EXCLUDED.sale_amount,
                order_count = EXCLUDED.order_count,
                paid_qty = EXCLUDED.paid_qty,
                shipped_qty = EXCLUDED.shipped_qty,
                actual_order_count = COALESCE(:actual_order_count, dm_store_daily.actual_order_count),
                actual_product_qty = COALESCE(:actual_product_qty, dm_store_daily.actual_product_qty),
                refund_amount = EXCLUDED.refund_amount,
                refund_count = EXCLUDED.refund_count,
                refund_rate = EXCLUDED.refund_rate,
                metric_version = EXCLUDED.metric_version,
                sale_cogs = EXCLUDED.sale_cogs,
                refund_cogs = EXCLUDED.refund_cogs,
                operating_profit = EXCLUDED.operating_profit,
                missing_cost_skus = EXCLUDED.missing_cost_skus,
                updated_at = NOW()
        """), {
                "sid": sid,
                "dt": biz_date,
                "sale_amount": float(vals.get("sale_amount") or 0),
            "order_count": int(vals.get("order_count") or 0),
            "shipped_qty": int(vals.get("shipped_qty") or 0),
            "actual_order_count": int(vals["actual_order_count"]) if vals.get("actual_order_count") is not None else None,
            "actual_product_qty": int(vals["actual_product_qty"]) if vals.get("actual_product_qty") is not None else None,
            "refund_amount": float(vals.get("refund_amount") or 0),
            "refund_count": int(vals.get("refund_count") or 0),
            "refund_rate": float(vals.get("refund_rate") or 0),
            "metric_version": JST_METRIC_VERSION,
            "sale_cogs": float(vals.get("sale_cogs") or 0),
            "refund_cogs": float(vals.get("refund_cogs") or 0),
            "operating_profit": float(vals.get("operating_profit") or 0),
        })
        imported += 1

    if clear_missing and imported_store_ids:
        clear_result = await db.execute(text("""
            UPDATE dm_store_daily dm
            SET sale_amount = 0,
                order_count = 0,
                paid_qty = 0,
                shipped_qty = 0,
                actual_order_count = 0,
                actual_product_qty = 0,
                refund_amount = 0,
                refund_count = 0,
                refund_rate = 0,
                metric_version = :metric_version,
                sale_cogs = 0,
                refund_cogs = 0,
                operating_profit = 0,
                missing_cost_skus = '[]'::jsonb,
                updated_at = NOW()
            FROM biz_stores s
            WHERE dm.store_id = s.id
              AND dm.biz_date = :dt
              AND s.is_active = true
              AND dm.metric_version = :metric_version
              AND NOT (dm.store_id = ANY(:imported_store_ids))
        """), {
            "dt": biz_date,
            "metric_version": JST_METRIC_VERSION,
            "imported_store_ids": imported_store_ids,
        })
        cleared_missing = clear_result.rowcount or 0

    await db.commit()
    return {
        "ok": True,
        "biz_date": str(biz_date),
        "daily_count": imported,
        "cleared_missing": cleared_missing,
        "clear_missing": clear_missing,
    }
