"""Task 5: curve normalization, quality assessment, and clip-level integration.

Implements v3.1 §4.1:
- value_unit detection (ratio_0_1 / percent_0_100 / unknown)
- curve quality status
- clip average: arithmetic mean for uniform intervals, trapezoidal for non-uniform
- observation window resolution
- position segment resolution
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal


class CurveQualityError(ValueError):
    """A curve or clip violates v3.1 §4.1 quality requirements."""


ValueUnit = Literal["ratio_0_1", "percent_0_100", "unknown"]
CurveQualityStatus = Literal[
    "ok", "out_of_range", "non_monotonic_time", "duplicate_time",
    "missing_fields", "insufficient_curve_resolution", "empty",
]
ObservationWindow = Literal["t2", "t7", "t30", "ad_hoc"]
PositionSegment = Literal["front", "middle", "rear"]


def detect_value_unit(points: list[dict]) -> ValueUnit:
    """Detect whether curve values are 0..1 ratios or 0..100 percentages."""

    if not points:
        return "unknown"
    values = [p.get("value") for p in points if p.get("value") is not None]
    if len(values) != len(points) or not values:
        return "unknown"
    if all(0 <= v <= 1.0 for v in values):
        return "ratio_0_1"
    if all(1.0 < v <= 100.0 for v in values):
        return "percent_0_100"
    return "unknown"


def normalize_curve(points: list[dict], *, value_unit: str) -> list[dict]:
    """Normalize curve to 0..1. Rejects unknown units and out-of-range values."""

    if value_unit == "unknown":
        raise CurveQualityError("unknown_unit")
    if value_unit not in ("ratio_0_1", "percent_0_100"):
        raise CurveQualityError("unknown_unit")

    factor = 100.0 if value_unit == "percent_0_100" else 1.0
    normalized = []
    for p in points:
        raw = float(p["value"])
        val = raw / factor
        if not 0 <= val <= 1:
            raise CurveQualityError("out_of_range")
        normalized.append({"second": int(p["second"]), "value": val})
    normalized.sort(key=lambda p: p["second"])
    return normalized


def assess_curve_quality(points: list[dict]) -> CurveQualityStatus:
    """Assess curve quality per v3.1 §4.1: returns first detected issue or 'ok'."""

    if not points:
        return "empty"
    seconds = []
    for p in points:
        if "second" not in p or "value" not in p:
            return "missing_fields"
        seconds.append(int(p["second"]))
    # Check duplicate time
    if len(set(seconds)) != len(seconds):
        return "duplicate_time"
    # Check non-monotonic time
    if seconds != sorted(seconds):
        return "non_monotonic_time"
    # Check out of range (normalized 0..1)
    for p in points:
        val = float(p["value"])
        if not 0 <= val <= 1:
            return "out_of_range"
    return "ok"


def interpolate_value(v1: float, v2: float, t1: int, t2: int, target_t: int | float) -> float:
    """Linear interpolation between two points."""

    if t2 == t1:
        return v1
    ratio = (target_t - t1) / (t2 - t1)
    return v1 + (v2 - v1) * ratio


def compute_clip_average(curve: list[dict], *, start_ms: int, end_ms: int) -> Decimal:
    """Compute clip average: arithmetic for uniform, trapezoidal for non-uniform.

    Boundary points are linearly interpolated. If the nearest curve point is
    more than 1 second from a clip boundary, raises insufficient_curve_resolution.
    """

    if not curve or end_ms <= start_ms:
        raise CurveQualityError("invalid_clip_bounds")
    if start_ms < 0:
        raise CurveQualityError("invalid_clip_bounds")

    sorted_curve = sorted(curve, key=lambda p: int(p["second"]))
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0

    # Check resolution: nearest point to each boundary must be within 1 second
    first_second = sorted_curve[0]["second"]
    last_second = sorted_curve[-1]["second"]
    if abs(first_second - start_s) > 1.0 or abs(last_second - end_s) > 1.0:
        # Check if there are points close enough on the correct side
        points_before_start = [p for p in sorted_curve if p["second"] <= start_s]
        points_after_end = [p for p in sorted_curve if p["second"] >= end_s]
        if not points_before_start or abs(points_before_start[-1]["second"] - start_s) > 1.0:
            raise CurveQualityError("insufficient_curve_resolution")
        if not points_after_end or abs(points_after_end[0]["second"] - end_s) > 1.0:
            raise CurveQualityError("insufficient_curve_resolution")

    # Build effective curve points within [start_s, end_s] with interpolated boundaries
    effective_points = []
    for p in sorted_curve:
        s = p["second"]
        if start_s <= s <= end_s:
            effective_points.append((float(s), float(p["value"])))

    # Add interpolated boundary points if needed
    if not effective_points or effective_points[0][0] > start_s:
        # Interpolate at start_s
        idx = 0
        while idx < len(sorted_curve) and sorted_curve[idx]["second"] < start_s:
            idx += 1
        if idx == 0:
            v_start = float(sorted_curve[0]["value"])
        elif idx >= len(sorted_curve):
            v_start = float(sorted_curve[-1]["value"])
        else:
            p_before = sorted_curve[idx - 1]
            p_after = sorted_curve[idx]
            v_start = interpolate_value(
                float(p_before["value"]), float(p_after["value"]),
                p_before["second"], p_after["second"], start_s,
            )
        effective_points.insert(0, (start_s, v_start))

    if effective_points[-1][0] < end_s:
        # Interpolate at end_s
        idx = len(sorted_curve) - 1
        while idx >= 0 and sorted_curve[idx]["second"] > end_s:
            idx -= 1
        if idx >= len(sorted_curve) - 1:
            v_end = float(sorted_curve[-1]["value"])
        elif idx < 0:
            v_end = float(sorted_curve[0]["value"])
        else:
            p_before = sorted_curve[idx]
            p_after = sorted_curve[idx + 1]
            v_end = interpolate_value(
                float(p_before["value"]), float(p_after["value"]),
                p_before["second"], p_after["second"], end_s,
            )
        effective_points.append((end_s, v_end))

    # Remove points outside [start_s, end_s]
    effective_points = [(s, v) for s, v in effective_points if start_s <= s <= end_s]
    effective_points.sort(key=lambda x: x[0])

    if len(effective_points) < 2:
        return Decimal(str(effective_points[0][1])) if effective_points else Decimal("0")

    # Check if intervals are uniform (all diffs equal within 1ms tolerance)
    diffs = [effective_points[i + 1][0] - effective_points[i][0] for i in range(len(effective_points) - 1)]
    is_uniform = max(diffs) - min(diffs) < 0.001

    if is_uniform:
        # Arithmetic mean
        avg = sum(v for _, v in effective_points) / len(effective_points)
        return Decimal(str(avg))

    # Trapezoidal integration time-weighted average
    total_area = 0.0
    total_duration = 0.0
    for i in range(len(effective_points) - 1):
        s1, v1 = effective_points[i]
        s2, v2 = effective_points[i + 1]
        duration = s2 - s1
        area = (v1 + v2) / 2 * duration
        total_area += area
        total_duration += duration
    if total_duration == 0:
        return Decimal(str(effective_points[0][1]))
    avg = total_area / total_duration
    return Decimal(str(avg))


def resolve_observation_window(*, video_age_hours: Decimal | float | int) -> ObservationWindow:
    """Resolve observation window per v3.1 §2.3 age boundaries."""

    hours = float(video_age_hours)
    if 36 <= hours < 72:
        return "t2"
    if 144 <= hours < 216:
        return "t7"
    if 672 <= hours < 792:
        return "t30"
    return "ad_hoc"


def resolve_position_segment(*, clip_start_ms: int, video_duration_ms: int) -> PositionSegment:
    """Resolve position segment per v3.1 §4.1: front [0,1/3), middle [1/3,2/3), rear [2/3,1]."""

    if video_duration_ms <= 0:
        raise CurveQualityError("invalid_video_duration")
    ratio = clip_start_ms / video_duration_ms
    if ratio < 1 / 3:
        return "front"
    if ratio < 2 / 3:
        return "middle"
    return "rear"
