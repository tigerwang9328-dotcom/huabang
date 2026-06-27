"""百胜来源门店维(dim.dim_baison_shop) -> 华邦标准门店维(dim.dim_store) 数据归位。

百胜只是 source_system='baison' 的来源之一；标准门店维供门店运营中心读取。
按 (store_code, source_system) upsert，重复同步幂等。不删除 dim_baison_shop。
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dim import DimBaisonShop, DimStore

logger = logging.getLogger("baison.store_mapping")
SOURCE_SYSTEM = "baison"


def _status_from_enabled(is_enabled) -> str:
    return "营业" if str(is_enabled) == "1" else "停用"


def _map(b: DimBaisonShop, now: datetime) -> dict:
    return {
        "store_code": b.shop_code,
        "store_name": b.shop_name,
        "region": b.area_name,            # 兼容旧列
        "region_code": b.area_code,
        "region_name": b.area_name,
        "province": b.province,
        "city": b.city,
        "county": b.county,
        "channel": b.channel_name,        # 兼容旧列
        "channel_code": b.channel_code,
        "channel_name": b.channel_name,
        "store_type": b.shop_type,
        "business_type": b.online_type,
        "category_code": b.category_code,
        "category_name": b.category_name,
        "address": b.address,
        "status": _status_from_enabled(b.is_enabled),
        "source_system": SOURCE_SYSTEM,
        "source_store_id": b.shop_id,
        "source_last_changed": b.last_changed,
        "synced_at": b.synced_at or now,
        "updated_at": now,
    }


async def map_baison_to_dim_store(db: AsyncSession) -> dict:
    """把 dim_baison_shop 全量映射 upsert 到 dim_store(source_system=baison)。"""
    now = datetime.now(timezone.utc)
    shops = (await db.execute(select(DimBaisonShop))).scalars().all()
    codes = [s.shop_code for s in shops if s.shop_code]
    existing = set()
    if codes:
        existing = set((await db.execute(
            select(DimStore.store_code).where(
                DimStore.store_code.in_(codes), DimStore.source_system == SOURCE_SYSTEM
            )
        )).scalars().all())

    inserted = updated = skipped = 0
    for b in shops:
        if not b.shop_code:
            skipped += 1
            continue
        row = _map(b, now)
        if b.shop_code in existing:
            updated += 1
        else:
            inserted += 1
            existing.add(b.shop_code)
        stmt = pg_insert(DimStore).values(**row)
        upd = {k: stmt.excluded[k] for k in row if k not in ("store_code", "source_system", "created_at")}
        stmt = stmt.on_conflict_do_update(constraint="uq_dim_store_code_source", set_=upd)
        await db.execute(stmt)
    await db.flush()
    logger.info("map baison->dim_store: total=%s inserted=%s updated=%s skipped=%s",
                len(shops), inserted, updated, skipped)
    return {"total": len(shops), "inserted": inserted, "updated": updated, "skipped": skipped}
