"""Opt-in production-database contract for Douyin product annotation.

The test never commits.  It verifies the archive lookup that turns a selected
style/SKU into a server-owned immutable clip snapshot.
"""

import os

import pytest
from sqlalchemy import select, text


@pytest.mark.asyncio
async def test_real_product_archive_materializes_sku_snapshot_and_rejects_cross_product_sku():
    if os.getenv("RUN_DOUYIN_PRODUCT_ARCHIVE_INTEGRATION") != "1":
        pytest.skip("set RUN_DOUYIN_PRODUCT_ARCHIVE_INTEGRATION=1 to run against PostgreSQL")

    from app.api.v1.douyin_color_annotation_routes import _materialize_outfit_parts
    from app.core.database import AsyncSessionLocal
    from app.models.douyin_color_analytics import DouyinCreatorAccount, GarmentStyle
    from app.schemas.douyin_color_analytics import OutfitPartRequest
    from app.services.douyin_color_annotation_service import AnnotationValidationError

    async with AsyncSessionLocal() as db:
        try:
            account = (await db.execute(select(DouyinCreatorAccount).where(
                DouyinCreatorAccount.status == "active",
            ))).scalar_one()
            archive = (await db.execute(text("""
                SELECT product_code, max(product_name) AS product_name, min(sku_code) AS sku_code
                FROM dim.dim_sku
                WHERE status = 'active' AND sku_code IS NOT NULL
                GROUP BY product_code
                ORDER BY product_code
                LIMIT 1
            """))).mappings().one()
            foreign_sku = (await db.execute(text("""
                SELECT sku_code FROM dim.dim_sku
                WHERE status = 'active' AND sku_code IS NOT NULL AND product_code <> :product_code
                ORDER BY sku_code
                LIMIT 1
            """), {"product_code": archive["product_code"]})).scalar_one()
            style = (await db.execute(select(GarmentStyle).where(
                GarmentStyle.account_id == account.id,
                GarmentStyle.style_code == archive["product_code"],
            ))).scalar_one_or_none()
            if style is None:
                style = GarmentStyle(
                    account_id=account.id,
                    style_code=archive["product_code"],
                    style_name=archive["product_name"] or archive["product_code"],
                    status="active",
                )
                db.add(style)
                await db.flush()
            elif style.status != "active":
                style.status = "active"
                await db.flush()

            snapshots = await _materialize_outfit_parts(
                db=db,
                account_id=account.id,
                payload_parts=[
                    OutfitPartRequest(position="top", style_id=style.id, sku_code=archive["sku_code"]),
                    OutfitPartRequest(position="bottom", style_id=style.id, sku_code=None),
                ],
            )
            assert snapshots[0]["product_code"] == archive["product_code"]
            assert snapshots[0]["sku_code"] == archive["sku_code"]
            assert snapshots[0]["product_name"]
            with pytest.raises(AnnotationValidationError, match="sku_not_found_for_product"):
                await _materialize_outfit_parts(
                    db=db,
                    account_id=account.id,
                    payload_parts=[OutfitPartRequest(position="top", style_id=style.id, sku_code=foreign_sku)],
                )
        finally:
            await db.rollback()
