from app.services.business_overview_service import _build_platform_sales


def test_build_platform_sales_keeps_zero_online_channel():
    channels = _build_platform_sales(13722, 0)

    assert channels == [
        {"name": "线下门店", "amount": 13722.0, "pct": 100.0},
        {"name": "线上渠道", "amount": 0.0, "pct": 0.0},
    ]


def test_build_platform_sales_returns_empty_without_sales():
    assert _build_platform_sales(0, 0) == []
