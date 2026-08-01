"""Task 2: 固定资产 CRUD 路由测试(复用 finance_center_mumaren_fixed_assets)。"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_domains import (
    FixedAssetInput,
    FixedAssetUpdate,
    create_fixed_asset,
    delete_fixed_asset,
    depreciate_fixed_asset,
    list_fixed_assets,
    update_fixed_asset,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenFixedAsset


def _asset(*, asset_id=1, book_id=1, status="draft", accumulated=Decimal("0")):
    return FinanceCenterMumarenFixedAsset(
        id=asset_id, book_id=book_id, asset_code="A001", asset_name="服务器",
        asset_category="IT设备", purchase_date=date(2026, 1, 1),
        original_value=Decimal("12000.00"), residual_value=Decimal("1200.00"),
        useful_life_months=60, accumulated_depreciation=accumulated, status=status,
    )


@pytest.mark.asyncio
async def test_create_fixed_asset_persists_draft_and_writes_audit_log():
    db = _MockDb()
    user = _FakeUser(user_id=7)
    res = await create_fixed_asset(
        body=FixedAssetInput(
            book_id=1, asset_code="A001", asset_name="服务器", asset_category="IT设备",
            purchase_date=date(2026, 1, 1), original_value=Decimal("12000"),
            residual_value=Decimal("1200"), useful_life_months=60,
        ),
        current_user=user, db=db,
    )
    assert res.data["status"] == "draft"
    assert res.data["accumulated_depreciation"] == Decimal("0")
    logs = db.audit_logs("create_fixed_asset")
    assert len(logs) == 1
    assert logs[0].book_id == 1
    assert logs[0].operator_id == 7


@pytest.mark.asyncio
async def test_list_fixed_assets_returns_rows_bounded_by_limit():
    rows = [_asset(asset_id=1), _asset(asset_id=2, book_id=1)]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    result = await list_fixed_assets(book_id=1, limit=100, _=_FakeUser(), db=db)
    assert result.success
    assert len(result.data) == 2


@pytest.mark.asyncio
async def test_update_fixed_asset_rejects_cross_book_and_writes_audit_log():
    asset = _asset(asset_id=1, book_id=1, status="draft")
    db = _MockDb(get_map={FinanceCenterMumarenFixedAsset: {1: asset}})
    user = _FakeUser(user_id=8)
    with pytest.raises(HTTPException) as exc:
        await update_fixed_asset(
            asset_id=1, body=FixedAssetUpdate(book_id=2, asset_name="新名"),
            current_user=user, db=db,
        )
    assert exc.value.status_code == 400
    assert db.audit_logs() == []

    db2 = _MockDb(get_map={FinanceCenterMumarenFixedAsset: {1: asset}})
    updated = await update_fixed_asset(
        asset_id=1, body=FixedAssetUpdate(book_id=1, asset_name="新名"),
        current_user=user, db=db2,
    )
    assert updated.data["asset_name"] == "新名"
    assert len(db2.audit_logs("update_fixed_asset")) == 1


@pytest.mark.asyncio
async def test_update_fixed_asset_rejects_non_editable_status():
    asset = _asset(asset_id=1, status="disposed")
    db = _MockDb(get_map={FinanceCenterMumarenFixedAsset: {1: asset}})
    with pytest.raises(HTTPException) as exc:
        await update_fixed_asset(
            asset_id=1, body=FixedAssetUpdate(book_id=1, asset_name="x"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_fixed_asset_only_allows_draft():
    asset = _asset(asset_id=1, status="active")
    db = _MockDb(get_map={FinanceCenterMumarenFixedAsset: {1: asset}})
    with pytest.raises(HTTPException) as exc:
        await delete_fixed_asset(asset_id=1, book_id=1, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 409

    draft = _asset(asset_id=1, status="draft")
    db2 = _MockDb(get_map={FinanceCenterMumarenFixedAsset: {1: draft}})
    res = await delete_fixed_asset(asset_id=1, book_id=1, current_user=_FakeUser(user_id=9), db=db2)
    assert res.success
    assert len(db2.deleted) == 1
    assert len(db2.audit_logs("delete_fixed_asset")) == 1


@pytest.mark.asyncio
async def test_depreciate_accumulates_and_caps_at_depreciable_amount():
    asset = _asset(asset_id=1, accumulated=Decimal("0"))
    db = _MockDb(get_map={FinanceCenterMumarenFixedAsset: {1: asset}})
    res = await depreciate_fixed_asset(asset_id=1, book_id=1, current_user=_FakeUser(), db=db)
    # (12000 - 1200) / 60 = 180.00
    assert res.data["accumulated_depreciation"] == Decimal("180.00")
    assert len(db.audit_logs("depreciate_fixed_asset")) == 1

    # 折旧到接近上限时封顶
    near_full = _asset(asset_id=2, accumulated=Decimal("10750.00"))
    db2 = _MockDb(get_map={FinanceCenterMumarenFixedAsset: {2: near_full}})
    res2 = await depreciate_fixed_asset(asset_id=2, book_id=1, current_user=_FakeUser(), db=db2)
    assert res2.data["accumulated_depreciation"] == Decimal("10800.00")
