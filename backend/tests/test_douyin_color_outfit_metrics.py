"""Task 5 v4.0: outfit-level metric computation (>=2 qualifying garments).

Outfit metrics aggregate across garments in the same video:
- Requires >=2 qualifying clear_primary+approved clips whose outfit_parts_json
  describes a whole outfit (>=2 garments)
- combination_key identifies the outfit (outer+top+bottom sorted, no color_id)
- Retention/bounce computed by duration-weighted aggregation across all
  qualifying clips (the whole-outfit curve)
- Independent from per-garment metrics (video_color_metrics)

v4.0 revised: one curve (clip) maps to one whole outfit. combination_key
excludes color_id; garments are distinguished by SKU.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.services.douyin_color_metrics_service import compute_outfit_metric
from app.services.douyin_color_outfit_service import build_combination_key


def _clip(clip_id, start_ms, end_ms, outfit_parts):
    """A qualifying clip carrying a whole-outfit garment breakdown."""

    return {
        "id": clip_id, "version": 1,
        "start_ms": start_ms, "end_ms": end_ms,
        "input_start_ms": start_ms, "input_end_ms": end_ms,
        "curve_resolution_ms": 1000,
        "focus_status": "clear_primary",
        "annotation_status": "approved",
        "overlap_status": "not_required",
        "outfit_parts_json": outfit_parts,
    }


def _parts(*triples):
    """Build outfit_parts_json from (position, style_id, sku_code) tuples."""

    return [
        {"position": pos, "style_id": sid, "sku_code": sku}
        for pos, sid, sku in triples
    ]


def _retention(curve, source_hash="ret_hash"):
    return {
        "id": 1, "analysis_type": 1, "curve_quality_status": "ok",
        "item_status": "success",
        "collected_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "normalized_curve_json": curve,
        "source_snapshot_hash": source_hash,
    }


def test_compute_outfit_metric_returns_none_for_single_garment():
    """<2 qualifying garments -> no outfit metric."""

    clips = [_clip(1, 0, 2000, _parts(("top", 10, "WZ010-M")))]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention([{"second": 0, "value": 0.5}]),
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is None


def test_compute_outfit_metric_aggregates_two_garments():
    """2-piece outfit (top+bottom) produces a metric with combination_key (no color_id)."""

    curve = [{"second": i, "value": 0.5 + i * 0.1} for i in range(6)]
    clips = [_clip(1, 0, 2000, _parts(("top", 10, "WZ010-M"), ("bottom", 30, "WZ030-L")))]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention(curve),
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None
    assert metric["participant_count"] == 2
    assert "top:10" in metric["combination_key"]
    assert "bottom:30" in metric["combination_key"]
    # combination_key must not carry color_id
    assert "top:10:" not in metric["combination_key"]
    assert metric["retention_calculation_status"] == "computed"
    assert metric["average_retention"] is not None


def test_compute_outfit_metric_aggregates_three_garments():
    """3-piece outfit (outer+top+bottom) produces a metric."""

    curve = [{"second": i, "value": 0.5} for i in range(10)]
    clips = [_clip(1, 0, 2000, _parts(
        ("outer", 100, "WZ100-L"),
        ("top", 300, "WZ300-M"),
        ("bottom", 500, "WZ500-L"),
    ))]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention(curve),
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None
    assert metric["participant_count"] == 3
    assert metric["combination_key"] == "outer:100|top:300|bottom:500"


def test_compute_outfit_metric_excludes_none_position_parts():
    """outfit_parts with position=none don't count toward outfit participation."""

    curve = [{"second": i, "value": 0.5} for i in range(6)]
    clips = [_clip(1, 0, 2000, _parts(
        ("top", 10, "WZ010-M"),
        ("bottom", 30, "WZ030-L"),
        ("none", 70, "WZ070-M"),
    ))]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention(curve),
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None
    assert metric["participant_count"] == 2  # none part excluded


def test_compute_outfit_metric_bounce_stays_platform_bounce_curve_value():
    """Outfit bounce is platform_bounce_curve_value, never 'bounce rate'."""

    curve = [{"second": i, "value": 0.3 + i * 0.05} for i in range(6)]
    bounce = {
        "id": 2, "analysis_type": 7, "curve_quality_status": "ok",
        "item_status": "success",
        "collected_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "normalized_curve_json": curve,
        "source_snapshot_hash": "bounce_hash",
    }
    clips = [_clip(1, 0, 2000, _parts(("top", 10, "WZ010-M"), ("bottom", 30, "WZ030-L")))]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention(curve),
        bounce_snapshot=bounce, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None
    assert metric["bounce_calculation_status"] == "computed"
    assert metric["average_platform_bounce_curve_value"] is not None
    # Field name must be platform_bounce_curve_value, never bounce_rate
    assert "bounce_rate" not in metric


def test_compute_outfit_metric_returns_insufficient_data_without_retention():
    """No retention snapshot -> insufficient_data for retention."""

    clips = [_clip(1, 0, 2000, _parts(("top", 10, "WZ010-M"), ("bottom", 30, "WZ030-L")))]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=None,
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None  # outfit exists but no data
    assert metric["retention_calculation_status"] == "insufficient_data"
    assert metric["average_retention"] is None


def test_compute_outfit_metric_combination_key_is_color_free():
    """combination_key format is position:style_id (no color_id) per v4.0."""

    participants = _parts(("outer", 100, "WZ100-L"), ("top", 300, "WZ300-M"), ("bottom", 500, "WZ500-L"))
    # build_combination_key consumes participant dicts with garment_position key
    key = build_combination_key([
        {"garment_position": p["position"], "style_id": p["style_id"], "sku_code": p["sku_code"]}
        for p in participants
    ])
    assert key == "outer:100|top:300|bottom:500"
