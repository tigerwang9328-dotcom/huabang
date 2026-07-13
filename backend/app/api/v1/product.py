"""商品经营中心 - 标准商品维(dim.dim_product)查询 + 百胜商品主档同步。

读取标准业务表 dim_product（不返回 raw_data / 成本价 / 任何密钥）。
"""
import logging
from datetime import date
from typing import Optional
from urllib.parse import quote, unquote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.data_scope import get_data_scope
from app.core.database import get_db
import asyncio as _asyncio

from app.core.database import AsyncSessionLocal
from app.core.store_whitelist import ALLOWED_INVENTORY_CODES, ALLOWED_STORE_CODES, allowed_inventory_sql_in
from app.integrations.baison.services.product_image_service import ensure_product_image_table, sku_color_image_urls
from app.integrations.baison.services.product_service import GOODS_LIST_METHOD, import_all_goods, import_goods_page
from app.integrations.baison.services.sku_service import SKU_LIST_METHOD, import_all_skus, import_sku_page
from app.models.dim import DimProduct, DimSku
from app.models.sys import SysUser
from app.services.size_wall_service import SizeWallService

logger = logging.getLogger("product.api")

router = APIRouter(tags=["商品经营中心"])


async def _size_wall_codes(db: AsyncSession, current_user: SysUser, store_code: Optional[str]) -> list[str]:
    scope = await get_data_scope(db, current_user)
    source_codes = scope.inventory_codes if scope.is_limited_store else ALLOWED_INVENTORY_CODES
    codes = sorted({str(code).upper() for code in source_codes} & set(ALLOWED_INVENTORY_CODES))
    if store_code and store_code.upper() not in codes:
        raise HTTPException(status_code=403, detail="无权查看该门店或仓库")
    return codes

# 列表返回字段（不含 raw_data / cost_price）
_COLS = (
    DimProduct.id, DimProduct.product_code, DimProduct.product_name,
    DimProduct.category_code, DimProduct.category_name, DimProduct.brand_name,
    DimProduct.top_category_name, DimProduct.year, DimProduct.season,
    DimProduct.tag_price, DimProduct.market_price, DimProduct.supplier_name,
    DimProduct.has_cost, DimProduct.status, DimProduct.source_system, DimProduct.synced_at,
)


def _num(v) -> float:
    return float(v or 0)


def _fmt_qty(v) -> int | float:
    n = _num(v)
    return int(n) if n.is_integer() else round(n, 2)


def _product_suggestion(row: dict) -> str:
    sales_qty = _num(row.get("sales_qty"))
    inventory_qty = _num(row.get("inventory_qty"))
    has_cost = bool(row.get("has_cost"))
    if not has_cost:
        return "补成本"
    if sales_qty > 0 and inventory_qty <= 0:
        return "关注补货"
    if sales_qty <= 0 and inventory_qty > 0:
        return "关注动销"
    if sales_qty >= 10:
        return "持续跟进"
    return "正常"


def _lifecycle_stage(row: dict) -> str:
    sales_qty = _num(row.get("sales_qty"))
    inventory_qty = _num(row.get("inventory_qty"))
    if sales_qty > 0:
        return "动销"
    if inventory_qty > 0:
        return "待动销"
    return "无库存"


def _sku_suggestion(row: dict) -> str:
    if not row.get("barcode"):
        return "补条码"
    if not row.get("has_cost"):
        return "补成本"
    if _num(row.get("sales_qty")) > 0 and _num(row.get("inventory_qty")) <= 0:
        return "关注补货"
    if _num(row.get("sales_qty")) <= 0 and _num(row.get("inventory_qty")) > 0:
        return "关注动销"
    return "正常"


def _sort_items(items: list[dict], sort_by: Optional[str], sort_order: Optional[str]) -> list[dict]:
    if sort_by not in {"inventory_qty", "sales_qty", "sales_amount"}:
        return items
    reverse = (sort_order or "desc").lower() != "asc"
    return sorted(items, key=lambda x: _num(x.get(sort_by)), reverse=reverse)


def _image_proxy_path(source_url: Optional[str]) -> Optional[str]:
    if not source_url:
        return None
    return f"/api/v1/product/image-proxy?url={quote(source_url, safe='')}"


async def _latest_sales_window(db: AsyncSession):
    row = (await db.execute(text("""
        SELECT MAX(biz_date) AS end_date, MAX(biz_date) - INTERVAL '6 days' AS start_date
        FROM dwd.dwd_pos_sale_goods
    """))).mappings().first()
    if not row or not row["end_date"]:
        return None, None
    return row["start_date"], row["end_date"]


async def _product_metrics(db: AsyncSession, product_codes: list[str]) -> dict[str, dict]:
    if not product_codes:
        return {}
    start_date, end_date = await _latest_sales_window(db)
    metrics = {code: {"inventory_qty": 0.0, "sales_qty": 0.0, "sales_amount": 0.0} for code in product_codes}
    inv_rows = (await db.execute(text("""
        SELECT product_code, COALESCE(SUM(qty), 0) AS inventory_qty
        FROM dwd.v_apparel_inventory_balance
        WHERE product_code = ANY(:codes)
          AND UPPER(warehouse_code::text) = ANY(:inventory_codes)
        GROUP BY product_code
    """), {"codes": product_codes, "inventory_codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().all()
    for row in inv_rows:
        metrics[row["product_code"]]["inventory_qty"] = _num(row["inventory_qty"])
    if start_date and end_date:
        sales_rows = (await db.execute(text("""
            SELECT product_code,
                   COALESCE(SUM(sales_qty), 0) AS sales_qty,
                   COALESCE(SUM(sales_amount), 0) AS sales_amount
            FROM dwd.dwd_pos_sale_goods
            WHERE product_code = ANY(:codes)
              AND store_code = ANY(:store_codes)
              AND biz_date >= :start_date
              AND biz_date <= :end_date
            GROUP BY product_code
        """), {
            "codes": product_codes,
            "store_codes": sorted(ALLOWED_STORE_CODES),
            "start_date": start_date,
            "end_date": end_date,
        })).mappings().all()
        for row in sales_rows:
            metrics[row["product_code"]]["sales_qty"] = _num(row["sales_qty"])
            metrics[row["product_code"]]["sales_amount"] = _num(row["sales_amount"])
    return metrics


async def _sku_metrics(db: AsyncSession, sku_rows: list[dict]) -> dict[str, dict]:
    sku_codes = [r["sku_code"] for r in sku_rows if r.get("sku_code")]
    if not sku_codes:
        return {}
    start_date, end_date = await _latest_sales_window(db)
    metrics = {code: {"inventory_qty": 0.0, "sales_qty": 0.0, "sales_amount": 0.0} for code in sku_codes}
    product_codes = sorted({r["product_code"] for r in sku_rows if r.get("product_code")})
    inv_rows = (await db.execute(text("""
        SELECT product_code,
               COALESCE(BTRIM(color_code::text), '') AS color_code,
               COALESCE(BTRIM(size_code::text), '') AS size_code,
               COALESCE(SUM(qty), 0) AS inventory_qty
        FROM dwd.v_apparel_inventory_balance
        WHERE product_code = ANY(:product_codes)
          AND UPPER(warehouse_code::text) = ANY(:inventory_codes)
        GROUP BY product_code, COALESCE(BTRIM(color_code::text), ''), COALESCE(BTRIM(size_code::text), '')
    """), {"product_codes": product_codes, "inventory_codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().all()
    inventory_by_spec = {
        (row["product_code"], row["color_code"], row["size_code"]): _num(row["inventory_qty"])
        for row in inv_rows
    }
    for row in sku_rows:
        sku_code = row.get("sku_code")
        if sku_code not in metrics:
            continue
        key = (
            row.get("product_code"),
            str(row.get("color_code") or "").strip(),
            str(row.get("size_code") or "").strip(),
        )
        metrics[sku_code]["inventory_qty"] = inventory_by_spec.get(key, 0.0)
    if start_date and end_date:
        sales_rows = (await db.execute(text("""
            SELECT product_code,
                   COALESCE(BTRIM(split_part(sku_code::text, '|', 2)), '') AS color_code,
                   COALESCE(BTRIM(split_part(sku_code::text, '|', 3)), '') AS size_code,
                   COALESCE(SUM(sales_qty), 0) AS sales_qty,
                   COALESCE(SUM(sales_amount), 0) AS sales_amount
            FROM dwd.dwd_pos_sale_goods
            WHERE product_code = ANY(:product_codes)
              AND store_code = ANY(:store_codes)
              AND biz_date >= :start_date
              AND biz_date <= :end_date
            GROUP BY product_code,
                     COALESCE(BTRIM(split_part(sku_code::text, '|', 2)), ''),
                     COALESCE(BTRIM(split_part(sku_code::text, '|', 3)), '')
        """), {
            "product_codes": product_codes,
            "store_codes": sorted(ALLOWED_STORE_CODES),
            "start_date": start_date,
            "end_date": end_date,
        })).mappings().all()
        sales_by_spec = {
            (row["product_code"], row["color_code"], row["size_code"]): row
            for row in sales_rows
        }
        for row in sku_rows:
            sku_code = row.get("sku_code")
            if sku_code not in metrics:
                continue
            key = (
                row.get("product_code"),
                str(row.get("color_code") or "").strip(),
                str(row.get("size_code") or "").strip(),
            )
            sale = sales_by_spec.get(key)
            if sale:
                metrics[sku_code]["sales_qty"] = _num(sale["sales_qty"])
                metrics[sku_code]["sales_amount"] = _num(sale["sales_amount"])
    return metrics


class ProductSyncRequest(BaseModel):
    full_sync: bool = True
    page_size: int = 20
    startModified: Optional[str] = "2026-01-01 00:00:00"
    endModified: Optional[str] = "2026-12-31 23:59:59"
    opt_user_code: str = "000"


@router.get("/product/list")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    brand_name: Optional[str] = None,
    category_name: Optional[str] = None,
    season: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    source_system: Optional[str] = None,
    only_positive: Optional[int] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("product:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """标准商品维分页查询（商品主档）。"""
    try:
        conds = []
        if keyword:
            kw = f"%{keyword.strip()}%"
            conds.append(or_(DimProduct.product_code.ilike(kw), DimProduct.product_name.ilike(kw)))
        if brand_name:
            conds.append(DimProduct.brand_name == brand_name)
        if category_name:
            conds.append(DimProduct.category_name == category_name)
        if season:
            conds.append(DimProduct.season == season)
        if year is not None:
            conds.append(DimProduct.year == year)
        if status:
            conds.append(DimProduct.status == status)
        if source_system:
            conds.append(DimProduct.source_system == source_system)
        if only_positive:
            inventory_in = allowed_inventory_sql_in()
            conds.append(text(f"""
                dim_product.product_code IN (
                    SELECT i.product_code
                    FROM dwd.v_apparel_inventory_balance i
                    WHERE UPPER(COALESCE(i.warehouse_code, '')::text) IN {inventory_in}
                    GROUP BY i.product_code
                    HAVING COALESCE(SUM(i.qty), 0) > 0
                )
            """))

        total = (await db.execute(select(func.count()).select_from(DimProduct).where(*conds))).scalar() or 0
        query = select(*_COLS).where(*conds).order_by(DimProduct.product_code)
        if sort_by not in {"inventory_qty", "sales_qty", "sales_amount"}:
            query = query.offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(query)).mappings().all()
        product_codes = [r["product_code"] for r in rows if r["product_code"]]
        metrics = await _product_metrics(db, product_codes)
        items = []
        for r in rows:
            item = dict(r)
            item.update(metrics.get(item.get("product_code"), {}))
            item["sales_qty"] = _fmt_qty(item.get("sales_qty"))
            item["sales_amount"] = round(_num(item.get("sales_amount")), 2)
            item["inventory_qty"] = _fmt_qty(item.get("inventory_qty"))
            item["lifecycle_stage"] = _lifecycle_stage(item)
            item["ai_suggestion"] = _product_suggestion(item)
            items.append(item)
        if sort_by in {"inventory_qty", "sales_qty", "sales_amount"}:
            items = _sort_items(items, sort_by, sort_order)
            items = items[(page - 1) * page_size: page * page_size]
        return {"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("product list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.post("/sync/baison/products")
async def sync_baison_products(
    req: ProductSyncRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """同步百胜商品主档（prm.goods.list_get）。full_sync=True 走全量分页。"""
    try:
        if req.full_sync:
            r = await import_all_goods(db, req.page_size, req.startModified, req.endModified, req.opt_user_code)
        else:
            r = await import_goods_page(db, 1, req.page_size, req.startModified, req.endModified, req.opt_user_code)
        if not r.get("ok"):
            return {"success": False, "message": "同步失败", "error": r.get("error"), "data": r}
        return {
            "success": True, "message": "同步完成",
            "data": {
                "method": GOODS_LIST_METHOD,
                "page_total": r.get("page_total"),
                "total_result": r.get("total_result"),
                "ods_inserted": r.get("ods_inserted", 0),
                "ods_updated": r.get("ods_updated", 0),
                "dim_inserted": r.get("dim_inserted", 0),
                "dim_updated": r.get("dim_updated", 0),
                "skipped": r.get("skipped", 0),
                "batch_no": r.get("batch_no"),
            },
        }
    except Exception:
        logger.exception("product sync error")
        return {"success": False, "message": "内部错误，请查看服务日志"}


# SKU 列表返回字段（不含 raw_data / 成本价 / ckj / cbj）
_SKU_COLS = (
    DimSku.id, DimSku.sku_code, DimSku.product_code, DimSku.product_name,
    DimSku.barcode, DimSku.color_code, DimSku.color_name, DimSku.size_code, DimSku.size_name,
    DimSku.brand_name, DimSku.season_name, DimSku.tag_price, DimSku.market_price,
    DimSku.has_cost, DimSku.status, DimSku.source_system, DimSku.synced_at,
)


class SkuSyncRequest(BaseModel):
    full_sync: bool = True
    page_size: int = 20


@router.get("/product/sku-list")
async def list_skus(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    product_code: Optional[str] = None,
    brand_name: Optional[str] = None,
    color_name: Optional[str] = None,
    size_name: Optional[str] = None,
    season_name: Optional[str] = None,
    status: Optional[str] = None,
    source_system: Optional[str] = None,
    only_positive: Optional[int] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    current_user: SysUser = Depends(require_permission("product:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """标准 SKU 维分页查询（SKU档案）。不返回 raw_data / 成本价。"""
    try:
        await ensure_product_image_table(db)
        conds = []
        if keyword:
            kw = f"%{keyword.strip()}%"
            conds.append(or_(DimSku.sku_code.ilike(kw), DimSku.barcode.ilike(kw),
                             DimSku.product_code.ilike(kw), DimSku.product_name.ilike(kw)))
        if product_code:
            conds.append(DimSku.product_code == product_code.strip())
        if brand_name:
            conds.append(DimSku.brand_name == brand_name)
        if color_name:
            conds.append(DimSku.color_name == color_name)
        if size_name:
            conds.append(DimSku.size_name == size_name)
        if season_name:
            conds.append(DimSku.season_name == season_name)
        if status:
            conds.append(DimSku.status == status)
        if source_system:
            conds.append(DimSku.source_system == source_system)
        if only_positive:
            inventory_in = allowed_inventory_sql_in()
            conds.append(text(f"""
                COALESCE((
                    SELECT SUM(i.qty)
                    FROM dwd.v_apparel_inventory_balance i
                    WHERE UPPER(COALESCE(i.warehouse_code, '')::text) IN {inventory_in}
                      AND i.product_code = dim_sku.product_code
                      AND COALESCE(BTRIM(i.color_code::text), '') = COALESCE(BTRIM(dim_sku.color_code::text), '')
                      AND COALESCE(BTRIM(i.size_code::text), '') = COALESCE(BTRIM(dim_sku.size_code::text), '')
                ), 0) > 0
            """))

        total = (await db.execute(select(func.count()).select_from(DimSku).where(*conds))).scalar() or 0
        query = select(*_SKU_COLS).where(*conds).order_by(
                text("""
                    COALESCE((
                        SELECT CASE WHEN pi.image_url IS NOT NULL THEN 0 ELSE 1 END
                        FROM dim.dim_product_image pi
                        WHERE pi.source_system = 'baison'
                          AND pi.product_code = dim_sku.product_code
                          AND pi.color_code = COALESCE(BTRIM(dim_sku.color_code::text), '')
                        LIMIT 1
                    ), 1)
                """),
                DimSku.sku_code,
            )
        if sort_by not in {"inventory_qty", "sales_qty", "sales_amount"}:
            query = query.offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(query)).mappings().all()
        row_dicts = [dict(r) for r in rows]
        metrics = await _sku_metrics(db, row_dicts)
        items = []
        for r in rows:
            item = dict(r)
            item.update(metrics.get(item.get("sku_code"), {}))
            item["sales_qty"] = _fmt_qty(item.get("sales_qty"))
            item["sales_amount"] = round(_num(item.get("sales_amount")), 2)
            item["inventory_qty"] = _fmt_qty(item.get("inventory_qty"))
            item["ai_suggestion"] = _sku_suggestion(item)
            items.append(item)
        if sort_by in {"inventory_qty", "sales_qty", "sales_amount"}:
            items = _sort_items(items, sort_by, sort_order)
            items = items[(page - 1) * page_size: page * page_size]
        image_urls = await sku_color_image_urls(db, items)
        for item in items:
            source_image_url = image_urls.get((str(item.get("product_code") or "").strip(), str(item.get("color_code") or "").strip()))
            item["image_url"] = _image_proxy_path(source_image_url)
        return {"success": True, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
    except Exception:
        logger.exception("sku list error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


@router.get("/product/image-proxy")
async def product_image_proxy(url: str = Query(..., min_length=8)):
    """同域代理百胜商品图片，避免 HTTPS 页面加载 HTTP 图片被浏览器拦截。"""
    source_url = unquote(url)
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host.endswith("gybssoft.com"):
        raise HTTPException(status_code=400, detail="不允许的图片地址")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(source_url)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="图片读取失败")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail="图片不存在")
    media_type = resp.headers.get("content-type") or "image/jpeg"
    return Response(
        content=resp.content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/product/quality-summary")
async def product_quality_summary(
    current_user: SysUser = Depends(require_permission("product:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    """商品/SKU 数据质量与经营接入概览。"""
    try:
        row = (await db.execute(text("""
            WITH inv_spec AS (
                SELECT product_code,
                       COALESCE(BTRIM(color_code::text), '') AS color_code,
                       COALESCE(BTRIM(size_code::text), '') AS size_code,
                       SUM(qty) AS qty
                FROM dwd.v_apparel_inventory_balance
                WHERE UPPER(warehouse_code::text) = ANY(:inventory_codes)
                GROUP BY product_code, COALESCE(BTRIM(color_code::text), ''), COALESCE(BTRIM(size_code::text), '')
            ), inv AS (
                SELECT COUNT(DISTINCT product_code) FILTER (WHERE qty <> 0) AS inv_product_count
                FROM inv_spec
            ), inv_sku AS (
                SELECT COUNT(DISTINCT s.sku_code) AS inv_sku_count
                FROM dim.dim_sku s
                JOIN inv_spec i
                  ON i.product_code = s.product_code
                 AND i.color_code = COALESCE(BTRIM(s.color_code::text), '')
                 AND i.size_code = COALESCE(BTRIM(s.size_code::text), '')
                WHERE s.source_system = 'baison'
                  AND i.qty <> 0
            ), inv_amount AS (
                SELECT COALESCE(SUM(i.qty * s.cost_price), 0) AS inventory_amount
                FROM inv_spec i
                JOIN dim.dim_sku s
                  ON s.source_system = 'baison'
                 AND s.product_code = i.product_code
                 AND COALESCE(BTRIM(s.color_code::text), '') = i.color_code
                 AND COALESCE(BTRIM(s.size_code::text), '') = i.size_code
                WHERE i.qty <> 0
                  AND s.cost_price IS NOT NULL
                  AND s.cost_price > 0
            ), sale AS (
                SELECT COUNT(DISTINCT product_code) AS sale_product_count,
                       COUNT(DISTINCT sku_code) FILTER (WHERE sku_code IS NOT NULL AND BTRIM(sku_code::text) <> '') AS sale_sku_count
                FROM dwd.dwd_pos_sale_goods
                WHERE store_code = ANY(:store_codes)
                  AND biz_date >= (SELECT MAX(biz_date) - INTERVAL '6 days' FROM dwd.dwd_pos_sale_goods)
                  AND biz_date <= (SELECT MAX(biz_date) FROM dwd.dwd_pos_sale_goods)
            )
            SELECT
                (SELECT COUNT(*) FROM dim.dim_product WHERE source_system='baison') AS product_count,
                (SELECT COUNT(*) FROM dim.dim_sku WHERE source_system='baison') AS sku_count,
                (SELECT COUNT(*) FROM dim.dim_product WHERE source_system='baison' AND (cost_price IS NULL OR cost_price <= 0)) AS product_missing_cost_count,
                (SELECT COUNT(*) FROM dim.dim_sku WHERE source_system='baison' AND (cost_price IS NULL OR cost_price <= 0)) AS sku_missing_cost_count,
                (SELECT COUNT(*) FROM dim.dim_sku WHERE source_system='baison' AND (barcode IS NULL OR BTRIM(barcode::text)='')) AS sku_missing_barcode_count,
                (SELECT COUNT(*) FROM dim.dim_sku WHERE source_system='baison' AND (
                    sku_code IS NULL OR BTRIM(sku_code::text) = ''
                    OR product_code IS NULL OR BTRIM(product_code::text) = ''
                    OR color_name IS NULL OR BTRIM(color_name::text) = ''
                    OR size_name IS NULL OR BTRIM(size_name::text) = ''
                )) AS abnormal_sku_count,
                inv.inv_product_count, inv_sku.inv_sku_count, inv_amount.inventory_amount,
                sale.sale_product_count, sale.sale_sku_count
            FROM inv CROSS JOIN inv_sku CROSS JOIN inv_amount CROSS JOIN sale
        """), {
            "inventory_codes": sorted(ALLOWED_INVENTORY_CODES),
            "store_codes": sorted(ALLOWED_STORE_CODES),
        })).mappings().first()
        data = dict(row or {})
        product_count = _num(data.get("product_count"))
        sku_count = _num(data.get("sku_count"))
        data["product_cost_ready_count"] = int(product_count - _num(data.get("product_missing_cost_count")))
        data["sku_cost_ready_count"] = int(sku_count - _num(data.get("sku_missing_cost_count")))
        data["sku_barcode_ready_count"] = int(sku_count - _num(data.get("sku_missing_barcode_count")))
        data["sku_barcode_rate"] = round(data["sku_barcode_ready_count"] / sku_count * 100, 1) if sku_count else 0
        return {"success": True, "data": data}
    except Exception:
        logger.exception("product quality summary error")
        return {"success": False, "message": "查询失败，请查看服务日志"}


async def _bg_full_sku_sync():
    async with AsyncSessionLocal() as bg_db:
        try:
            await import_all_skus(bg_db, 20)
            await bg_db.commit()
        except Exception:
            logger.exception("background sku full sync error")


@router.post("/sync/baison/skus")
async def sync_baison_skus(
    req: SkuSyncRequest,
    current_user: SysUser = Depends(require_permission("sync:import")),
    db: AsyncSession = Depends(get_db),
):
    """同步百胜 SKU 档案（prm.goods.sku_list_get）。

    full_sync=True：全量约 2048 页/40944 条、约 15 分钟，放后台任务执行并立即返回（避免网关超时）。
    full_sync=False：仅同步第 1 页（快速验证），返回明细计数。
    """
    try:
        if req.full_sync:
            _asyncio.create_task(_bg_full_sku_sync())
            return {"success": True, "message": "SKU 全量同步已在后台启动（约 2048 页 / 40944 条，约 15 分钟），完成后请刷新列表",
                    "data": {"method": SKU_LIST_METHOD, "page_total": 2048, "total_result": 40944, "mode": "background"}}
        r = await import_sku_page(db, 1, req.page_size)
        if not r.get("ok"):
            return {"success": False, "message": "同步失败", "error": r.get("error"), "data": r}
        return {"success": True, "message": "首页同步完成",
                "data": {"method": SKU_LIST_METHOD, "page_total": r.get("page_total"), "total_result": r.get("total_result"),
                         "ods_inserted": r.get("ods_inserted"), "ods_updated": r.get("ods_updated"),
                         "dim_inserted": r.get("dim_inserted"), "dim_updated": r.get("dim_updated"),
                         "skipped": r.get("skipped"), "batch_no": r.get("batch_no")}}
    except Exception:
        logger.exception("sku sync error")
        return {"success": False, "message": "内部错误，请查看服务日志"}


@router.get("/product/size-wall/overview")
async def size_wall_overview(
    analysis_date: Optional[date] = Query(None),
    store_code: Optional[str] = Query(None),
    current_user: SysUser = Depends(require_permission("product:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    codes = await _size_wall_codes(db, current_user, store_code)
    data = await SizeWallService().overview(db, codes, store_code, analysis_date)
    return {"success": True, "data": data}


@router.get("/product/size-wall/candidates")
async def size_wall_candidates(
    analysis_date: Optional[date] = Query(None), store_code: Optional[str] = Query(None),
    year: Optional[int] = Query(None), size_group: Optional[str] = Query(None),
    normalized_size_code: Optional[str] = Query(None), raw_size_code: Optional[str] = Query(None),
    size_code: Optional[str] = Query(None, description="兼容旧版，等同标准尺码筛选"),
    category_name: Optional[str] = Query(None), price_band: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None, ge=0, le=100), suggested_action: Optional[str] = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    current_user: SysUser = Depends(require_permission("product:overview:view")),
    db: AsyncSession = Depends(get_db),
):
    codes = await _size_wall_codes(db, current_user, store_code)
    data = await SizeWallService().candidates(
        db, codes, store_code=store_code, analysis_date=analysis_date, year=year,
        size_group=size_group, normalized_size_code=normalized_size_code,
        raw_size_code=raw_size_code, size_code=size_code,
        category_name=category_name, price_band_value=price_band,
        min_score=min_score, suggested_action=suggested_action, page=page, page_size=page_size,
    )
    image_urls = await sku_color_image_urls(db, data.get("items") or [])
    for item in data.get("items") or []:
        key = (str(item.get("product_code") or "").strip(), str(item.get("color_code") or "").strip())
        item["image_url"] = _image_proxy_path(image_urls.get(key))
    return {"success": True, "data": data}
