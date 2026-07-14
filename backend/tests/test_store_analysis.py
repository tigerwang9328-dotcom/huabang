from pathlib import Path

from app.api.v1.store import _growth_rate, _pending_metric


BACKEND = Path(__file__).resolve().parents[1]


def test_growth_rate_handles_day_and_week_comparisons_without_fake_zeroes():
    assert _growth_rate(120, 100) == 0.2
    assert _growth_rate(80, 100) == -0.2
    assert _growth_rate(100, 0) is None
    assert _growth_rate(100, None) is None


def test_unavailable_store_metrics_are_explicitly_pending():
    metric = _pending_metric("dingtalk_footfall", "客流来源未接入")
    assert metric == {
        "value": None,
        "status": "pending_data",
        "source": "dingtalk_footfall",
        "reason": "客流来源未接入",
    }


def test_store_analysis_contract_has_independent_sources_and_drilldowns():
    source = (BACKEND / "app" / "api" / "v1" / "store.py").read_text(encoding="utf-8")

    for field in (
        '"day_over_day_growth"',
        '"week_over_week_growth"',
        '"source_freshness"',
        '"pending_metrics"',
        '"top_products"',
        '"slow_products"',
        '"exceptions"',
    ):
        assert field in source

    assert "dwd.v_apparel_inventory_balance" in source
    assert "ALLOWED_STORE_CODES" in source
