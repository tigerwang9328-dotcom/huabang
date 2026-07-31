"""Task 5 v4.0: outfit-level metric computation (>=2 qualifying garments).

Outfit metrics aggregate across garments in the same video:
- Requires >=2 qualifying clear_primary+approved clips with valid garment_position
- combination_key identifies the outfit (outer+top+bottom sorted)
- Retention/bounce computed by duration-weighted aggregation across all qualifying clips
- Independent from single-garment metrics (video_color_metrics)
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.services.douyin_color_metrics_service import compute_outfit_metric
from app.services.douyin_color_outfit_service import build_combination_key


def _clip(clip_id, start_ms, end_ms, garment_position, style_id, color_id):
    return {
        "id": clip_id, "version": 1,
        "start_ms": start_ms, "end_ms": end_ms,
        "input_start_ms": start_ms, "input_end_ms": end_ms,
        "curve_resolution_ms": 1000,
        "focus_status": "clear_primary",
        "annotation_status": "approved",
        "overlap_status": "not_required",
        "style_id": style_id, "color_id": color_id,
        "garment_position": garment_position,
    }


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

    clips = [_clip(1, 0, 2000, "top", 10, 20)]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention([{"second": 0, "value": 0.5}]),
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is None


def test_compute_outfit_metric_aggregates_two_garments():
    """2-piece outfit (top+bottom) produces a metric with combination_key."""

    curve = [{"second": i, "value": 0.5 + i * 0.1} for i in range(6)]
    clips = [
        _clip(1, 0, 2000, "top", 10, 20),
        _clip(2, 3000, 5000, "bottom", 30, 40),
    ]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention(curve),
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None
    assert metric["participant_count"] == 2
    assert "top:10:20" in metric["combination_key"]
    assert "bottom:30:40" in metric["combination_key"]
    assert metric["retention_calculation_status"] == "computed"
    assert metric["average_retention"] is not None


def test_compute_outfit_metric_aggregates_three_garments():
    """3-piece outfit (outer+top+bottom) produces a metric."""

    curve = [{"second": i, "value": 0.5} for i in range(10)]
    clips = [
        _clip(1, 0, 2000, "outer", 100, 200),
        _clip(2, 3000, 5000, "top", 300, 400),
        _clip(3, 6000, 8000, "bottom", 500, 600),
    ]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention(curve),
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None
    assert metric["participant_count"] == 3
    assert metric["combination_key"] == "outer:100:200|top:300:400|bottom:500:600"


def test_compute_outfit_metric_excludes_none_position_clips():
    """Clips with garment_position=none don't count toward outfit participation."""

    curve = [{"second": i, "value": 0.5} for i in range(6)]
    clips = [
        _clip(1, 0, 2000, "top", 10, 20),
        _clip(2, 3000, 5000, "bottom", 30, 40),
        {**_clip(3, 6000, 8000, "none", 70, 80), "garment_position": "none"},
    ]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=_retention(curve),
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None
    assert metric["participant_count"] == 2  # none clip excluded


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
    clips = [
        _clip(1, 0, 2000, "top", 10, 20),
        _clip(2, 3000, 5000, "bottom", 30, 40),
    ]
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

    clips = [
        _clip(1, 0, 2000, "top", 10, 20),
        _clip(2, 3000, 5000, "bottom", 30, 40),
    ]
    metric = compute_outfit_metric(
        clips=clips, retention_snapshot=None,
        bounce_snapshot=None, video_duration_ms=10000,
        observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric is not None  # outfit exists but no data
    assert metric["retention_calculation_status"] == "insufficient_data"
    assert metric["average_retention"] is None
