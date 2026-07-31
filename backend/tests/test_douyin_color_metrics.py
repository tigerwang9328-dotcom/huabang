"""Task 5: video-color metrics computation with independent snapshot selection.

Covers v3.1 §4.2:
- Independent retention/bounce snapshot selection (latest qualifying)
- metric_input_hash and annotation_set_hash computation
- Multi-clip aggregation per video-color
- Bounce stays platform_bounce_curve_value, never ranked until semantic verification
- v4.0 garment_position split-ranking integration
"""

import hashlib
import json
from datetime import datetime, timezone

import pytest
from decimal import Decimal

from app.services.douyin_color_metrics_service import (
    MetricsCalculationError,
    compute_annotation_set_hash,
    compute_metric_input_hash,
    compute_video_color_metric,
    select_bounce_snapshot,
    select_retention_snapshot,
)


# --- snapshot selection ---

def _make_snapshot(*, snapshot_id, analysis_type, quality="ok", collected_at, status="success"):
    return {
        "id": snapshot_id,
        "analysis_type": analysis_type,
        "curve_quality_status": quality,
        "collected_at": collected_at,
        "item_status": status,
    }


def test_select_retention_snapshot_picks_latest_qualifying():
    """Retention snapshot = latest success + ok quality, analysis_type=1."""

    snapshots = [
        _make_snapshot(snapshot_id=1, analysis_type=1, collected_at=datetime(2026, 7, 1, tzinfo=timezone.utc)),
        _make_snapshot(snapshot_id=2, analysis_type=1, collected_at=datetime(2026, 7, 3, tzinfo=timezone.utc)),
        _make_snapshot(snapshot_id=3, analysis_type=1, collected_at=datetime(2026, 7, 2, tzinfo=timezone.utc)),
    ]
    selected = select_retention_snapshot(snapshots, source_data_cutoff_at=datetime(2026, 7, 10, tzinfo=timezone.utc))
    assert selected["id"] == 2  # latest


def test_select_retention_snapshot_excludes_non_qualifying():
    """Non-success or non-ok quality snapshots are excluded."""

    snapshots = [
        _make_snapshot(snapshot_id=1, analysis_type=1, quality="out_of_range", collected_at=datetime(2026, 7, 5, tzinfo=timezone.utc)),
        _make_snapshot(snapshot_id=2, analysis_type=1, status="rate_limited", collected_at=datetime(2026, 7, 4, tzinfo=timezone.utc)),
        _make_snapshot(snapshot_id=3, analysis_type=7, collected_at=datetime(2026, 7, 3, tzinfo=timezone.utc)),  # wrong type
        _make_snapshot(snapshot_id=4, analysis_type=1, collected_at=datetime(2026, 7, 2, tzinfo=timezone.utc)),
    ]
    selected = select_retention_snapshot(snapshots, source_data_cutoff_at=datetime(2026, 7, 10, tzinfo=timezone.utc))
    assert selected["id"] == 4


def test_select_retention_snapshot_respects_source_data_cutoff():
    """Snapshots collected after source_data_cutoff_at are excluded."""

    cutoff = datetime(2026, 7, 3, tzinfo=timezone.utc)
    snapshots = [
        _make_snapshot(snapshot_id=1, analysis_type=1, collected_at=datetime(2026, 7, 2, tzinfo=timezone.utc)),
        _make_snapshot(snapshot_id=2, analysis_type=1, collected_at=datetime(2026, 7, 4, tzinfo=timezone.utc)),  # after cutoff
    ]
    selected = select_retention_snapshot(snapshots, source_data_cutoff_at=cutoff)
    assert selected["id"] == 1


def test_select_retention_snapshot_returns_none_when_no_qualifying():
    """Returns None when no qualifying snapshot exists (retention still computes with None bounce)."""

    snapshots = []
    selected = select_retention_snapshot(snapshots, source_data_cutoff_at=datetime(2026, 7, 10, tzinfo=timezone.utc))
    assert selected is None


def test_select_bounce_snapshot_independent_from_retention():
    """Bounce snapshot selects analysis_type=7 independently."""

    snapshots = [
        _make_snapshot(snapshot_id=10, analysis_type=7, collected_at=datetime(2026, 7, 3, tzinfo=timezone.utc)),
        _make_snapshot(snapshot_id=11, analysis_type=7, collected_at=datetime(2026, 7, 5, tzinfo=timezone.utc)),
        _make_snapshot(snapshot_id=12, analysis_type=1, collected_at=datetime(2026, 7, 6, tzinfo=timezone.utc)),  # wrong type
    ]
    selected = select_bounce_snapshot(snapshots, source_data_cutoff_at=datetime(2026, 7, 10, tzinfo=timezone.utc))
    assert selected["id"] == 11


def test_select_bounce_snapshot_returns_none_when_missing():
    """No bounce snapshot -> bounce_snapshot_id=NULL, bounce_calculation_status=insufficient_data."""

    selected = select_bounce_snapshot([], source_data_cutoff_at=datetime(2026, 7, 10, tzinfo=timezone.utc))
    assert selected is None


# --- hash computation ---

def test_compute_annotation_set_hash_is_deterministic_and_order_independent():
    """annotation_set_hash must be stable regardless of clip input order."""

    clips_a = [
        {"id": 1, "version": 1, "start_ms": 0, "end_ms": 2000, "style_id": 10, "color_id": 20, "annotation_status": "approved"},
        {"id": 2, "version": 1, "start_ms": 3000, "end_ms": 5000, "style_id": 10, "color_id": 20, "annotation_status": "approved"},
    ]
    clips_b = list(reversed(clips_a))
    assert compute_annotation_set_hash(clips_a) == compute_annotation_set_hash(clips_b)


def test_compute_annotation_set_hash_changes_when_clips_change():
    """Different clips produce different hashes."""

    clips_a = [{"id": 1, "version": 1, "start_ms": 0, "end_ms": 2000, "style_id": 10, "color_id": 20, "annotation_status": "approved"}]
    clips_b = [{"id": 1, "version": 2, "start_ms": 0, "end_ms": 2000, "style_id": 10, "color_id": 20, "annotation_status": "approved"}]
    assert compute_annotation_set_hash(clips_a) != compute_annotation_set_hash(clips_b)


def test_compute_metric_input_hash_is_deterministic():
    """metric_input_hash must be stable for the same inputs."""

    hash1 = compute_metric_input_hash(
        retention_source_hash="abc123",
        bounce_source_hash="def456",
        annotation_set_hash="ghi789",
        observation_window="t7",
        metric_version="v1.0",
    )
    hash2 = compute_metric_input_hash(
        retention_source_hash="abc123",
        bounce_source_hash="def456",
        annotation_set_hash="ghi789",
        observation_window="t7",
        metric_version="v1.0",
    )
    assert hash1 == hash2


def test_compute_metric_input_hash_changes_when_bounce_changes():
    """Changing bounce snapshot produces a different metric_input_hash."""

    hash_with_bounce = compute_metric_input_hash(
        retention_source_hash="abc123",
        bounce_source_hash="def456",
        annotation_set_hash="ghi789",
        observation_window="t7",
        metric_version="v1.0",
    )
    hash_without_bounce = compute_metric_input_hash(
        retention_source_hash="abc123",
        bounce_source_hash=None,
        annotation_set_hash="ghi789",
        observation_window="t7",
        metric_version="v1.0",
    )
    assert hash_with_bounce != hash_without_bounce


# --- video-color metric computation ---

def _make_qualifying_clip(*, clip_id, start_ms, end_ms, style_id=10, color_id=20):
    return {
        "id": clip_id,
        "version": 1,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "input_start_ms": start_ms,
        "input_end_ms": end_ms,
        "curve_resolution_ms": 1000,
        "focus_status": "clear_primary",
        "annotation_status": "approved",
        "overlap_status": "not_required",
        "style_id": style_id,
        "color_id": color_id,
        "garment_position": "top",
    }


def _make_retention_snapshot(*, curve, snapshot_id=1, source_hash="ret_hash_1"):
    return {
        "id": snapshot_id,
        "analysis_type": 1,
        "curve_quality_status": "ok",
        "item_status": "success",
        "collected_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "normalized_curve_json": curve,
        "source_snapshot_hash": source_hash,
        "video_age_hours_at_collection": Decimal("150"),
    }


def _make_bounce_snapshot(*, curve, snapshot_id=2, source_hash="bounce_hash_1"):
    return {
        "id": snapshot_id,
        "analysis_type": 7,
        "curve_quality_status": "ok",
        "item_status": "success",
        "collected_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "normalized_curve_json": curve,
        "source_snapshot_hash": source_hash,
    }


def test_compute_video_color_metric_aggregates_single_clip():
    """Single qualifying clip produces a metric with average_retention from that clip."""

    curve = [
        {"second": 0, "value": 0.5},
        {"second": 1, "value": 0.7},
        {"second": 2, "value": 0.9},
    ]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=2000)]
    retention = _make_retention_snapshot(curve=curve)
    metric = compute_video_color_metric(
        clips=clips,
        retention_snapshot=retention,
        bounce_snapshot=None,
        video_duration_ms=10000,
        observation_window="t7",
        metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric["retention_calculation_status"] == "computed"
    assert metric["average_retention"] is not None
    assert metric["clip_count"] == 1
    assert metric["bounce_snapshot_id"] is None
    assert metric["bounce_calculation_status"] == "insufficient_data"


def test_compute_video_color_metric_aggregates_multiple_clips_by_duration():
    """Multiple qualifying clips aggregate by duration-weighted average."""

    curve = [
        {"second": 0, "value": 0.5},
        {"second": 1, "value": 0.7},
        {"second": 2, "value": 0.9},
        {"second": 3, "value": 0.6},
        {"second": 4, "value": 0.8},
        {"second": 5, "value": 0.4},
    ]
    clips = [
        _make_qualifying_clip(clip_id=1, start_ms=0, end_ms=2000),
        _make_qualifying_clip(clip_id=2, start_ms=3000, end_ms=5000),
    ]
    retention = _make_retention_snapshot(curve=curve)
    metric = compute_video_color_metric(
        clips=clips,
        retention_snapshot=retention,
        bounce_snapshot=None,
        video_duration_ms=10000,
        observation_window="t7",
        metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric["clip_count"] == 2
    assert metric["total_clip_duration_ms"] == 4000
    assert metric["retention_calculation_status"] == "computed"


def test_compute_video_color_metric_computes_bounce_when_semantics_verified():
    """Bounce computes only when semantics_status is verified_*_is_better."""

    curve = [{"second": 0, "value": 0.3}, {"second": 1, "value": 0.5}]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000)]
    retention = _make_retention_snapshot(curve=curve)
    bounce = _make_bounce_snapshot(curve=curve)

    metric_verified = compute_video_color_metric(
        clips=clips, retention_snapshot=retention, bounce_snapshot=bounce,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="verified_lower_is_better",
    )
    assert metric_verified["bounce_calculation_status"] == "computed"
    assert metric_verified["average_platform_bounce_curve_value"] is not None
    assert metric_verified["bounce_snapshot_id"] is not None

    metric_unverified = compute_video_color_metric(
        clips=clips, retention_snapshot=retention, bounce_snapshot=bounce,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    # Bounce snapshot exists but semantics unverified -> bounce not ranked, stays as platform_bounce_curve_value
    assert metric_unverified["bounce_calculation_status"] == "computed"
    assert metric_unverified["average_platform_bounce_curve_value"] is not None


def test_compute_video_color_metric_excludes_non_qualifying_clips():
    """multi_focus, unclear, submitted, and pending_approval clips are excluded."""

    curve = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.7}]
    clips = [
        _make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000),
        {**_make_qualifying_clip(clip_id=2, start_ms=2000, end_ms=3000), "focus_status": "multi_focus"},
        {**_make_qualifying_clip(clip_id=3, start_ms=4000, end_ms=5000), "annotation_status": "submitted"},
        {**_make_qualifying_clip(clip_id=4, start_ms=6000, end_ms=7000), "overlap_status": "pending_approval"},
    ]
    retention = _make_retention_snapshot(curve=curve)
    metric = compute_video_color_metric(
        clips=clips, retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric["clip_count"] == 1  # only clip 1 qualifies


def test_compute_video_color_metric_includes_garment_position_for_split_ranking():
    """v4.0: metric includes garment_position for split-ranking bucket assignment."""

    curve = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.7}]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000)]
    clips[0]["garment_position"] = "bottom"
    retention = _make_retention_snapshot(curve=curve)
    metric = compute_video_color_metric(
        clips=clips, retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric["garment_position"] == "bottom"


def test_compute_video_color_metric_computes_position_segment():
    """dominant_position_segment is computed from clip start position."""

    curve = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.7}]
    # clip at 8000ms in a 10000ms video -> 0.8 -> rear
    clips = [_make_qualifying_clip(clip_id=1, start_ms=8000, end_ms=9000)]
    retention = _make_retention_snapshot(curve=curve)
    metric = compute_video_color_metric(
        clips=clips, retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric["dominant_position_segment"] == "rear"


def test_compute_video_color_metric_returns_insufficient_data_when_no_retention():
    """No retention snapshot -> retention_calculation_status=insufficient_data."""

    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000)]
    metric = compute_video_color_metric(
        clips=clips, retention_snapshot=None, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metric["retention_calculation_status"] == "insufficient_data"
    assert metric["average_retention"] is None
