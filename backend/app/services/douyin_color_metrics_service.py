"""Task 5: video-color metrics with independent retention/bounce snapshot selection.

Implements v3.1 §4.2:
- Independent snapshot selection (retention=type 1, bounce=type 7)
- metric_input_hash and annotation_set_hash
- Multi-clip duration-weighted aggregation
- Bounce stays platform_bounce_curve_value until semantics verified
- v4.0 garment_position passthrough for split-ranking
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.services.douyin_color_outfit_service import (
    OutfitCompositionError,
    build_combination_key,
    derive_outfit_participants,
)
from app.services.douyin_color_curve_service import (
    CurveQualityError,
    compute_clip_average,
    resolve_observation_window,
    resolve_position_segment,
)


class MetricsCalculationError(ValueError):
    """A metrics calculation request violates v3.1 §4.2."""


_QUALIFYING_OVERLAP = {"not_required", "approved"}
_VERIFIED_BOUNCE_STATUSES = {"verified_lower_is_better", "verified_higher_is_better"}


def _is_qualifying_snapshot(snap: dict, *, analysis_type: int, cutoff: datetime | None) -> bool:
    """A snapshot qualifies if success + ok quality + correct type + before cutoff."""

    if snap.get("analysis_type") != analysis_type:
        return False
    if snap.get("item_status") != "success":
        return False
    if snap.get("curve_quality_status") != "ok":
        return False
    if cutoff is not None and snap.get("collected_at") is not None:
        if snap["collected_at"] > cutoff:
            return False
    return True


def select_retention_snapshot(
    snapshots: list[dict], *, source_data_cutoff_at: datetime | None
) -> dict | None:
    """Select the latest qualifying retention snapshot (analysis_type=1)."""

    qualifying = [
        s for s in snapshots
        if _is_qualifying_snapshot(s, analysis_type=1, cutoff=source_data_cutoff_at)
    ]
    if not qualifying:
        return None
    return max(qualifying, key=lambda s: s.get("collected_at") or datetime.min.replace(tzinfo=None))


def select_bounce_snapshot(
    snapshots: list[dict], *, source_data_cutoff_at: datetime | None
) -> dict | None:
    """Select the latest qualifying bounce snapshot (analysis_type=7), independently."""

    qualifying = [
        s for s in snapshots
        if _is_qualifying_snapshot(s, analysis_type=7, cutoff=source_data_cutoff_at)
    ]
    if not qualifying:
        return None
    return max(qualifying, key=lambda s: s.get("collected_at") or datetime.min.replace(tzinfo=None))


def _canonical_json(obj: Any) -> str:
    """Canonical JSON for hashing: sorted keys, no extra whitespace, UTF-8."""

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def compute_annotation_set_hash(clips: list[dict]) -> str:
    """Hash of participating clip IDs, versions, bounds, style/color, status.

    Order-independent: clips are sorted by ID before hashing.
    """

    canonical_clips = sorted(
        [
            {
                "id": c["id"],
                "version": c["version"],
                "start_ms": c["start_ms"],
                "end_ms": c["end_ms"],
                "style_id": c["style_id"],
                "color_id": c["color_id"],
                "annotation_status": c["annotation_status"],
            }
            for c in clips
        ],
        key=lambda c: c["id"],
    )
    payload = _canonical_json(canonical_clips)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_metric_input_hash(
    *,
    retention_source_hash: str | None,
    bounce_source_hash: str | None,
    annotation_set_hash: str,
    observation_window: str,
    metric_version: str,
) -> str:
    """Hash of all metric inputs. Changes when any input changes."""

    payload = _canonical_json({
        "retention_source_hash": retention_source_hash,
        "bounce_source_hash": bounce_source_hash,
        "annotation_set_hash": annotation_set_hash,
        "observation_window": observation_window,
        "metric_version": metric_version,
    })
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_qualifying_clip(clip: dict) -> bool:
    """A clip qualifies for metric computation if clear_primary+approved+overlap ok."""

    return (
        clip.get("focus_status") == "clear_primary"
        and clip.get("annotation_status") == "approved"
        and clip.get("overlap_status") in _QUALIFYING_OVERLAP
    )


def compute_video_color_metric(
    *,
    clips: list[dict],
    retention_snapshot: dict | None,
    bounce_snapshot: dict | None,
    video_duration_ms: int,
    observation_window: str,
    metric_version: str,
    bounce_semantics_status: str,
) -> dict:
    """Compute a single video-color metric from clips and independent snapshots.

    Returns a dict with all VideoColorMetric fields ready for persistence.
    Bounce is always computed as platform_bounce_curve_value when a bounce snapshot
    exists; ranking eligibility is gated by bounce_semantics_status elsewhere.
    """

    qualifying_clips = [c for c in clips if _is_qualifying_clip(c)]
    annotation_set_hash = compute_annotation_set_hash(qualifying_clips) if qualifying_clips else ""

    retention_source_hash = retention_snapshot.get("source_snapshot_hash") if retention_snapshot else None
    bounce_source_hash = bounce_snapshot.get("source_snapshot_hash") if bounce_snapshot else None

    metric_input_hash = compute_metric_input_hash(
        retention_source_hash=retention_source_hash,
        bounce_source_hash=bounce_source_hash,
        annotation_set_hash=annotation_set_hash,
        observation_window=observation_window,
        metric_version=metric_version,
    )

    # Position segment from first qualifying clip
    dominant_position_segment = None
    garment_position = "none"
    if qualifying_clips:
        first_clip = min(qualifying_clips, key=lambda c: c["start_ms"])
        try:
            dominant_position_segment = resolve_position_segment(
                clip_start_ms=first_clip["start_ms"],
                video_duration_ms=video_duration_ms,
            )
        except CurveQualityError:
            dominant_position_segment = None
        garment_position = first_clip.get("garment_position", "none")

    total_clip_duration_ms = sum(c["end_ms"] - c["start_ms"] for c in qualifying_clips)

    # Retention calculation
    average_retention = None
    retention_calculation_status = "pending"
    if retention_snapshot is None:
        retention_calculation_status = "insufficient_data"
    elif not qualifying_clips:
        retention_calculation_status = "insufficient_data"
    else:
        curve = retention_snapshot.get("normalized_curve_json") or []
        if not curve:
            retention_calculation_status = "insufficient_data"
        else:
            try:
                weighted_sum = Decimal("0")
                for clip in qualifying_clips:
                    clip_avg = compute_clip_average(
                        curve, start_ms=clip["start_ms"], end_ms=clip["end_ms"]
                    )
                    clip_duration = Decimal(str(clip["end_ms"] - clip["start_ms"]))
                    weighted_sum += clip_avg * clip_duration
                average_retention = weighted_sum / Decimal(str(total_clip_duration_ms)) if total_clip_duration_ms > 0 else None
                retention_calculation_status = "computed"
            except CurveQualityError:
                retention_calculation_status = "failed"

    # Bounce calculation (always platform_bounce_curve_value, never "bounce rate")
    average_platform_bounce_curve_value = None
    max_platform_bounce_curve_value = None
    bounce_calculation_status = "pending"
    if bounce_snapshot is None:
        bounce_calculation_status = "insufficient_data"
    elif not qualifying_clips:
        bounce_calculation_status = "insufficient_data"
    else:
        curve = bounce_snapshot.get("normalized_curve_json") or []
        if not curve:
            bounce_calculation_status = "insufficient_data"
        else:
            try:
                weighted_sum = Decimal("0")
                max_val = Decimal("0")
                for clip in qualifying_clips:
                    clip_avg = compute_clip_average(
                        curve, start_ms=clip["start_ms"], end_ms=clip["end_ms"]
                    )
                    clip_duration = Decimal(str(clip["end_ms"] - clip["start_ms"]))
                    weighted_sum += clip_avg * clip_duration
                    if clip_avg > max_val:
                        max_val = clip_avg
                average_platform_bounce_curve_value = (
                    weighted_sum / Decimal(str(total_clip_duration_ms))
                    if total_clip_duration_ms > 0 else None
                )
                max_platform_bounce_curve_value = max_val
                bounce_calculation_status = "computed"
            except CurveQualityError:
                bounce_calculation_status = "failed"

    return {
        "clip_count": len(qualifying_clips),
        "total_clip_duration_ms": total_clip_duration_ms,
        "average_retention": average_retention,
        "retention_drop": None,  # computed at report level across colors
        "average_platform_bounce_curve_value": average_platform_bounce_curve_value,
        "max_platform_bounce_curve_value": max_platform_bounce_curve_value,
        "dominant_position_segment": dominant_position_segment,
        "garment_position": garment_position,
        "retention_calculation_status": retention_calculation_status,
        "bounce_calculation_status": bounce_calculation_status,
        "retention_snapshot_id": retention_snapshot.get("id") if retention_snapshot else None,
        "bounce_snapshot_id": bounce_snapshot.get("id") if bounce_snapshot else None,
        "retention_source_hash": retention_source_hash,
        "bounce_source_hash": bounce_source_hash,
        "annotation_set_hash": annotation_set_hash,
        "metric_input_hash": metric_input_hash,
        "metric_version": metric_version,
        "video_duration_ms": video_duration_ms,
        "calculated_at": datetime.now(timezone.utc),
    }

def compute_outfit_metric(
    *,
    clips: list[dict],
    retention_snapshot: dict | None,
    bounce_snapshot: dict | None,
    video_duration_ms: int,
    observation_window: str,
    metric_version: str,
    bounce_semantics_status: str,
) -> dict | None:
    """Compute outfit-level metric from >=2 qualifying garments.

    Returns None if fewer than 2 qualifying garments exist.
    Aggregation is duration-weighted across all qualifying clips (cross-garment).
    """

    participants = derive_outfit_participants(clips)
    if len(participants) < 2:
        return None

    try:
        combination_key = build_combination_key(participants)
    except OutfitCompositionError:
        return None

    # Reuse the single-garment metric computation but override key fields
    base_metric = compute_video_color_metric(
        clips=clips,
        retention_snapshot=retention_snapshot,
        bounce_snapshot=bounce_snapshot,
        video_duration_ms=video_duration_ms,
        observation_window=observation_window,
        metric_version=metric_version,
        bounce_semantics_status=bounce_semantics_status,
    )

    # Override fields for outfit-level metric
    base_metric["combination_key"] = combination_key
    base_metric["participant_count"] = len(participants)
    # Remove single-garment specific fields not in outfit_color_metrics
    base_metric.pop("style_id", None)
    base_metric.pop("color_id", None)
    base_metric.pop("video_id", None)
    base_metric.pop("garment_position", None)
    base_metric.pop("dominant_position_segment", None)

    return base_metric
