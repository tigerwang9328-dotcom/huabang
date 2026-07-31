"""v4.0 ranking amendment: outfit combinations and garment-position split rankings.

Covers:
- garment_styles.garment_position field (outer/top/bottom/none)
- outfit_combinations table and model
- outfit_color_metrics table and model
- video_color_metrics.garment_position derived field
- pure functions for combination key generation and split-ranking eligibility

v4.0 revised: one curve (clip) maps to one whole outfit (>=2 garments).
combination_key excludes color_id; garments are distinguished by SKU.
focus_status semantics: clear_primary=整套穿搭清晰可见; multi_focus=多套穿搭同屏;
unclear=无法判断整套穿搭.
"""

import pytest

from app.models.douyin_color_analytics import (
    GarmentStyle,
    OutfitCombination,
    OutfitColorMetric,
    VideoColorMetric,
)
from app.services.douyin_color_outfit_service import (
    OutfitCompositionError,
    build_combination_key,
    classify_garment_position_for_ranking,
    derive_outfit_participants,
    is_eligible_for_outfit_ranking,
    is_eligible_for_single_ranking,
    split_ranking_bucket,
)


def test_garment_style_has_garment_position_field_with_frozen_enum():
    """garment_styles must carry garment_position constrained to outer/top/bottom/none."""

    column = GarmentStyle.__table__.columns.get("garment_position")
    assert column is not None, "garment_styles.garment_position column missing"
    assert column.nullable is False, "garment_position must be NOT NULL"
    assert column.default is not None, "garment_position must have a default"

    check_clauses = [
        str(c.sqltext) for c in GarmentStyle.__table__.constraints
        if hasattr(c, "sqltext") and "garment_position" in str(c.sqltext)
    ]
    assert any("outer" in c and "top" in c and "bottom" in c and "none" in c for c in check_clauses), (
        "garment_position must have a CHECK constraint covering outer/top/bottom/none"
    )


def test_video_color_metric_has_garment_position_for_split_ranking():
    """video_color_metrics needs garment_position to split top vs bottom rankings."""

    column = VideoColorMetric.__table__.columns.get("garment_position")
    assert column is not None, "video_color_metrics.garment_position column missing"
    assert column.nullable is False, "garment_position must be NOT NULL"
    assert column.default is not None, "garment_position must have a default"


def test_outfit_combination_model_exists_with_frozen_fields():
    """outfit_combinations table must exist with the v4.0 frozen fields."""

    table = OutfitCombination.__table__
    assert table.name == "outfit_combinations"
    assert table.schema == "douyin"

    required_columns = {
        "id", "account_id", "video_id", "observation_window",
        "combination_key", "participant_count",
        "annotation_set_hash", "retention_snapshot_id", "bounce_snapshot_id",
        "created_at",
    }
    actual_columns = set(table.columns.keys())
    missing = required_columns - actual_columns
    assert not missing, f"outfit_combinations missing columns: {missing}"

    assert table.columns["participant_count"].nullable is False

    unique_constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
    assert any("uq" in name and "outfit" in name.lower() for name in unique_constraint_names), (
        "outfit_combinations must have a UNIQUE constraint on (account_id, video_id, observation_window, combination_key)"
    )


def test_outfit_color_metric_model_exists_with_outfit_key():
    """outfit_color_metrics table must exist with combination_key as part of the unique key."""

    table = OutfitColorMetric.__table__
    assert table.name == "outfit_color_metrics"
    assert table.schema == "douyin"

    required_columns = {
        "id", "account_id", "combination_key", "observation_window",
        "metric_version", "metric_input_hash",
        "average_retention", "retention_drop",
        "average_platform_bounce_curve_value", "max_platform_bounce_curve_value",
        "retention_calculation_status", "bounce_calculation_status",
        "calculated_at",
    }
    actual_columns = set(table.columns.keys())
    missing = required_columns - actual_columns
    assert not missing, f"outfit_color_metrics missing columns: {missing}"

    unique_constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
    assert any("uq" in name and "outfit" in name.lower() for name in unique_constraint_names), (
        "outfit_color_metrics must have a UNIQUE constraint including combination_key"
    )


def test_build_combination_key_sorts_by_garment_position_ascending():
    """combination_key must be deterministic: sorted by business order outer->top->bottom.

    v4.0: key format is "position:style_id" (no color_id); garments are
    distinguished by SKU, not color.
    """

    participants = [
        {"garment_position": "bottom", "style_id": 100, "sku_code": "WZ001-BLACK-M"},
        {"garment_position": "outer", "style_id": 300, "sku_code": "WZ003-RED-L"},
        {"garment_position": "top", "style_id": 500, "sku_code": "WZ005-BLUE-M"},
    ]
    key = build_combination_key(participants)
    assert key == "outer:300|top:500|bottom:100", (
        "combination_key must sort by business order outer -> top -> bottom and "
        "exclude color_id"
    )


def test_build_combination_key_rejects_fewer_than_two_participants():
    """Outfit ranking requires at least 2 qualifying garments."""

    with pytest.raises(OutfitCompositionError, match="insufficient_participants"):
        build_combination_key([
            {"garment_position": "top", "style_id": 500, "sku_code": "WZ005-BLUE-M"},
        ])


def test_build_combination_key_rejects_none_or_other_positions():
    """none/other garments must never enter an outfit combination."""

    with pytest.raises(OutfitCompositionError, match="invalid_garment_position"):
        build_combination_key([
            {"garment_position": "none", "style_id": 1, "sku_code": None},
            {"garment_position": "top", "style_id": 3, "sku_code": "WZ003-RED-M"},
        ])


def test_derive_outfit_participants_collects_approved_clear_primary_clips():
    """Only clear_primary + approved + overlap-approved clips join an outfit.

    v4.0: each qualifying clip carries outfit_parts_json describing the whole
    outfit; participants are collected from those parts (deduplicated).
    """

    clips = [
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [{"position": "outer", "style_id": 10, "sku_code": "WZ010-RED-M"}]},
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "approved",
         "outfit_parts_json": [{"position": "top", "style_id": 30, "sku_code": "WZ030-BLUE-M"}]},
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [{"position": "bottom", "style_id": 50, "sku_code": "WZ050-BLACK-L"}]},
        {"focus_status": "multi_focus", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [{"position": "top", "style_id": 70, "sku_code": "WZ070-GREEN-M"}]},
        {"focus_status": "clear_primary", "annotation_status": "submitted", "overlap_status": "not_required",
         "outfit_parts_json": [{"position": "bottom", "style_id": 90, "sku_code": "WZ090-BLACK-L"}]},
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "pending_approval",
         "outfit_parts_json": [{"position": "outer", "style_id": 110, "sku_code": "WZ110-RED-L"}]},
    ]
    participants = derive_outfit_participants(clips)
    positions = sorted(p["garment_position"] for p in participants)
    assert positions == ["bottom", "outer", "top"], (
        "only clear_primary+approved+overlap(approved|not_required) clips qualify"
    )
    # sku_code is carried through, color_id is absent
    assert all("color_id" not in p for p in participants)
    assert all("sku_code" in p for p in participants)


def test_derive_outfit_participants_deduplicates_repeated_outfit_parts():
    """Multiple clips showing the same outfit must not double-count garments."""

    clips = [
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [
             {"position": "top", "style_id": 30, "sku_code": "WZ030-BLUE-M"},
             {"position": "bottom", "style_id": 50, "sku_code": "WZ050-BLACK-L"},
         ]},
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [
             {"position": "top", "style_id": 30, "sku_code": "WZ030-BLUE-M"},
             {"position": "bottom", "style_id": 50, "sku_code": "WZ050-BLACK-L"},
         ]},
    ]
    participants = derive_outfit_participants(clips)
    assert len(participants) == 2  # deduplicated


def test_derive_outfit_participants_allows_null_sku_code():
    """sku_code may be None when the SKU is not yet resolved."""

    clips = [
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [
             {"position": "top", "style_id": 30, "sku_code": None},
             {"position": "bottom", "style_id": 50, "sku_code": None},
         ]},
    ]
    participants = derive_outfit_participants(clips)
    assert all(p["sku_code"] is None for p in participants)
    assert len(participants) == 2


def test_is_eligible_for_outfit_ranking_requires_at_least_two_qualifying_garments():
    """A video with only 1 qualifying garment cannot enter outfit ranking."""

    assert is_eligible_for_outfit_ranking([
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [{"position": "top", "style_id": 1, "sku_code": "WZ001-M"}]},
    ]) is False

    assert is_eligible_for_outfit_ranking([
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [
             {"position": "top", "style_id": 1, "sku_code": "WZ001-M"},
             {"position": "bottom", "style_id": 3, "sku_code": "WZ003-L"},
         ]},
    ]) is True


def test_is_eligible_for_single_ranking_keeps_clear_primary_approved_only():
    """Single-garment ranking eligibility reuses v3.1 semantics.

    clear_primary = a whole outfit is clearly visible.
    """

    assert is_eligible_for_single_ranking(
        focus_status="clear_primary", annotation_status="approved", overlap_status="not_required"
    ) is True

    assert is_eligible_for_single_ranking(
        focus_status="multi_focus", annotation_status="approved", overlap_status="not_required"
    ) is False

    assert is_eligible_for_single_ranking(
        focus_status="unclear", annotation_status="approved", overlap_status="not_required"
    ) is False

    assert is_eligible_for_single_ranking(
        focus_status="clear_primary", annotation_status="submitted", overlap_status="not_required"
    ) is False


def test_split_ranking_bucket_assigns_top_outer_to_top_bucket_and_bottom_to_bottom():
    """split_ranking_bucket maps garment_position to the correct ranking bucket."""

    assert split_ranking_bucket("outer") == "top"
    assert split_ranking_bucket("top") == "top"
    assert split_ranking_bucket("bottom") == "bottom"
    assert split_ranking_bucket("none") is None
    assert split_ranking_bucket("other") is None


def test_classify_garment_position_for_ranking_rejects_invalid_values():
    """garment_position must be one of outer/top/bottom/none."""

    assert classify_garment_position_for_ranking("outer") == "outer"
    assert classify_garment_position_for_ranking("top") == "top"
    assert classify_garment_position_for_ranking("bottom") == "bottom"
    assert classify_garment_position_for_ranking("none") == "none"

    with pytest.raises(OutfitCompositionError, match="invalid_garment_position"):
        classify_garment_position_for_ranking("dress")


def test_outfit_combination_supports_two_piece_without_outer():
    """2-piece outfit (top+bottom, no outer) is valid per v4.0."""

    participants = [
        {"garment_position": "top", "style_id": 100, "sku_code": "WZ100-M"},
        {"garment_position": "bottom", "style_id": 300, "sku_code": "WZ300-L"},
    ]
    key = build_combination_key(participants)
    assert key == "top:100|bottom:300"
    assert is_eligible_for_outfit_ranking([
        {"focus_status": "clear_primary", "annotation_status": "approved", "overlap_status": "not_required",
         "outfit_parts_json": [
             {"position": "top", "style_id": 100, "sku_code": "WZ100-M"},
             {"position": "bottom", "style_id": 300, "sku_code": "WZ300-L"},
         ]},
    ]) is True


def test_outfit_combination_supports_three_piece_with_outer():
    """3-piece outfit (outer+top+bottom) is valid per v4.0."""

    participants = [
        {"garment_position": "outer", "style_id": 100, "sku_code": "WZ100-L"},
        {"garment_position": "top", "style_id": 300, "sku_code": "WZ300-M"},
        {"garment_position": "bottom", "style_id": 500, "sku_code": "WZ500-L"},
    ]
    key = build_combination_key(participants)
    assert key == "outer:100|top:300|bottom:500"
