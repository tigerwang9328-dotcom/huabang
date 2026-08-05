"""TDD tests for the Douyin color analytics v4.0 report routes (Task: report routes).

Covers:
- 7 new routes registered (outfit/top/bottom report, export, advance-stage,
  bounce-report toggle, compute-metrics)
- query_outfit_rankings: ranking_rows, <3 samples excluded, <5 samples no stdev
- query_single_garment_rankings: top bucket filters outer+top, bottom only bottom
- export_rankings: CSV and XLSX formula-injection escaping
- Source-code permission checks for admin/verified-semantics routes
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers: sync mock session for service-function tests
# ---------------------------------------------------------------------------

class _OutfitMetric:
    """Mock for OutfitColorMetric rows."""

    def __init__(self, combination_key, average_retention, calculated_at,
                 participant_count=2, dominant_position_segment="front"):
        self.combination_key = combination_key
        self.average_retention = average_retention
        self.calculated_at = calculated_at
        self.participant_count = participant_count
        self.dominant_position_segment = dominant_position_segment


class _VideoColorMetric:
    """Mock for VideoColorMetric rows."""

    def __init__(self, style_id, sku_code, garment_position, average_retention,
                 calculated_at, dominant_position_segment="front"):
        self.style_id = style_id
        self.sku_code = sku_code
        self.garment_position = garment_position
        self.average_retention = average_retention
        self.calculated_at = calculated_at
        self.dominant_position_segment = dominant_position_segment


class _Scalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _Result:
    def __init__(self, scalars=None, scalar=None):
        self._scalars = scalars or []
        self._scalar = scalar

    def scalars(self):
        return _Scalars(self._scalars)

    def scalar(self):
        return self._scalar


class _SyncDb:
    """Synchronous mock session for service function tests.

    Returns pre-configured results in order: first the metric query, then
    the multi_focus count, then the unclear count.

    ``metric_filter`` simulates the SQL WHERE clause filter on the metric rows
    (e.g. garment_position IN (...) for single-garment rankings).
    """

    def __init__(self, metrics, multi_focus_count=0, unclear_count=0, metric_filter=None):
        self._call = 0
        self._metrics = metrics
        self._multi_focus_count = multi_focus_count
        self._unclear_count = unclear_count
        self._metric_filter = metric_filter

    def execute(self, _query):
        self._call += 1
        if self._call == 1:
            if self._metric_filter is not None:
                filtered = [m for m in self._metrics if self._metric_filter(m)]
                return _Result(scalars=filtered)
            return _Result(scalars=self._metrics)
        elif self._call == 2:
            return _Result(scalar=self._multi_focus_count)
        return _Result(scalar=self._unclear_count)


def _ts(day):
    return datetime(2026, 7, day, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 1: routes registered
# ---------------------------------------------------------------------------

def test_report_routes_are_registered():
    """All 7 new report/release/compute routes must be registered on the router."""
    from app.api.v1.douyin_color_analytics import router

    expected_routes = {
        ("/douyin-color-analytics/accounts/{account_id}/report/outfit", frozenset({"GET"})),
        ("/douyin-color-analytics/accounts/{account_id}/report/top", frozenset({"GET"})),
        ("/douyin-color-analytics/accounts/{account_id}/report/bottom", frozenset({"GET"})),
        ("/douyin-color-analytics/accounts/{account_id}/report/export", frozenset({"POST"})),
        ("/douyin-color-analytics/accounts/{account_id}/release-stage/advance", frozenset({"POST"})),
        ("/douyin-color-analytics/accounts/{account_id}/release-stage/bounce-report", frozenset({"POST"})),
        ("/douyin-color-analytics/accounts/{account_id}/compute-metrics", frozenset({"POST"})),
    }
    actual_routes = {(route.path, frozenset(route.methods or [])) for route in router.routes}
    missing = expected_routes - actual_routes
    assert not missing, f"Missing routes: {missing}"


# ---------------------------------------------------------------------------
# Tests 2-4: query_outfit_rankings
# ---------------------------------------------------------------------------

def test_query_outfit_rankings_returns_ranking_rows():
    """>=3 samples per combination_key → ranking row with average_retention."""
    from app.services.douyin_color_report_query_service import query_outfit_rankings

    metrics = [
        _OutfitMetric("top:10|bottom:20", Decimal("0.50"), _ts(1)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.70"), _ts(2)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.60"), _ts(3)),
    ]
    db = _SyncDb(metrics, multi_focus_count=1, unclear_count=2)

    result = query_outfit_rankings(
        session=db, account_id=1, observation_window="t7",
    )

    assert "ranking_rows" in result
    assert len(result["ranking_rows"]) == 1
    row = result["ranking_rows"][0]
    assert row["combination_key"] == "top:10|bottom:20"
    assert row["sample_count"] == 3
    assert abs(row["average_retention"] - 0.6) < 0.001
    assert row["stdev"] is None  # <5 samples → no stdev
    assert row["participant_count"] == 2
    assert result["excluded_multi_focus_count"] == 1
    assert result["excluded_unclear_count"] == 2
    assert result["observation_window"] == "t7"
    assert result["position_segment"] == "all"
    assert result["disclaimer"] == "本报告为历史关联性分析，不是因果结论"


def test_query_outfit_rankings_below_3_samples_no_ranking():
    """<3 samples per combination_key → excluded from ranking."""
    from app.services.douyin_color_report_query_service import query_outfit_rankings

    metrics = [
        _OutfitMetric("top:10|bottom:20", Decimal("0.50"), _ts(1)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.70"), _ts(2)),
    ]
    db = _SyncDb(metrics)

    result = query_outfit_rankings(
        session=db, account_id=1, observation_window="t7",
    )

    assert result["ranking_rows"] == []
    assert result["sample_count"] == 2  # total samples considered


def test_query_outfit_rankings_below_5_samples_no_stdev():
    """>=3 but <5 samples → enters ranking but stdev is None."""
    from app.services.douyin_color_report_query_service import query_outfit_rankings

    metrics = [
        _OutfitMetric("top:10|bottom:20", Decimal("0.50"), _ts(1)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.60"), _ts(2)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.70"), _ts(3)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.55"), _ts(4)),
    ]
    db = _SyncDb(metrics)

    result = query_outfit_rankings(
        session=db, account_id=1, observation_window="t7",
    )

    assert len(result["ranking_rows"]) == 1
    row = result["ranking_rows"][0]
    assert row["sample_count"] == 4
    assert row["stdev"] is None  # <5 → no stdev


def test_query_outfit_rankings_5_samples_shows_stdev():
    """>=5 samples → stdev (sample standard deviation n-1) is shown."""
    from app.services.douyin_color_report_query_service import query_outfit_rankings

    metrics = [
        _OutfitMetric("top:10|bottom:20", Decimal("0.50"), _ts(1)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.60"), _ts(2)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.70"), _ts(3)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.55"), _ts(4)),
        _OutfitMetric("top:10|bottom:20", Decimal("0.65"), _ts(5)),
    ]
    db = _SyncDb(metrics)

    result = query_outfit_rankings(
        session=db, account_id=1, observation_window="t7",
    )

    row = result["ranking_rows"][0]
    assert row["sample_count"] == 5
    assert row["stdev"] is not None
    assert row["stdev"] > 0


# ---------------------------------------------------------------------------
# Tests 5-6: query_single_garment_rankings
# ---------------------------------------------------------------------------

def test_query_single_garment_rankings_top_filters_outer_and_top():
    """top bucket includes garment_position in (outer, top)."""
    from app.services.douyin_color_report_query_service import query_single_garment_rankings

    metrics = [
        _VideoColorMetric(10, "SKU-A", "outer", Decimal("0.50"), _ts(1)),
        _VideoColorMetric(10, "SKU-A", "outer", Decimal("0.60"), _ts(2)),
        _VideoColorMetric(10, "SKU-A", "outer", Decimal("0.55"), _ts(3)),
        _VideoColorMetric(20, "SKU-B", "top", Decimal("0.70"), _ts(1)),
        _VideoColorMetric(20, "SKU-B", "top", Decimal("0.75"), _ts(2)),
        _VideoColorMetric(20, "SKU-B", "top", Decimal("0.65"), _ts(3)),
        _VideoColorMetric(30, "SKU-C", "bottom", Decimal("0.80"), _ts(1)),
        _VideoColorMetric(30, "SKU-C", "bottom", Decimal("0.85"), _ts(2)),
        _VideoColorMetric(30, "SKU-C", "bottom", Decimal("0.82"), _ts(3)),
    ]
    # metric_filter simulates the SQL WHERE garment_position IN ('outer','top') filter
    db = _SyncDb(metrics, metric_filter=lambda m: m.garment_position in ("outer", "top"))

    result = query_single_garment_rankings(
        session=db, account_id=1, ranking_bucket="top", observation_window="t7",
    )

    combination_keys = {r["combination_key"] for r in result["ranking_rows"]}
    # top bucket should include outer (style 10) and top (style 20), but NOT bottom (style 30)
    assert "10:SKU-A" in combination_keys
    assert "20:SKU-B" in combination_keys
    assert "30:SKU-C" not in combination_keys


def test_query_single_garment_rankings_bottom_filters_bottom_only():
    """bottom bucket includes only garment_position='bottom'."""
    from app.services.douyin_color_report_query_service import query_single_garment_rankings

    metrics = [
        _VideoColorMetric(10, "SKU-A", "outer", Decimal("0.50"), _ts(1)),
        _VideoColorMetric(10, "SKU-A", "outer", Decimal("0.60"), _ts(2)),
        _VideoColorMetric(10, "SKU-A", "outer", Decimal("0.55"), _ts(3)),
        _VideoColorMetric(30, "SKU-C", "bottom", Decimal("0.80"), _ts(1)),
        _VideoColorMetric(30, "SKU-C", "bottom", Decimal("0.85"), _ts(2)),
        _VideoColorMetric(30, "SKU-C", "bottom", Decimal("0.82"), _ts(3)),
    ]
    # metric_filter simulates the SQL WHERE garment_position IN ('bottom') filter
    db = _SyncDb(metrics, metric_filter=lambda m: m.garment_position == "bottom")

    result = query_single_garment_rankings(
        session=db, account_id=1, ranking_bucket="bottom", observation_window="t7",
    )

    combination_keys = {r["combination_key"] for r in result["ranking_rows"]}
    assert "30:SKU-C" in combination_keys
    assert "10:SKU-A" not in combination_keys


# ---------------------------------------------------------------------------
# Tests 7-8: export_rankings formula injection escaping
# ---------------------------------------------------------------------------

def test_export_rankings_csv_escapes_formula_injection():
    """CSV export must escape = + - @ formula-injection prefixes."""
    from app.services.douyin_color_report_query_service import export_rankings

    rankings = {
        "ranking_rows": [
            {
                "combination_key": "=SUM(A1)",
                "average_retention": 0.5,
                "stdev": None,
                "sample_count": 3,
                "participant_count": 2,
                "position_segment": "all",
            },
            {
                "combination_key": "+cmd|/c calc",
                "average_retention": 0.6,
                "stdev": None,
                "sample_count": 3,
                "participant_count": 2,
                "position_segment": "all",
            },
        ],
        "observation_window": "t7",
        "position_segment": "all",
        "metric_version": "v4.0",
        "source_data_cutoff_at": "2026-07-31T00:00:00+00:00",
        "sample_count": 6,
    }

    result = export_rankings(rankings=rankings, format="csv", tab="outfit")

    assert "content" in result
    assert "filename" in result
    assert result["filename"].endswith(".csv")
    content = result["content"]
    # Formula injection prefixes must be escaped with a leading single quote
    assert "'=SUM(A1)" in content
    assert "'+cmd|/c calc" in content
    # No data line (non-metadata, non-header) should start with an unescaped = or +
    data_lines = [
        line for line in content.split("\n")
        if line and not line.startswith("#") and "combination_key" not in line
    ]
    for line in data_lines:
        assert not line.startswith("=SUM"), f"Unescaped formula in line: {line}"
        assert not line.startswith("+cmd"), f"Unescaped formula in line: {line}"


def test_export_rankings_xlsx_escapes_formula_injection():
    """XLSX export must escape = + - @ formula-injection prefixes."""
    from app.services.douyin_color_report_query_service import export_rankings

    rankings = {
        "ranking_rows": [
            {
                "combination_key": "=cmd|/c calc",
                "average_retention": 0.5,
                "stdev": 0.1,
                "sample_count": 5,
                "participant_count": 2,
                "position_segment": "all",
            },
            {
                "combination_key": "@SUM(A1)",
                "average_retention": 0.6,
                "stdev": 0.2,
                "sample_count": 5,
                "participant_count": 2,
                "position_segment": "all",
            },
        ],
        "observation_window": "t7",
        "position_segment": "all",
        "metric_version": "v4.0",
        "source_data_cutoff_at": "2026-07-31T00:00:00+00:00",
        "sample_count": 10,
    }

    result = export_rankings(rankings=rankings, format="xlsx", tab="top")

    assert "content" in result
    assert "filename" in result
    assert result["filename"].endswith(".xlsx")
    content = result["content"]
    assert "'=cmd|/c calc" in content
    assert "'@SUM(A1)" in content


# ---------------------------------------------------------------------------
# Tests 9-11: source-code permission checks
# ---------------------------------------------------------------------------

def _source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "v1"
        / "douyin_color_analytics.py"
    ).read_text(encoding="utf-8")


def test_advance_stage_route_requires_admin_permission():
    """advance_release_stage route must require douyin.admin permission."""
    source = _source()
    fn_start = source.index("def advance_release_stage")
    section = source[fn_start : fn_start + 800]
    assert 'require_permission("douyin.admin")' in section or 'require_any_permission' in section and '"douyin.admin"' in section


def test_toggle_bounce_report_route_requires_verified_semantics():
    """toggle_bounce_report route must enforce bounce_semantics verification."""
    source = _source()
    fn_start = source.index("def toggle_bounce_report")
    section = source[fn_start : fn_start + 1200]
    # The route must call enable_bounce_report (which raises ValueError if not verified)
    # or otherwise reference the verified-semantics gating.
    assert "enable_bounce_report" in section or "bounce_semantics_not_verified" in section or "can_enable_bounce_report" in section


def test_compute_metrics_route_requires_admin_permission():
    """compute_metrics route must require douyin.admin permission."""
    source = _source()
    fn_start = source.index("def compute_metrics")
    section = source[fn_start : fn_start + 800]
    assert 'require_permission("douyin.admin")' in section or 'require_any_permission' in section and '"douyin.admin"' in section


def test_compute_metrics_route_replaces_prior_v41_results_before_inserting():
    """Repeated multi-outfit recomputation must not hit metric unique constraints."""
    source = _source()
    fn_start = source.index("def compute_metrics")
    section = source[fn_start : fn_start + 1800]
    assert 'delete(OutfitColorMetric)' in section
    assert 'delete(VideoColorMetric)' in section
    assert section.index('delete(OutfitColorMetric)') < section.index('clips = (await db.execute')
