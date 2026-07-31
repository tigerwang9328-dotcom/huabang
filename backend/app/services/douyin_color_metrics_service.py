"""Task 5: video-color metrics with independent retention/bounce snapshot selection.

Implements v3.1 §4.2 + v4.0 revised whole-outfit semantics:
- Independent snapshot selection (retention=type 1, bounce=type 7)
- metric_input_hash and annotation_set_hash
- Multi-clip duration-weighted aggregation over the whole-outfit curve
- Bounce stays platform_bounce_curve_value until semantics verified
- v4.0: one curve (clip) maps to one whole outfit (>=2 garments).
  compute_video_color_metric derives one per-garment metric per outfit_part,
  reusing the whole-outfit curve (no time-segment splitting).
  combination_key excludes color_id; garments are distinguished by SKU.
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


def _canonical_outfit_part(part: dict) -> dict:
    """Normalise an outfit part for hashing (position/style_id/sku_code only)."""

    return {
        "position": part.get("position") or part.get("garment_position"),
        "style_id": part.get("style_id"),
        "sku_code": part.get("sku_code"),
    }


def compute_annotation_set_hash(clips: list[dict]) -> str:
    """Hash of participating clip IDs, versions, bounds, outfit_parts, status.

    Order-independent: clips are sorted by ID, outfit_parts by (position, style_id,
    sku_code) before hashing.

    v4.0: outfit_parts_json (position, style_id, sku_code) replaces the single
    style_id/color_id pair. Color no longer participates in the hash.
    """

    canonical_clips = sorted(
        [
            {
                "id": c["id"],
                "version": c["version"],
                "start_ms": c["start_ms"],
                "end_ms": c["end_ms"],
                "outfit_parts": sorted(
                    [_canonical_outfit_part(p) for p in (c.get("outfit_parts_json") or [])],
                    key=lambda p: (
                        p["position"] or "",
                        p["style_id"] if p["style_id"] is not None else -1,
                        p["sku_code"] or "",
                    ),
                ),
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
    """A clip qualifies for metric computation if clear_primary+approved+overlap ok.

    v4.0: clear_primary means a whole outfit is clearly visible.
    """

    return (
        clip.get("focus_status") == "clear_primary"
        and clip.get("annotation_status") == "approved"
        and clip.get("overlap_status") in _QUALIFYING_OVERLAP
    )


def _compute_curve_base(
    *,
    clips: list[dict],
    retention_snapshot: dict | None,
    bounce_snapshot: dict | None,
    video_duration_ms: int,
    observation_window: str,
    metric_version: str,
) -> dict:
    """Compute shared retention/bounce fields from qualifying clips.

    The whole-outfit curve is aggregated across all qualifying clips via
    duration-weighted averaging. This base is shared by every per-garment
    video_color_metric and by the outfit_color_metric.
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

    # Position segment from earliest qualifying clip (whole-outfit curve anchor)
    dominant_position_segment = None
    if qualifying_clips:
        first_clip = min(qualifying_clips, key=lambda c: c["start_ms"])
        try:
            dominant_position_segment = resolve_position_segment(
                clip_start_ms=first_clip["start_ms"],
                video_duration_ms=video_duration_ms,
            )
        except CurveQualityError:
            dominant_position_segment = None

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
        "retention_drop": None,  # computed at report level across outfits
        "average_platform_bounce_curve_value": average_platform_bounce_curve_value,
        "max_platform_bounce_curve_value": max_platform_bounce_curve_value,
        "dominant_position_segment": dominant_position_segment,
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


def compute_video_color_metric(
    *,
    clips: list[dict],
    outfit_parts: list[dict],
    retention_snapshot: dict | None,
    bounce_snapshot: dict | None,
    video_duration_ms: int,
    observation_window: str,
    metric_version: str,
    bounce_semantics_status: str,
) -> list[dict]:
    """Derive per-garment video_color_metric dicts from outfit_parts.

    v4.0: one curve (clip) maps to one whole outfit. Each garment in
    ``outfit_parts`` produces one metric dict carrying garment_position,
    style_id and sku_code. The curve is the whole-outfit curve (shared across
    garments, not split by time segment).

    Returns a list of dicts (one per garment). When ``outfit_parts`` is empty
    an empty list is returned. Bounce is always computed as
    platform_bounce_curve_value when a bounce snapshot exists; ranking
    eligibility is gated by bounce_semantics_status elsewhere.
    """

    base = _compute_curve_base(
        clips=clips,
        retention_snapshot=retention_snapshot,
        bounce_snapshot=bounce_snapshot,
        video_duration_ms=video_duration_ms,
        observation_window=observation_window,
        metric_version=metric_version,
    )

    metrics: list[dict] = []
    for part in outfit_parts:
        metric = dict(base)
        metric["garment_position"] = (
            part.get("position") or part.get("garment_position") or "none"
        )
        metric["style_id"] = part.get("style_id")
        metric["sku_code"] = part.get("sku_code")
        metrics.append(metric)
    return metrics


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
    """Compute the outfit-level metric (main v4.0 metric entry).

    Returns None if fewer than 2 qualifying garments exist. Aggregation is
    duration-weighted across all qualifying clips (the whole-outfit curve).
    combination_key excludes color_id; garments are distinguished by SKU.
    """

    participants = derive_outfit_participants(clips)
    if len(participants) < 2:
        return None

    try:
        combination_key = build_combination_key(participants)
    except OutfitCompositionError:
        return None

    base = _compute_curve_base(
        clips=clips,
        retention_snapshot=retention_snapshot,
        bounce_snapshot=bounce_snapshot,
        video_duration_ms=video_duration_ms,
        observation_window=observation_window,
        metric_version=metric_version,
    )

    # Override fields for outfit-level metric
    base["combination_key"] = combination_key
    base["participant_count"] = len(participants)
    # Remove single-garment specific fields not in outfit_color_metrics
    base.pop("clip_count", None)
    base.pop("style_id", None)
    base.pop("color_id", None)
    base.pop("video_id", None)
    base.pop("garment_position", None)
    base.pop("sku_code", None)

    return base
