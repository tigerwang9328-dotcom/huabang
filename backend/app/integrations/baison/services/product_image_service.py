"""百胜商品图片同步与查询。

链路：file.goods.image.batch -> dim.dim_product_image -> 商品中心/SKU档案。
SKU 页面只按 商品款号 + 颜色 展示颜色图；没有颜色图时返回空，不回退商品主图。
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.baison.client import BaisonClient

logger = logging.getLogger("baison.product_image_service")

PRODUCT_IMAGE_BATCH_METHOD = "file.goods.image.batch"
SOURCE_SYSTEM = "baison"


def _trim(value) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _parse_response(data) -> list[dict]:
    if not isinstance(data, dict):
        return []
    success = str(data.get("code")) == "1" and str(data.get("flag")).lower() == "success"
    if not success:
        return []
    payload = data.get("data")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            payload = None
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data")
    return rows if isinstance(rows, list) else []


def _chunked(items: list[tuple[str, str]], size: int = 50) -> Iterable[list[tuple[str, str]]]:
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def fetch_product_images(pairs: list[tuple[str, str]], client: Optional[BaisonClient] = None) -> list[dict]:
    client = client or BaisonClient()
    rows: list[dict] = []
    for chunk in _chunked(pairs):
        goods = [{"GoodsCode": product_code, "ColorCode": color_code} for product_code, color_code in chunk]
        resp = client.request(
            PRODUCT_IMAGE_BATCH_METHOD,
            {"PageNo": 1, "PageSize": max(len(goods), 1), "Goods": goods},
            timeout=30,
        )
        rows.extend(_parse_response(resp.data))
    return rows


async def ensure_product_image_table(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS dim.dim_product_image (
            id BIGSERIAL PRIMARY KEY,
            product_code VARCHAR(64) NOT NULL,
            color_code VARCHAR(32) NOT NULL DEFAULT '',
            image_url TEXT,
            is_main_pic BOOLEAN DEFAULT FALSE,
            raw_data JSONB,
            source_system VARCHAR(32) NOT NULL DEFAULT 'baison',
            synced_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_dim_product_image_color_source
                UNIQUE (product_code, color_code, source_system)
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_dim_product_image_product_color
        ON dim.dim_product_image (product_code, color_code)
    """))


def _sku_pairs(sku_rows: list[dict]) -> list[tuple[str, str]]:
    pairs = []
    seen = set()
    for row in sku_rows:
        product_code = _trim(row.get("product_code"))
        color_code = _trim(row.get("color_code"))
        if not product_code or not color_code:
            continue
        key = (product_code, color_code)
        if key not in seen:
            pairs.append(key)
            seen.add(key)
    return pairs


async def _load_cached_images(db: AsyncSession, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], Optional[str]]:
    if not pairs:
        return {}
    rows = (await db.execute(text("""
        SELECT product_code, color_code, image_url
        FROM dim.dim_product_image
        WHERE source_system = :source_system
          AND (product_code, color_code) IN (
              SELECT * FROM unnest(CAST(:product_codes AS varchar[]), CAST(:color_codes AS varchar[]))
          )
    """), {
        "source_system": SOURCE_SYSTEM,
        "product_codes": [p[0] for p in pairs],
        "color_codes": [p[1] for p in pairs],
    })).mappings().all()
    return {
        (_trim(row["product_code"]) or "", _trim(row["color_code"]) or ""): row["image_url"]
        for row in rows
    }


async def _upsert_image_rows(
    db: AsyncSession,
    pairs: list[tuple[str, str]],
    api_rows: list[dict],
    now: datetime,
) -> dict[tuple[str, str], Optional[str]]:
    selected: dict[tuple[str, str], dict] = {}
    for row in api_rows:
        if not isinstance(row, dict):
            continue
        product_code = _trim(row.get("GoodsCode"))
        color_code = _trim(row.get("ColorCode"))
        if not product_code or not color_code:
            continue
        key = (product_code, color_code)
        current = selected.get(key)
        if current is None or (not current.get("IsMainPic") and row.get("IsMainPic")):
            selected[key] = row

    urls: dict[tuple[str, str], Optional[str]] = {}
    for product_code, color_code in pairs:
        row = selected.get((product_code, color_code))
        image_url = _trim(row.get("ImageUrl")) if row else None
        is_main_pic = str(row.get("IsMainPic")) in ("1", "true", "True") if row else False
        urls[(product_code, color_code)] = image_url
        await db.execute(text("""
            INSERT INTO dim.dim_product_image
                (product_code, color_code, image_url, is_main_pic, raw_data, source_system, synced_at, updated_at)
            VALUES
                (:product_code, :color_code, :image_url, :is_main_pic, CAST(:raw_data AS jsonb), :source_system, :synced_at, :synced_at)
            ON CONFLICT (product_code, color_code, source_system)
            DO UPDATE SET
                image_url = EXCLUDED.image_url,
                is_main_pic = EXCLUDED.is_main_pic,
                raw_data = EXCLUDED.raw_data,
                synced_at = EXCLUDED.synced_at,
                updated_at = EXCLUDED.updated_at
        """), {
            "product_code": product_code,
            "color_code": color_code,
            "image_url": image_url,
            "is_main_pic": is_main_pic,
            "raw_data": json.dumps(row or {}, ensure_ascii=False),
            "source_system": SOURCE_SYSTEM,
            "synced_at": now,
        })
    return urls


async def sku_color_image_urls(db: AsyncSession, sku_rows: list[dict]) -> dict[tuple[str, str], Optional[str]]:
    await ensure_product_image_table(db)
    pairs = _sku_pairs(sku_rows)
    if not pairs:
        return {}

    cached = await _load_cached_images(db, pairs)
    missing_pairs = [pair for pair in pairs if pair not in cached]
    if missing_pairs:
        try:
            api_rows = await asyncio.to_thread(fetch_product_images, missing_pairs)
            fetched = await _upsert_image_rows(db, missing_pairs, api_rows, datetime.now(timezone.utc))
            cached.update(fetched)
        except Exception:
            logger.exception("fetch baison product images failed")
    return cached
