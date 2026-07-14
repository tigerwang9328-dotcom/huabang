import asyncio

import pytest
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.core.store_whitelist import ALLOWED_INVENTORY_CODES
from app.services.size_wall_service import (
    CLOTHING_CATEGORIES,
    SizeWallService,
    calculate_candidate_score,
    classify_size_group,
    choose_action,
    classify_size_status,
    is_clothing_category,
    is_candidate_score,
    is_eligible_year,
    is_valid_wall_size,
    normalize_size_code,
    parse_sale_sku,
    size_sort_value,
)


def test_candidate_threshold_is_inclusive_at_60():
    assert not is_candidate_score(59)
    assert is_candidate_score(60)


def test_score_combines_year_movement_and_single_size():
    result = calculate_candidate_score(
        year=2025,
        current_year=2026,
        sales_qty_30d=2,
        remaining_size_count=1,
        listed_size_count=5,
        remaining_color_count=3,
        listed_color_count=5,
    )
    assert result.score == 60
    assert result.structure_score == 35
    assert "单码" in result.reasons


def test_size_structure_scores_double_size_and_40_percent_boundary():
    double_size = calculate_candidate_score(
        year=2025, current_year=2026, sales_qty_30d=4,
        remaining_size_count=2, listed_size_count=5,
        remaining_color_count=3, listed_color_count=5,
    )
    boundary = calculate_candidate_score(
        year=2025, current_year=2026, sales_qty_30d=4,
        remaining_size_count=4, listed_size_count=10,
        remaining_color_count=3, listed_color_count=5,
    )
    above_boundary = calculate_candidate_score(
        year=2025, current_year=2026, sales_qty_30d=4,
        remaining_size_count=5, listed_size_count=12,
        remaining_color_count=3, listed_color_count=5,
    )
    assert double_size.structure_score == 25
    assert boundary.structure_score == 20
    assert above_boundary.structure_score == 0


def test_year_window_excludes_current_and_older_stock():
    assert is_eligible_year(2023, 2026)
    assert is_eligible_year(2025, 2026)
    assert not is_eligible_year(2026, 2026)
    assert not is_eligible_year(2022, 2026)
    assert not is_eligible_year(None, 2026)


def test_sale_sku_parser_normalizes_color_and_size():
    assert parse_sale_sku("31262T144|-02|52Y") == ("31262T144", "02", "52Y")
    assert parse_sale_sku("") is None


def test_only_clothing_categories_enter_size_wall():
    for category in ["裤子", "羽绒服", "裙子", "保暖内衣", "衬衫(停用)"]:
        assert is_clothing_category(category)
    for category in ["袜子", "围巾", "鞋子", "皮带", "包类", "赠品", "未定义", "未分类"]:
        assert not is_clothing_category(category)


def test_free_size_is_excluded_but_all_fitted_size_families_are_valid():
    assert not is_valid_wall_size("F")
    assert not is_valid_wall_size("46Y")
    assert not is_valid_wall_size("58Y")
    assert not is_valid_wall_size("")
    for size in ["44Y", "48Y", "56Y", "60Y", "XXS", "5XL", "23N", "46K", "38Z", "46Z", "50P", "100"]:
        assert is_valid_wall_size(size)


def test_size_aliases_groups_and_sorting_are_stable():
    assert normalize_size_code("XXL") == "2XL"
    assert normalize_size_code("XXXL") == "3XL"
    assert normalize_size_code("XS-1") == "XS-1"
    assert classify_size_group("48Y") == "numeric_top"
    assert classify_size_group("2XL") == "letter"
    assert classify_size_group("31N") == "pants"
    assert classify_size_group("34K") == "pants"
    assert classify_size_group("42Z") == "collar"
    assert classify_size_group("50P") == "other"
    assert size_sort_value("48Y") < size_sort_value("52Y")
    assert size_sort_value("M") < size_sort_value("2XL")
    assert size_sort_value("31K") < size_sort_value("38K")


def test_size_status_uses_default_thresholds():
    assert classify_size_status(0) == "无候选"
    assert classify_size_status(4) == "少量候选"
    assert classify_size_status(5) == "可集中陈列"
    assert classify_size_status(20) == "可集中陈列"
    assert classify_size_status(21) == "候选积压"


def test_action_priority_is_deterministic():
    assert choose_action(distribution_count=3, local_qty=2, company_qty=6, sales_qty_30d=2, tag_price=500) == "集中调拨"
    assert choose_action(distribution_count=1, local_qty=12, company_qty=12, sales_qty_30d=0, tag_price=500) == "集中清仓"
    assert choose_action(distribution_count=1, local_qty=2, company_qty=2, sales_qty_30d=1, tag_price=800) == "VIP定向推荐"
    assert choose_action(distribution_count=1, local_qty=3, company_qty=3, sales_qty_30d=2, tag_price=500) == "搭配销售"


def test_warehouse_is_not_treated_as_multi_store_distribution():
    assert choose_action(
        distribution_count=3, local_qty=2, company_qty=6,
        sales_qty_30d=2, tag_price=500, location_type="warehouse",
    ) == "搭配销售"


def test_store_with_enough_local_stock_gets_concentrated_display_advice():
    assert choose_action(
        distribution_count=1, local_qty=5, company_qty=5,
        sales_qty_30d=2, tag_price=500, location_type="store",
    ) == "集中陈列"


def test_store_scope_rejects_unbound_location():
    with pytest.raises(PermissionError):
        SizeWallService._codes(["285204"], "185805")


async def _load_live_payloads():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        service = SizeWallService()
        overview = await service.overview(db, sorted(ALLOWED_INVENTORY_CODES))
        candidates = await service.candidates(db, sorted(ALLOWED_INVENTORY_CODES), page=1, page_size=5)
        filtered = await service.candidates(
            db, sorted(ALLOWED_INVENTORY_CODES), year=2023, size_code="50Y",
            min_score=60, page=1, page_size=5,
        )
        parse_coverage = (await db.execute(text("""
            select count(*) total,count(s.product_code) matched
            from dwd.dwd_pos_sale_goods g
            left join dim.dim_sku s on s.product_code=g.product_code
             and trim(leading '-' from coalesce(s.color_code,''))=trim(leading '-' from split_part(g.sku_code,'|',2))
             and coalesce(s.size_code,'')=split_part(g.sku_code,'|',3)
        """))).mappings().one()
        snapshot_scope = (await db.execute(text("""
            select distinct category_name,size_code from dm.dm_size_wall_candidate_daily
        """))).mappings().all()
    await engine.dispose()
    return overview, candidates, filtered, parse_coverage, snapshot_scope


def test_live_snapshot_exposes_overview_and_candidates():
    overview, candidates, filtered, parse_coverage, snapshot_scope = asyncio.run(_load_live_payloads())
    assert overview["analysis_date"]
    size_codes = {row["size_code"] for row in overview["size_summary"]}
    assert "F" not in size_codes
    assert {row["code"] for row in overview["size_groups"]} >= {"numeric_top", "letter", "pants"}
    assert {"48Y", "50Y", "52Y", "54Y"} < size_codes
    assert overview["data_coverage"]["candidate_style_colors"] >= 250
    assert {row["store_code"] for row in overview["location_options"]} == set(ALLOWED_INVENTORY_CODES)
    assert overview["store_matrix"]
    assert all(row["apparel_inventory_qty"] >= row["candidate_qty"] >= 0 for row in overview["store_matrix"])
    assert all(0 <= row["candidate_ratio"] <= 1 for row in overview["store_matrix"])
    assert candidates["total"] > 0
    assert candidates["items"][0]["score"] >= 60
    assert candidates["items"][0]["remaining_size_codes"]
    assert len(candidates["items"][0]["remaining_size_codes"]) == candidates["items"][0]["remaining_size_count"]
    assert 0 < len(filtered["items"]) <= 5
    assert all(row["product_year"] == 2023 and row["normalized_size_code"] == "50Y" for row in filtered["items"])
    assert all(row["raw_size_code"] for row in filtered["items"])
    assert parse_coverage["total"] >= 2660
    assert parse_coverage["matched"] == parse_coverage["total"]
    assert all(row["category_name"] in CLOTHING_CATEGORIES and str(row["size_code"]).upper() != "F" for row in snapshot_scope)
