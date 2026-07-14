from pathlib import Path

from app.services.business_overview_service import _build_platform_sales
from app.services.sales_metric_service import PAY_DETAIL_SQL


BACKEND = Path(__file__).resolve().parents[1]


def test_payment_formula_exposes_online_and_offline_sales_columns():
    assert "AS offline_sales_amount" in PAY_DETAIL_SQL
    assert "AS online_sales_amount" in PAY_DETAIL_SQL
    assert "p->>'jsdm' = '011'" in PAY_DETAIL_SQL
    assert "('000', '003', '004', '666', '971')" in PAY_DETAIL_SQL


def test_overview_exposes_ready_channel_metrics_from_shared_payment_formula():
    source = (BACKEND / "app" / "services" / "business_overview_service.py").read_text(
        encoding="utf-8"
    )

    assert "PAY_DETAIL_SQL" in source
    assert '"yesterday_offline_sales"' in source
    assert '"yesterday_online_sales"' in source
    assert 'bm["yesterday_offline_sales"] = _value' in source
    assert 'bm["yesterday_online_sales"] = _value' in source


def test_sales_trend_returns_real_channel_columns_instead_of_fixed_online_zero():
    source = (BACKEND / "app" / "api" / "v1" / "dashboard.py").read_text(
        encoding="utf-8"
    )

    assert "pay.offline_sales_amount" in source
    assert "pay.online_sales_amount" in source
    assert '"offline_sales": float(r["offline_sales"] or 0)' in source
    assert '"online_sales": float(r["online_sales"] or 0)' in source
    assert '"online_sales": 0' not in source


def test_dws_rebuild_persists_real_channel_amounts():
    source = (BACKEND / "app" / "services" / "sales_metric_service.py").read_text(
        encoding="utf-8"
    )
    rebuild_source = source[source.index("async def rebuild_confirmed_sales_dws") :]

    assert "pay.offline_sales_amount" in rebuild_source
    assert "pay.online_sales_amount" in rebuild_source
    assert "offline_sales_amount=x.offline_sales_amount" in rebuild_source
    assert "online_sales_amount=x.online_sales_amount" in rebuild_source
    assert "online_sales_amount=0" not in rebuild_source


def test_small_online_share_is_not_rounded_down_to_zero():
    channels = _build_platform_sales(18057, 9)

    assert channels[0]["pct"] == 99.95
    assert channels[1]["pct"] == 0.05
