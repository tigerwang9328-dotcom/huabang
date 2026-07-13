from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import re
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_INVENTORY_CODES, ALLOWED_STORE_CODES


CANDIDATE_SCORE = 60
DEFAULT_SIZE_WALL_RULES = {"low_max": 4, "high_min": 21}

CLOTHING_CATEGORIES = (
    "保暖内衣", "内裤", "卫衣", "套装", "尼克服", "棉服", "毛衣", "派克服", "皮衣",
    "短T", "短衬", "羊毛大衣", "羽绒服", "背心", "茄克", "衬衫(停用)", "裘皮外套",
    "裙子", "裤子", "西服", "针织衫", "长T（停用）", "长衬", "长袖T恤", "风衣", "马甲",
)
SIZE_GROUPS = (
    {"code": "numeric_top", "label": "数字上装码", "order": 10},
    {"code": "letter", "label": "字母码", "order": 20},
    {"code": "pants", "label": "裤码", "order": 30},
    {"code": "collar", "label": "领围码", "order": 40},
    {"code": "other", "label": "其他", "order": 50},
)
SIZE_GROUP_ORDER = {row["code"]: row["order"] for row in SIZE_GROUPS}
LETTER_SIZE_ORDER = {
    "XXS": 10, "XS": 20, "XS-1": 21, "S": 30, "M": 40, "L": 50,
    "XL": 60, "2XL": 70, "3XL": 80, "4XL": 90, "5XL": 100,
}


def is_clothing_category(category_name: Optional[str]) -> bool:
    return str(category_name or "").strip() in CLOTHING_CATEGORIES


def is_valid_wall_size(size_code: Optional[str]) -> bool:
    return bool(str(size_code or "").strip()) and str(size_code).strip().upper() != "F"


def normalize_size_code(size_code: Optional[str]) -> str:
    value = str(size_code or "").strip().upper()
    return {"XXL": "2XL", "XXXL": "3XL"}.get(value, value)


def classify_size_group(size_code: Optional[str]) -> str:
    value = normalize_size_code(size_code)
    if re.fullmatch(r"\d{2}Y", value):
        return "numeric_top"
    if value in LETTER_SIZE_ORDER:
        return "letter"
    if re.fullmatch(r"\d{2}[KN]", value):
        return "pants"
    if re.fullmatch(r"\d{2}Z", value):
        return "collar"
    return "other"


def size_sort_value(size_code: Optional[str]) -> int:
    value = normalize_size_code(size_code)
    group = classify_size_group(value)
    if group == "letter":
        return LETTER_SIZE_ORDER.get(value, 999)
    match = re.search(r"\d+", value)
    numeric = int(match.group()) if match else 999
    suffix_order = {"N": 0, "K": 1}.get(value[-1:] if value else "", 0)
    return numeric * 10 + suffix_order


def _num(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class ScoreResult:
    score: int
    structure_score: int
    reasons: list[str]


def is_eligible_year(product_year: Optional[int], current_year: int) -> bool:
    return product_year is not None and current_year - 3 <= int(product_year) <= current_year - 1


def is_candidate_score(score: int) -> bool:
    return score >= CANDIDATE_SCORE


def calculate_candidate_score(
    *,
    year: int,
    current_year: int,
    sales_qty_30d: float,
    remaining_size_count: int,
    listed_size_count: int,
    remaining_color_count: int,
    listed_color_count: int,
) -> ScoreResult:
    reasons: list[str] = []
    year_score = {current_year - 1: 10, current_year - 2: 15, current_year - 3: 20}.get(year, 0)
    if year_score:
        reasons.append(f"{year}年旧款")

    if sales_qty_30d <= 0:
        movement_score = 30
        reasons.append("近30日零动销")
    elif sales_qty_30d <= 1:
        movement_score = 24
        reasons.append("近30日仅售1件")
    elif sales_qty_30d <= 3:
        movement_score = 15
        reasons.append("近30日动销偏慢")
    else:
        movement_score = 0

    size_ratio = remaining_size_count / listed_size_count if listed_size_count else 1
    if remaining_size_count == 1:
        structure_score = 35
        reasons.append("单码")
    elif remaining_size_count == 2:
        structure_score = 25
        reasons.append("双码")
    elif size_ratio <= 0.4:
        structure_score = 20
        reasons.append("尺码覆盖不超过40%")
    else:
        structure_score = 0

    color_ratio = remaining_color_count / listed_color_count if listed_color_count else 1
    if remaining_color_count == 1 or color_ratio <= 0.4:
        color_score = 15
        reasons.append("剩余颜色过少")
    else:
        color_score = 0

    return ScoreResult(year_score + movement_score + structure_score + color_score, structure_score, reasons)


def parse_sale_sku(sku_code: Optional[str]) -> Optional[tuple[str, str, str]]:
    parts = str(sku_code or "").strip().split("|")
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1].lstrip("-"), parts[2]


def classify_size_status(quantity: float, low_max: int = 4, high_min: int = 21) -> str:
    if quantity <= 0:
        return "断货"
    if quantity <= low_max:
        return "偏少"
    if quantity >= high_min:
        return "偏多"
    return "正常"


def price_band(tag_price: float) -> str:
    if tag_price < 300:
        return "300元以下"
    if tag_price < 500:
        return "300-499元"
    if tag_price < 800:
        return "500-799元"
    if tag_price < 1200:
        return "800-1199元"
    return "1200元以上"


def choose_action(
    *, distribution_count: int, local_qty: float, company_qty: float,
    sales_qty_30d: float, tag_price: float, location_type: str = "store",
) -> str:
    if location_type == "store" and distribution_count >= 2 and local_qty <= 2:
        return "集中调拨"
    if sales_qty_30d <= 0 and company_qty >= 10:
        return "集中清仓"
    if tag_price >= 800:
        return "VIP定向推荐"
    if location_type == "store" and local_qty >= 5:
        return "集中陈列"
    return "搭配销售"


class SizeWallService:
    async def build_snapshot(self, db: AsyncSession, analysis_date: Optional[date] = None) -> dict[str, Any]:
        coverage = (await db.execute(text("""
            select min(biz_date) min_date, max(biz_date) max_date
            from dwd.dwd_pos_sale_goods where store_code=any(:store_codes)
        """), {"store_codes": sorted(ALLOWED_STORE_CODES)})).mappings().first()
        max_date = coverage.get("max_date") if coverage else None
        if not max_date:
            raise ValueError("商品销售明细为空，无法生成尺码墙快照")
        dt = analysis_date or max_date
        if dt > max_date:
            raise ValueError(f"分析日期不能晚于最近完整销售日 {max_date}")
        if dt < coverage.get("min_date"):
            raise ValueError(f"分析日期不能早于销售历史起始日 {coverage.get('min_date')}")
        coverage_start = max(coverage.get("min_date"), dt - timedelta(days=29))
        coverage_days = (dt - coverage_start).days + 1
        current_year = dt.year
        rules = await self._rules(db)

        rows = (await db.execute(text(r"""
            with inventory_raw as (
              select upper(i.warehouse_code) store_code,max(i.warehouse_name) store_name,
                     i.product_code,trim(leading '-' from coalesce(i.color_code,'')) color_code,
                     max(i.color_name) color_name,i.size_code,max(i.size_name) size_name,
                     greatest(sum(coalesce(i.qty,0)),0) inventory_qty,
                     greatest(sum(coalesce(i.qty,0)),0)
                       * max(coalesce(nullif(s.cost_price,0),nullif(p.cost_price,0),0)) inventory_amount
              from dwd.v_apparel_inventory_balance i
              left join dim.dim_sku s on s.product_code=i.product_code
               and trim(leading '-' from coalesce(s.color_code,''))=trim(leading '-' from coalesce(i.color_code,''))
               and coalesce(s.size_code,'')=coalesce(i.size_code,'')
              join dim.dim_product p on p.product_code=i.product_code
              where upper(i.warehouse_code)=any(:inventory_codes)
                and upper(trim(coalesce(i.size_code,'')))<>'F' and trim(coalesce(i.size_code,''))<>''
                and coalesce(p.category_name,p.category_l2,p.category_l1,'未分类')=any(:clothing_categories)
              group by upper(i.warehouse_code),i.product_code,trim(leading '-' from coalesce(i.color_code,'')),i.size_code
            ), inventory as (
              select ir.*,
                     case upper(trim(ir.size_code)) when 'XXL' then '2XL' when 'XXXL' then '3XL'
                          else upper(trim(ir.size_code)) end normalized_size_code
              from inventory_raw ir
            ), inventory_classified as (
              select i.*,
                     case when normalized_size_code ~ '^\d{2}Y$' then 'numeric_top'
                          when normalized_size_code ~ '^(XXS|XS|XS-1|S|M|L|XL|[2-5]XL)$' then 'letter'
                          when normalized_size_code ~ '^\d{2}[KN]$' then 'pants'
                          when normalized_size_code ~ '^\d{2}Z$' then 'collar'
                          else 'other' end size_group
              from inventory i
            ), sku_sizes as (
              select s.product_code,trim(leading '-' from coalesce(s.color_code,'')) color_code,
                     case upper(trim(s.size_code)) when 'XXL' then '2XL' when 'XXXL' then '3XL'
                          else upper(trim(s.size_code)) end normalized_size_code
              from dim.dim_sku s join dim.dim_product p on p.product_code=s.product_code
              where trim(coalesce(s.size_code,''))<>'' and upper(trim(s.size_code))<>'F'
                and coalesce(p.category_name,p.category_l2,p.category_l1,'未分类')=any(:clothing_categories)
            ), listed_sizes as (
              select product_code,color_code,count(distinct normalized_size_code) listed_size_count
              from sku_sizes group by 1,2
            ), listed_colors as (
              select product_code,count(distinct color_code) listed_color_count
              from sku_sizes where color_code<>'' group by 1
            ), structure as (
              select product_code,color_code,
                     count(distinct normalized_size_code) filter(where inventory_qty>0) remaining_size_count,
                     sum(inventory_qty) company_all_size_qty
              from inventory_classified group by 1,2
            ), remaining_colors as (
              select product_code,count(*) filter(where company_all_size_qty>0) remaining_color_count
              from structure group by 1
            ), sale_color as (
              select product_code,trim(leading '-' from split_part(sku_code,'|',2)) color_code,
                     sum(sales_qty) sales_qty_30d,sum(sales_amount) sales_amount_30d
              from dwd.dwd_pos_sale_goods
              where biz_date between :coverage_start and :dt and store_code=any(:store_codes)
                and upper(trim(split_part(sku_code,'|',3)))<>'F'
              group by 1,2
            ), sale_local as (
              select store_code,product_code,trim(leading '-' from split_part(sku_code,'|',2)) color_code,
                     split_part(sku_code,'|',3) size_code,
                     sum(sales_qty) sales_qty_30d,sum(sales_amount) sales_amount_30d
              from dwd.dwd_pos_sale_goods
              where biz_date between :coverage_start and :dt and store_code=any(:store_codes)
                and upper(trim(split_part(sku_code,'|',3)))<>'F'
              group by 1,2,3,4
            ), wall_company as (
              select product_code,color_code,sum(inventory_qty) company_wall_qty
              from inventory_classified group by 1,2
            ), distribution as (
              select product_code,color_code,normalized_size_code,count(*) filter(where inventory_qty>0) distribution_count
              from inventory_classified where store_code=any(:store_codes) group by 1,2,3
            )
            select i.*,p.product_name,p.year,coalesce(p.category_name,p.category_l2,p.category_l1,'未分类') category_name,
                   coalesce(nullif(sku.tag_price,0),nullif(p.tag_price,0),nullif(p.market_price,0),0) tag_price,
                   ls.listed_size_count,st.remaining_size_count,lc.listed_color_count,rc.remaining_color_count,
                   coalesce(sc.sales_qty_30d,0) color_sales_qty_30d,
                   coalesce(sl.sales_qty_30d,0) local_sales_qty_30d,coalesce(sl.sales_amount_30d,0) local_sales_amount_30d,
                   coalesce(wc.company_wall_qty,0) company_wall_qty,coalesce(d.distribution_count,0) distribution_count
            from inventory_classified i
            join dim.dim_product p on p.product_code=i.product_code
            left join dim.dim_sku sku on sku.product_code=i.product_code
             and trim(leading '-' from coalesce(sku.color_code,''))=i.color_code and coalesce(sku.size_code,'')=i.size_code
            join listed_sizes ls on ls.product_code=i.product_code and ls.color_code=i.color_code
            join structure st on st.product_code=i.product_code and st.color_code=i.color_code
            join listed_colors lc on lc.product_code=i.product_code
            join remaining_colors rc on rc.product_code=i.product_code
            left join sale_color sc on sc.product_code=i.product_code and sc.color_code=i.color_code
            left join sale_local sl on sl.store_code=i.store_code and sl.product_code=i.product_code
             and sl.color_code=i.color_code and sl.size_code=i.size_code
            left join wall_company wc on wc.product_code=i.product_code and wc.color_code=i.color_code
            left join distribution d on d.product_code=i.product_code and d.color_code=i.color_code
             and d.normalized_size_code=i.normalized_size_code
            where i.inventory_qty>0
              and p.year between :min_year and :max_year
              and (st.remaining_size_count<=2 or st.remaining_size_count::numeric/nullif(ls.listed_size_count,0)<=0.4)
        """), {
            "dt": dt, "coverage_start": coverage_start,
            "store_codes": sorted(ALLOWED_STORE_CODES), "inventory_codes": sorted(ALLOWED_INVENTORY_CODES),
            "clothing_categories": list(CLOTHING_CATEGORIES),
            "min_year": current_year - 3, "max_year": current_year - 1,
        })).mappings().all()

        candidates: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            score = calculate_candidate_score(
                year=int(row["year"]), current_year=current_year,
                sales_qty_30d=_num(row["color_sales_qty_30d"]),
                remaining_size_count=int(row["remaining_size_count"]), listed_size_count=int(row["listed_size_count"]),
                remaining_color_count=int(row["remaining_color_count"]), listed_color_count=int(row["listed_color_count"]),
            )
            if score.structure_score <= 0 or not is_candidate_score(score.score):
                continue
            location_type = "store" if row["store_code"] in ALLOWED_STORE_CODES else "warehouse"
            row.update({
                "analysis_date": dt, "score": score.score,
                "size_sort": size_sort_value(row["normalized_size_code"]),
                "score_reasons": json.dumps(score.reasons, ensure_ascii=False),
                "price_band": price_band(_num(row["tag_price"])),
                "size_status": classify_size_status(
                    _num(row["inventory_qty"]), low_max=rules["low_max"], high_min=rules["high_min"],
                ),
                "suggested_action": choose_action(
                    distribution_count=int(row["distribution_count"]), local_qty=_num(row["inventory_qty"]),
                    company_qty=_num(row["company_wall_qty"]), sales_qty_30d=_num(row["color_sales_qty_30d"]),
                    tag_price=_num(row["tag_price"]), location_type=location_type,
                ),
                "location_type": location_type,
                "sales_coverage_start": coverage_start, "sales_coverage_end": dt, "sales_coverage_days": coverage_days,
            })
            candidates.append(row)

        await db.execute(text("delete from dm.dm_size_wall_candidate_daily where analysis_date=:dt"), {"dt": dt})
        if candidates:
            await db.execute(text("""
                insert into dm.dm_size_wall_candidate_daily(
                  analysis_date,store_code,store_name,location_type,product_code,product_name,color_code,color_name,
                  size_code,size_name,normalized_size_code,size_group,size_sort,
                  product_year,category_name,tag_price,price_band,inventory_qty,inventory_amount,
                  sales_qty_30d,sales_amount_30d,listed_size_count,remaining_size_count,listed_color_count,
                  remaining_color_count,distribution_count,company_wall_qty,score,score_reasons,suggested_action,
                  size_status,sales_coverage_start,sales_coverage_end,sales_coverage_days,generated_at)
                values(
                  :analysis_date,:store_code,:store_name,:location_type,:product_code,:product_name,:color_code,:color_name,
                  :size_code,:size_name,:normalized_size_code,:size_group,:size_sort,
                  :year,:category_name,:tag_price,:price_band,:inventory_qty,:inventory_amount,
                  :local_sales_qty_30d,:local_sales_amount_30d,:listed_size_count,:remaining_size_count,:listed_color_count,
                  :remaining_color_count,:distribution_count,:company_wall_qty,:score,cast(:score_reasons as jsonb),:suggested_action,
                  :size_status,:sales_coverage_start,:sales_coverage_end,:sales_coverage_days,now())
            """), candidates)
        return {
            "analysis_date": str(dt), "candidate_rows": len(candidates),
            "candidate_style_colors": len({(r["product_code"], r["color_code"]) for r in candidates}),
            "candidate_qty": round(sum(_num(r["inventory_qty"]) for r in candidates), 2),
            "sales_coverage_start": str(coverage_start), "sales_coverage_end": str(dt), "sales_coverage_days": coverage_days,
        }

    async def _analysis_date(self, db: AsyncSession, value: Optional[date]) -> Optional[date]:
        if value:
            return value
        return (await db.execute(text("select max(analysis_date) from dm.dm_size_wall_candidate_daily"))).scalar()

    async def _rules(self, db: AsyncSession) -> dict[str, int]:
        raw = (await db.execute(text("select param_value from sys.sys_param where param_key='size_wall_rules'"))).scalar()
        try:
            parsed = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        except (TypeError, ValueError):
            parsed = {}
        low_max = int(parsed.get("low_max", DEFAULT_SIZE_WALL_RULES["low_max"]))
        high_min = int(parsed.get("high_min", DEFAULT_SIZE_WALL_RULES["high_min"]))
        if low_max < 0 or high_min <= low_max:
            return dict(DEFAULT_SIZE_WALL_RULES)
        return {"low_max": low_max, "high_min": high_min}

    @staticmethod
    def _codes(allowed_codes: list[str], store_code: Optional[str]) -> list[str]:
        codes = sorted(set(allowed_codes) & set(ALLOWED_INVENTORY_CODES))
        if store_code:
            normalized = store_code.upper()
            if normalized not in codes:
                raise PermissionError("无权查看该门店或仓库")
            return [normalized]
        return codes

    async def overview(self, db: AsyncSession, allowed_codes: list[str], store_code: Optional[str] = None,
                       analysis_date: Optional[date] = None) -> dict[str, Any]:
        dt = await self._analysis_date(db, analysis_date)
        if not dt:
            return {"analysis_date": None, "size_summary": [], "store_matrix": [], "location_options": [], "warnings": ["尺码墙快照尚未生成"]}
        codes = self._codes(allowed_codes, store_code)
        rules = await self._rules(db)
        params = {"dt": dt, "codes": codes}
        size_rows = (await db.execute(text("""
            select normalized_size_code size_code,size_group,min(size_sort) size_sort,
                   sum(inventory_qty) qty,count(distinct (product_code,color_code)) style_colors,
                   sum(inventory_amount) inventory_amount,sum(sales_qty_30d) sales_qty_30d
            from dm.dm_size_wall_candidate_daily
            where analysis_date=:dt and store_code=any(:codes)
            group by normalized_size_code,size_group
            order by case size_group when 'numeric_top' then 10 when 'letter' then 20
                     when 'pants' then 30 when 'collar' then 40 else 50 end,
                     min(size_sort),normalized_size_code
        """), params)).mappings().all()
        size_summary = []
        for raw in size_rows:
            row = dict(raw)
            row["status"] = classify_size_status(
                _num(row["qty"]), low_max=rules["low_max"], high_min=rules["high_min"],
            )
            row["display_size"] = row["size_code"].removesuffix("Y")
            size_summary.append(row)

        matrix_codes = [c for c in codes if c in ALLOWED_STORE_CODES] or codes
        matrix = (await db.execute(text("""
            with locations as (select unnest(cast(:matrix_codes as varchar[])) store_code),
            sizes as (
              select normalized_size_code size_code,size_group,min(size_sort) size_sort
              from dm.dm_size_wall_candidate_daily where analysis_date=:dt and store_code=any(:matrix_codes)
              group by normalized_size_code,size_group
            ), agg as (
              select store_code,normalized_size_code size_code,sum(inventory_qty) qty,
                     count(distinct (product_code,color_code)) style_colors
              from dm.dm_size_wall_candidate_daily where analysis_date=:dt and store_code=any(:matrix_codes)
              group by store_code,normalized_size_code
            )
            select l.store_code,coalesce(ds.store_name,l.store_code) store_name,s.size_code,s.size_group,s.size_sort,
                   coalesce(a.qty,0) qty,coalesce(a.style_colors,0) style_colors
            from locations l cross join sizes s left join agg a using(store_code,size_code)
            left join (
              select store_code,max(store_name) store_name from dim.dim_store group by store_code
            ) ds on ds.store_code=l.store_code
            order by l.store_code,case s.size_group when 'numeric_top' then 10 when 'letter' then 20
                     when 'pants' then 30 when 'collar' then 40 else 50 end,s.size_sort,s.size_code
        """), {**params, "matrix_codes": matrix_codes})).mappings().all()
        matrix_map: dict[str, dict[str, Any]] = {}
        for raw in matrix:
            row = dict(raw)
            item = matrix_map.setdefault(row["store_code"], {"store_code": row["store_code"], "store_name": row["store_name"], "sizes": {}})
            item["sizes"][row["size_code"]] = {
                "qty": _num(row["qty"]), "style_colors": int(row["style_colors"]),
                "status": classify_size_status(
                    _num(row["qty"]), low_max=rules["low_max"], high_min=rules["high_min"],
                ),
            }

        location_options = (await db.execute(text("""
            select store_code,max(coalesce(store_name,store_code)) store_name,max(location_type) location_type
            from dm.dm_size_wall_candidate_daily
            where analysis_date=:dt and store_code=any(:codes)
            group by store_code order by store_code
        """), params)).mappings().all()

        distributions = (await db.execute(text("""
            select 'category' dimension,category_name name,sum(inventory_qty) qty,sum(inventory_amount) amount,sum(sales_qty_30d) sales_qty
            from dm.dm_size_wall_candidate_daily where analysis_date=:dt and store_code=any(:codes) group by category_name
            union all
            select 'price',price_band,sum(inventory_qty),sum(inventory_amount),sum(sales_qty_30d)
            from dm.dm_size_wall_candidate_daily where analysis_date=:dt and store_code=any(:codes) group by price_band
            order by dimension,qty desc
        """), params)).mappings().all()
        meta = (await db.execute(text("""
            select min(sales_coverage_start) coverage_start,max(sales_coverage_end) coverage_end,
                   max(sales_coverage_days) coverage_days,max(generated_at) generated_at,
                   count(*) candidate_rows,count(distinct (product_code,color_code)) candidate_style_colors,
                   sum(inventory_qty) candidate_qty,sum(inventory_amount) candidate_amount,
                   sum(sales_qty_30d) baseline_sales_qty,sum(sales_amount_30d) baseline_sales_amount
            from dm.dm_size_wall_candidate_daily where analysis_date=:dt and store_code=any(:codes)
        """), params)).mappings().first()
        warnings = []
        if int((meta or {}).get("coverage_days") or 0) < 30:
            warnings.append(f"当前销售历史仅覆盖 {int((meta or {}).get('coverage_days') or 0)} 天，动销判断按实际覆盖期计算。")
        if not meta or not meta.get("candidate_rows"):
            warnings.append("当前筛选范围没有达到60分的尺码墙候选库存。")
        high = max(size_summary, key=lambda x: _num(x["qty"]), default=None)
        low = min(size_summary, key=lambda x: _num(x["qty"]), default=None)
        insights = []
        if high:
            insights.append(f"{high['display_size']}码候选库存最多，共 {_num(high['qty']):.0f} 件，建议优先按品类和价格段分区陈列。")
        if low and _num(low["qty"]) <= rules["low_max"]:
            insights.append(f"{low['display_size']}码候选库存{low['status']}，陈列时避免预留过大区域。")
        category_rows = [dict(x) for x in distributions if x["dimension"] == "category"]
        price_rows = [dict(x) for x in distributions if x["dimension"] == "price"]
        if category_rows and price_rows:
            insights.append(f"候选主要集中在{category_rows[0]['name']}、{price_rows[0]['name']}，建议在对应尺码区内优先成组陈列。")
        return {
            "analysis_date": str(dt), "data_coverage": dict(meta or {}), "size_summary": size_summary,
            "store_matrix": list(matrix_map.values()), "location_options": [dict(x) for x in location_options],
            "size_groups": [
                {**group, "sizes": [row["size_code"] for row in size_summary if row["size_group"] == group["code"]]}
                for group in SIZE_GROUPS if any(row["size_group"] == group["code"] for row in size_summary)
            ],
            "eligible_years": list(range(dt.year - 3, dt.year)), "status_rules": rules,
            "category_distribution": category_rows, "price_distribution": price_rows,
            "warnings": warnings, "insights": insights,
            "display_advice": ["先按数字上装码、字母码、裤码和领围码分区，再在组内按具体尺码排列。", "每个尺码区优先陈列高分候选，单码款使用醒目标识避免顾客继续寻找其他尺码。"],
            "sales_scripts": ["先确认顾客常穿尺码，直接带到对应尺码区，再从品类和预算中缩小选择。", "这一区都是您能穿的尺码，可以先挑版型和颜色，不需要逐款询问有没有码。"],
        }

    async def candidates(self, db: AsyncSession, allowed_codes: list[str], *, store_code: Optional[str] = None,
                         analysis_date: Optional[date] = None, year: Optional[int] = None,
                         size_group: Optional[str] = None, normalized_size_code: Optional[str] = None,
                         raw_size_code: Optional[str] = None, size_code: Optional[str] = None,
                         category_name: Optional[str] = None,
                         price_band_value: Optional[str] = None, min_score: Optional[int] = None,
                         suggested_action: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        dt = await self._analysis_date(db, analysis_date)
        if not dt:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        codes = self._codes(allowed_codes, store_code)
        conditions = ["analysis_date=:dt", "store_code=any(:codes)"]
        params: dict[str, Any] = {"dt": dt, "codes": codes, "offset": (page - 1) * page_size, "limit": page_size}
        for value, sql, key in [
            (year, "product_year=:year", "year"), (size_group, "size_group=:size_group", "size_group"),
            (normalized_size_code or size_code, "normalized_size_code=:normalized_size_code", "normalized_size_code"),
            (raw_size_code, "size_code=:raw_size_code", "raw_size_code"),
            (category_name, "category_name=:category_name", "category_name"),
            (price_band_value, "price_band=:price_band", "price_band"),
            (min_score, "score>=:min_score", "min_score"),
            (suggested_action, "suggested_action=:suggested_action", "suggested_action"),
        ]:
            if value not in (None, ""):
                conditions.append(sql)
                params[key] = value
        where = " and ".join(conditions)
        total = (await db.execute(text(f"select count(*) from dm.dm_size_wall_candidate_daily where {where}"), params)).scalar() or 0
        rows = (await db.execute(text(f"""
            select analysis_date,store_code,store_name,location_type,product_code,product_name,color_code,color_name,
                   size_code,size_code raw_size_code,size_name,normalized_size_code,size_group,size_sort,
                   product_year,category_name,tag_price,price_band,inventory_qty,inventory_amount,
                   sales_qty_30d,sales_amount_30d,listed_size_count,remaining_size_count,listed_color_count,
                   remaining_color_count,distribution_count,company_wall_qty,score,score_reasons,suggested_action,
                   size_status,sales_coverage_days
            from dm.dm_size_wall_candidate_daily where {where}
            order by score desc,inventory_amount desc,size_group,size_sort,product_code,color_code,size_code,store_code
            offset :offset limit :limit
        """), params)).mappings().all()
        return {"items": [dict(x) for x in rows], "total": int(total), "page": page, "page_size": page_size, "analysis_date": str(dt)}
