from datetime import datetime, timezone

from app.services.life_data_analysis_service import build_investment_overview


def test_builds_verified_roi_and_manual_ai_recommendation():
    captures = [
        {
            "page_path": "/dito/pc/ad/analysis",
            "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
            "response_payload": {
                "code": 0,
                "data": {
                    "BudgetCardInfo": {
                        "indicator": [{"total_ad_cost": 132717, "total_ad_pay_gmv": 299600}]
                    },
                    "TargetSexAgeDistribute": {
                        "data": [{"age_name": "31-40", "man_ad_cost_1d": 49392, "woman_ad_cost_1d": 34227}]
                    },
                    "CityDistribution": {"data": [{"city_resident": "贵阳市", "sub_ad_cost": 120092, "sub_ad_cost_rate": 0.9048}]},
                    "indicatorTrend": {"data": [{"date_str": "2026-07-06", "total_ad_cost": 19145, "total_ad_pay_gmv": 0}]},
                    "SceneVideoRankTop": {"data": [{"item_id": "v1", "item_title": "贵阳男装", "current_ad_cost": 22351, "current_ad_pay_gmv": 0, "item_total_play_cnt": 1000}]},
                },
            },
        },
        {
            "page_path": "/dito/pc/business/page",
            "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
            "response_payload": {
                "code": 0,
                "data": {"Overview": {"data": [{"pay_gmv": 299600, "verify_gmv": 116000, "refund_gmv": 31040, "verify_cert_cnt": 8}]}}
            },
        },
    ]

    result = build_investment_overview(
        captures,
        [],
        {
            "status": "online",
            "template_count": 7,
            "last_full_success_at": datetime(2026, 7, 13, 3, 22, tzinfo=timezone.utc),
            "group_health": {
                "video": {"status": "healthy", "template_count": 1},
                "business": {"status": "healthy", "template_count": 3},
                "advertising": {"status": "healthy", "template_count": 2},
            },
        },
    )

    assert result["summary"]["ad_cost_fen"] == 132717
    assert result["summary"]["verify_gmv_fen"] == 116000
    assert result["summary"]["verify_roi"] == 0.87
    assert result["summary"]["cost_per_verify_fen"] == 16590
    assert result["ai_recommendation"]["action"] == "reduce_and_observe"
    assert result["ai_recommendation"]["requires_human_confirm"] is True
    assert result["demographics"][0]["age"] == "31-40"
    assert result["regions"][0]["name"] == "贵阳市"
    assert result["trends"][0]["date"] == "2026-07-06"
    assert result["materials"][0]["play_count"] == 1000
    assert result["collector"]["template_count"] == 7
    assert result["collector"]["groups"]["advertising"]["status"] == "healthy"
    assert result["collector"]["last_full_success_at"] == "2026-07-13T03:22:00+00:00"


def test_never_invents_roi_when_cost_is_missing():
    result = build_investment_overview([], [], None)
    assert result["summary"]["verify_roi"] is None
    assert result["ai_recommendation"]["action"] == "collect_more_data"
    assert result["data_quality"]["missing"]


def test_uses_latest_statistical_period_instead_of_historical_maximum():
    def capture(end_date: str, cost: int, verify: int):
        return [
            {
                "page_path": "/dito/pc/ad/analysis",
                "captured_at": datetime.fromisoformat(f"{end_date}T03:00:00+00:00"),
                "request_payload": {"biz_params": {"common_params": {"end_date": end_date}}},
                "response_payload": {"code": 0, "data": {"indicator": [{"total_ad_cost": cost}]}},
            },
            {
                "page_path": "/dito/pc/business/page",
                "captured_at": datetime.fromisoformat(f"{end_date}T03:00:01+00:00"),
                "request_payload": {"biz_params": {"common_params": {"end_date": end_date}}},
                "response_payload": {"code": 0, "data": {"Overview": {"data": [{"verify_gmv": verify}]}}},
            },
        ]

    rows = capture("2026-07-12", 999999, 888888) + capture("2026-07-13", 10000, 12000)
    result = build_investment_overview(rows, [], {"status": "online"})
    assert result["summary"]["ad_cost_fen"] == 10000
    assert result["summary"]["verify_gmv_fen"] == 12000
    assert result["period"]["stat_end"] == "2026-07-13"
