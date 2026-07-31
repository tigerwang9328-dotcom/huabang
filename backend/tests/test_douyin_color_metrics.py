"""Task 5: video-color metrics computation with independent snapshot selection.

Covers v3.1 §4.2 + v4.0 revised whole-outfit semantics:
- Independent retention/bounce snapshot selection (latest qualifying)
- metric_input_hash and annotation_set_hash computation (outfit_parts, no color)
- Per-garment metric derivation from outfit_parts (whole-outfit curve reused)
- Bounce stays platform_bounce_curve_value, never ranked until semantic verification
- v4.0 garment_position/sku_code split-ranking integration
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

def _hash_clip(clip_id, version=1, start_ms=0, end_ms=2000, parts=None, status="approved"):
    if parts is None:
        parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
    return {
        "id": clip_id, "version": version,
        "start_ms": start_ms, "end_ms": end_ms,
        "outfit_parts_json": parts,
        "annotation_status": status,
    }


def test_compute_annotation_set_hash_is_deterministic_and_order_independent():
    """annotation_set_hash must be stable regardless of clip input order."""

    clips_a = [
        _hash_clip(1, parts=[{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]),
        _hash_clip(2, parts=[{"position": "bottom", "style_id": 20, "sku_code": "WZ020-L"}]),
    ]
    clips_b = list(reversed(clips_a))
    assert compute_annotation_set_hash(clips_a) == compute_annotation_set_hash(clips_b)


def test_compute_annotation_set_hash_changes_when_clips_change():
    """Different clips produce different hashes."""

    clips_a = [_hash_clip(1, version=1)]
    clips_b = [_hash_clip(1, version=2)]
    assert compute_annotation_set_hash(clips_a) != compute_annotation_set_hash(clips_b)


def test_compute_annotation_set_hash_excludes_color_and_uses_sku_code():
    """v4.0: hash is driven by outfit_parts (position/style_id/sku_code), not color_id."""

    base_parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
    clip = _hash_clip(1, parts=base_parts)
    hash_with_sku = compute_annotation_set_hash([clip])

    # Changing sku_code changes the hash
    changed_sku = _hash_clip(1, parts=[{"position": "top", "style_id": 10, "sku_code": "WZ010-L"}])
    assert hash_with_sku != compute_annotation_set_hash([changed_sku])

    # outfit_parts_json order within a clip does not change the hash
    reordered = _hash_clip(1, parts=[
        {"position": "bottom", "style_id": 20, "sku_code": "WZ020-L"},
        {"position": "top", "style_id": 10, "sku_code": "WZ010-M"},
    ])
    same_set_diff_order = _hash_clip(1, parts=[
        {"position": "top", "style_id": 10, "sku_code": "WZ010-M"},
        {"position": "bottom", "style_id": 20, "sku_code": "WZ020-L"},
    ])
    assert compute_annotation_set_hash([reordered]) == compute_annotation_set_hash([same_set_diff_order])


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

def _make_qualifying_clip(*, clip_id, start_ms, end_ms, outfit_parts=None):
    if outfit_parts is None:
        outfit_parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
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
        "outfit_parts_json": outfit_parts,
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


def test_compute_video_color_metric_derives_one_metric_per_outfit_part():
    """v4.0: each garment in outfit_parts produces one metric dict."""

    curve = [
        {"second": 0, "value": 0.5},
        {"second": 1, "value": 0.7},
        {"second": 2, "value": 0.9},
    ]
    outfit_parts = [
        {"position": "top", "style_id": 10, "sku_code": "WZ010-M"},
        {"position": "bottom", "style_id": 30, "sku_code": "WZ030-L"},
    ]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=2000, outfit_parts=outfit_parts)]
    retention = _make_retention_snapshot(curve=curve)
    metrics = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts,
        retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert len(metrics) == 2
    positions = sorted(m["garment_position"] for m in metrics)
    assert positions == ["bottom", "top"]
    assert all(m["sku_code"] is not None for m in metrics)
    # both share the whole-outfit curve retention
    assert all(m["retention_calculation_status"] == "computed" for m in metrics)
    assert all(m["average_retention"] is not None for m in metrics)


def test_compute_video_color_metric_aggregates_single_clip():
    """Single qualifying clip produces a metric with average_retention from that clip."""

    curve = [
        {"second": 0, "value": 0.5},
        {"second": 1, "value": 0.7},
        {"second": 2, "value": 0.9},
    ]
    outfit_parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=2000, outfit_parts=outfit_parts)]
    retention = _make_retention_snapshot(curve=curve)
    metrics = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts,
        retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert len(metrics) == 1
    metric = metrics[0]
    assert metric["retention_calculation_status"] == "computed"
    assert metric["average_retention"] is not None
    assert metric["clip_count"] == 1
    assert metric["bounce_snapshot_id"] is None
    assert metric["bounce_calculation_status"] == "insufficient_data"
    assert metric["sku_code"] == "WZ010-M"


def test_compute_video_color_metric_aggregates_multiple_clips_by_duration():
    """Multiple qualifying clips aggregate by duration-weighted average (whole-outfit curve)."""

    curve = [
        {"second": 0, "value": 0.5},
        {"second": 1, "value": 0.7},
        {"second": 2, "value": 0.9},
        {"second": 3, "value": 0.6},
        {"second": 4, "value": 0.8},
        {"second": 5, "value": 0.4},
    ]
    outfit_parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
    clips = [
        _make_qualifying_clip(clip_id=1, start_ms=0, end_ms=2000, outfit_parts=outfit_parts),
        _make_qualifying_clip(clip_id=2, start_ms=3000, end_ms=5000, outfit_parts=outfit_parts),
    ]
    retention = _make_retention_snapshot(curve=curve)
    metrics = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts,
        retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    metric = metrics[0]
    assert metric["clip_count"] == 2
    assert metric["total_clip_duration_ms"] == 4000
    assert metric["retention_calculation_status"] == "computed"


def test_compute_video_color_metric_computes_bounce_when_semantics_verified():
    """Bounce computes only when semantics_status is verified_*_is_better."""

    curve = [{"second": 0, "value": 0.3}, {"second": 1, "value": 0.5}]
    outfit_parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000, outfit_parts=outfit_parts)]
    retention = _make_retention_snapshot(curve=curve)
    bounce = _make_bounce_snapshot(curve=curve)

    metrics_verified = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts, retention_snapshot=retention, bounce_snapshot=bounce,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="verified_lower_is_better",
    )
    metric_verified = metrics_verified[0]
    assert metric_verified["bounce_calculation_status"] == "computed"
    assert metric_verified["average_platform_bounce_curve_value"] is not None
    assert metric_verified["bounce_snapshot_id"] is not None

    metrics_unverified = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts, retention_snapshot=retention, bounce_snapshot=bounce,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    metric_unverified = metrics_unverified[0]
    # Bounce snapshot exists but semantics unverified -> bounce not ranked, stays as platform_bounce_curve_value
    assert metric_unverified["bounce_calculation_status"] == "computed"
    assert metric_unverified["average_platform_bounce_curve_value"] is not None


def test_compute_video_color_metric_excludes_non_qualifying_clips():
    """multi_focus, unclear, submitted, and pending_approval clips are excluded."""

    curve = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.7}]
    outfit_parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
    clips = [
        _make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000, outfit_parts=outfit_parts),
        {**_make_qualifying_clip(clip_id=2, start_ms=2000, end_ms=3000, outfit_parts=outfit_parts), "focus_status": "multi_focus"},
        {**_make_qualifying_clip(clip_id=3, start_ms=4000, end_ms=5000, outfit_parts=outfit_parts), "annotation_status": "submitted"},
        {**_make_qualifying_clip(clip_id=4, start_ms=6000, end_ms=7000, outfit_parts=outfit_parts), "overlap_status": "pending_approval"},
    ]
    retention = _make_retention_snapshot(curve=curve)
    metrics = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts, retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metrics[0]["clip_count"] == 1  # only clip 1 qualifies


def test_compute_video_color_metric_carries_garment_position_and_sku_per_part():
    """v4.0: each metric carries garment_position and sku_code from its outfit_part."""

    curve = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.7}]
    outfit_parts = [
        {"position": "outer", "style_id": 100, "sku_code": "WZ100-L"},
        {"position": "bottom", "style_id": 300, "sku_code": "WZ300-L"},
    ]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000, outfit_parts=outfit_parts)]
    retention = _make_retention_snapshot(curve=curve)
    metrics = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts, retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    by_pos = {m["garment_position"]: m for m in metrics}
    assert by_pos["outer"]["style_id"] == 100
    assert by_pos["outer"]["sku_code"] == "WZ100-L"
    assert by_pos["bottom"]["style_id"] == 300
    assert by_pos["bottom"]["sku_code"] == "WZ300-L"


def test_compute_video_color_metric_computes_position_segment():
    """dominant_position_segment is computed from the earliest clip start position."""

    curve = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.7}]
    # clip at 8000ms in a 10000ms video -> 0.8 -> rear
    outfit_parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=8000, end_ms=9000, outfit_parts=outfit_parts)]
    retention = _make_retention_snapshot(curve=curve)
    metrics = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts, retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metrics[0]["dominant_position_segment"] == "rear"


def test_compute_video_color_metric_returns_insufficient_data_when_no_retention():
    """No retention snapshot -> retention_calculation_status=insufficient_data."""

    outfit_parts = [{"position": "top", "style_id": 10, "sku_code": "WZ010-M"}]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000, outfit_parts=outfit_parts)]
    metrics = compute_video_color_metric(
        clips=clips, outfit_parts=outfit_parts, retention_snapshot=None, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metrics[0]["retention_calculation_status"] == "insufficient_data"
    assert metrics[0]["average_retention"] is None


def test_compute_video_color_metric_returns_empty_list_for_no_outfit_parts():
    """Empty outfit_parts -> empty list (no per-garment metrics)."""

    curve = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.7}]
    clips = [_make_qualifying_clip(clip_id=1, start_ms=0, end_ms=1000, outfit_parts=[])]
    retention = _make_retention_snapshot(curve=curve)
    metrics = compute_video_color_metric(
        clips=clips, outfit_parts=[], retention_snapshot=retention, bounce_snapshot=None,
        video_duration_ms=10000, observation_window="t7", metric_version="v1.0",
        bounce_semantics_status="unverified",
    )
    assert metrics == []
