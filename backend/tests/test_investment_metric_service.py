"""Tests for long-lived normalized investment metrics."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.investment_metric_service import normalize_capture


def ad_analysis_capture():
    return SimpleNamespace(
        id=42,
        account_id="1798826701211732",
        page_path="/dito/pc/ad/analysis",
        request_payload={
            "biz_params": {
                "common_params": {
                    "start_date": "2026-07-10",
                    "end_date": "2026-07-16",
                }
            }
        },
        response_payload={
            "code": 0,
            "data": {
                "layout": [
                    {
                        "data": {
                            "ProvinceDistribution": {
                                "data": [
                                    {
                                        "province_resident": "贵州省",
                                        "sub_ad_cost": 113423,
                                        "sub_ad_cost_rate": 0.9933,
                                    }
                                ]
                            }
                        },
                        "children": [
                            {
                                "data": {
                                    "CityDistribution": {
                                        "data": [
                                            {
                                                "city_resident": "贵阳市",
                                                "sub_ad_cost": 113174,
                                                "sub_ad_cost_rate": 0.9911,
                                            }
                                        ]
                                    }
                                }
                            }
                        ],
                    }
                ]
            },
        },
        captured_at=datetime(2026, 7, 17, 8, 41, tzinfo=timezone.utc),
    )


def test_region_levels_are_normalized_separately():
    facts = normalize_capture(ad_analysis_capture())

    province = [fact for fact in facts if fact.dimension_type == "region_province"]
    city = [fact for fact in facts if fact.dimension_type == "region_city"]

    assert [(fact.dimension_label, fact.spend_fen) for fact in province] == [
        ("贵州省", 113423)
    ]
    assert [(fact.dimension_label, fact.spend_fen) for fact in city] == [
        ("贵阳市", 113174)
    ]
    assert province[0].source_capture_ids == [42]
    assert city[0].metrics_extra == {"spend_rate": 0.9911}


def test_region_fact_preserves_period_fen_and_estimated_attribution():
    fact = next(
        fact
        for fact in normalize_capture(ad_analysis_capture())
        if fact.dimension_type == "region_city"
    )

    assert fact.stat_start.isoformat() == "2026-07-10"
    assert fact.stat_end.isoformat() == "2026-07-16"
    assert fact.attribution_quality == "period_estimate"
    assert isinstance(fact.spend_fen, int)
    assert len(fact.input_hash) == 64
