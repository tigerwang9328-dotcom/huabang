"""Task 5: curve normalization, quality assessment, and clip-level integration.

Covers v3.1 §4.1:
- value_unit detection (ratio_0_1 / percent_0_100 / unknown)
- curve quality status (out_of_range, non_monotonic_time, duplicate_time, missing_fields, insufficient_curve_resolution)
- clip average: arithmetic mean for uniform intervals, trapezoidal for non-uniform
- observation window resolution (t2/t7/t30/ad_hoc)
- position segment (front/middle/rear)
"""

import pytest
from decimal import Decimal

from app.services.douyin_color_curve_service import (
    CurveQualityError,
    assess_curve_quality,
    compute_clip_average,
    detect_value_unit,
    interpolate_value,
    normalize_curve,
    resolve_observation_window,
    resolve_position_segment,
)


# --- value unit detection ---

def test_detect_value_unit_recognizes_ratio_0_1():
    points = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.8}, {"second": 2, "value": 0.3}]
    assert detect_value_unit(points) == "ratio_0_1"


def test_detect_value_unit_recognizes_percent_0_100():
    points = [{"second": 0, "value": 50.0}, {"second": 1, "value": 80.0}, {"second": 2, "value": 30.0}]
    assert detect_value_unit(points) == "percent_0_100"


def test_detect_value_unit_returns_unknown_for_mixed_signals():
    points = [{"second": 0, "value": 1.5}, {"second": 1, "value": 150.0}]
    assert detect_value_unit(points) == "unknown"


def test_detect_value_unit_returns_unknown_for_empty_curve():
    assert detect_value_unit([]) == "unknown"


# --- curve normalization ---

def test_normalize_curve_converts_percent_to_0_1():
    points = [{"second": 0, "value": 50.0}, {"second": 1, "value": 80.0}]
    normalized = normalize_curve(points, value_unit="percent_0_100")
    assert normalized == [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.8}]


def test_normalize_curve_passes_ratio_through_unchanged():
    points = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.8}]
    normalized = normalize_curve(points, value_unit="ratio_0_1")
    assert normalized == [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.8}]


def test_normalize_curve_rejects_unknown_unit():
    points = [{"second": 0, "value": 0.5}]
    with pytest.raises(CurveQualityError, match="unknown_unit"):
        normalize_curve(points, value_unit="unknown")


def test_normalize_curve_rejects_out_of_range_after_conversion():
    points = [{"second": 0, "value": 150.0}]  # 150% -> 1.5 > 1
    with pytest.raises(CurveQualityError, match="out_of_range"):
        normalize_curve(points, value_unit="percent_0_100")


# --- curve quality assessment ---

def test_assess_curve_quality_rejects_non_monotonic_time():
    points = [{"second": 0, "value": 0.5}, {"second": 2, "value": 0.8}, {"second": 1, "value": 0.3}]
    status = assess_curve_quality(points)
    assert status == "non_monotonic_time"


def test_assess_curve_quality_rejects_duplicate_time():
    points = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.8}, {"second": 1, "value": 0.3}]
    status = assess_curve_quality(points)
    assert status == "duplicate_time"


def test_assess_curve_quality_rejects_out_of_range_values():
    points = [{"second": 0, "value": 1.5}, {"second": 1, "value": 0.8}]
    status = assess_curve_quality(points)
    assert status == "out_of_range"


def test_assess_curve_quality_returns_ok_for_valid_curve():
    points = [{"second": 0, "value": 0.5}, {"second": 1, "value": 0.8}, {"second": 2, "value": 0.3}]
    status = assess_curve_quality(points)
    assert status == "ok"


def test_assess_curve_quality_rejects_missing_fields():
    points = [{"second": 0}, {"second": 1, "value": 0.8}]
    status = assess_curve_quality(points)
    assert status == "missing_fields"


# --- clip average computation ---

def test_compute_clip_average_uses_arithmetic_mean_for_uniform_intervals():
    curve = [
        {"second": 0, "value": 0.5},
        {"second": 1, "value": 0.7},
        {"second": 2, "value": 0.9},
    ]
    avg = compute_clip_average(curve, start_ms=0, end_ms=2000)
    assert abs(float(avg) - 0.7) < 1e-6


def test_compute_clip_average_uses_trapezoidal_for_non_uniform_intervals():
    curve = [
        {"second": 0, "value": 0.0},
        {"second": 1, "value": 1.0},
        {"second": 3, "value": 1.0},
    ]
    # intervals: [0,1] trapezoid = 0.5*1 = 0.5; [1,3] trapezoid = 1.0*2 = 2.0
    # total = 2.5, duration = 3, avg = 2.5/3
    avg = compute_clip_average(curve, start_ms=0, end_ms=3000)
    assert abs(float(avg) - (2.5 / 3.0)) < 1e-6


def test_compute_clip_average_interpolates_at_boundaries():
    curve = [
        {"second": 0, "value": 0.0},
        {"second": 2, "value": 1.0},
    ]
    # clip [500ms, 1500ms], interpolate at 0.5s = 0.25, at 1.5s = 0.75
    # trapezoid = (0.25 + 0.75) / 2 * 1 = 0.5, duration = 1, avg = 0.5
    avg = compute_clip_average(curve, start_ms=500, end_ms=1500)
    assert abs(float(avg) - 0.5) < 1e-6


def test_compute_clip_average_returns_insufficient_resolution_when_gap_exceeds_1s():
    curve = [
        {"second": 0, "value": 0.5},
        {"second": 5, "value": 0.8},
    ]
    # clip [1000ms, 2000ms], nearest point at 0s is 1s away from 1000ms boundary -> ok
    # but nearest point at 5s is 3s away from 2000ms boundary -> insufficient
    with pytest.raises(CurveQualityError, match="insufficient_curve_resolution"):
        compute_clip_average(curve, start_ms=1000, end_ms=2000)


# --- interpolation ---

def test_interpolate_value_linear_between_two_points():
    assert abs(interpolate_value(0.0, 1.0, 0, 2, 1) - 0.5) < 1e-6
    assert abs(interpolate_value(0.0, 1.0, 0, 2, 0) - 0.0) < 1e-6
    assert abs(interpolate_value(0.0, 1.0, 0, 2, 2) - 1.0) < 1e-6


# --- observation window ---

def test_resolve_observation_window_t2():
    assert resolve_observation_window(video_age_hours=Decimal("48")) == "t2"
    assert resolve_observation_window(video_age_hours=Decimal("36")) == "t2"
    assert resolve_observation_window(video_age_hours=Decimal("71.9")) == "t2"


def test_resolve_observation_window_t7():
    assert resolve_observation_window(video_age_hours=Decimal("144")) == "t7"
    assert resolve_observation_window(video_age_hours=Decimal("200")) == "t7"
    assert resolve_observation_window(video_age_hours=Decimal("215.9")) == "t7"


def test_resolve_observation_window_t30():
    assert resolve_observation_window(video_age_hours=Decimal("672")) == "t30"
    assert resolve_observation_window(video_age_hours=Decimal("700")) == "t30"
    assert resolve_observation_window(video_age_hours=Decimal("791.9")) == "t30"


def test_resolve_observation_window_ad_hoc():
    assert resolve_observation_window(video_age_hours=Decimal("10")) == "ad_hoc"
    assert resolve_observation_window(video_age_hours=Decimal("100")) == "ad_hoc"
    assert resolve_observation_window(video_age_hours=Decimal("300")) == "ad_hoc"
    assert resolve_observation_window(video_age_hours=Decimal("800")) == "ad_hoc"


# --- position segment ---

def test_resolve_position_segment_front():
    assert resolve_position_segment(clip_start_ms=0, video_duration_ms=30000) == "front"
    assert resolve_position_segment(clip_start_ms=9999, video_duration_ms=30000) == "front"


def test_resolve_position_segment_middle():
    assert resolve_position_segment(clip_start_ms=10000, video_duration_ms=30000) == "middle"
    assert resolve_position_segment(clip_start_ms=19999, video_duration_ms=30000) == "middle"


def test_resolve_position_segment_rear():
    assert resolve_position_segment(clip_start_ms=20000, video_duration_ms=30000) == "rear"
    assert resolve_position_segment(clip_start_ms=30000, video_duration_ms=30000) == "rear"


def test_resolve_position_segment_rejects_zero_duration():
    with pytest.raises(CurveQualityError, match="invalid_video_duration"):
        resolve_position_segment(clip_start_ms=0, video_duration_ms=0)
