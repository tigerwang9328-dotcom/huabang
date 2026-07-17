from datetime import datetime, timezone

import pytest

import app.services.life_data_analysis_service as analysis_service
from app.services.life_data_analysis_service import (
    _scan_canonical_fields,
    build_investment_overview,
)


FRONTEND_CANONICAL_ALIASES = {
    "plays": ["plays", "item_play_cnt", "item_total_play_cnt"],
    "spend_fen": ["spend_fen", "total_ad_cost", "current_ad_cost"],
    "ad_orders": ["ad_orders", "order_cnt", "ad_order_cnt", "ad_pay_order_cnt", "total_ad_order_cnt", "current_ad_order_cnt"],
    "ad_pay_gmv_fen": ["ad_pay_gmv_fen", "ad_pay_gmv", "total_ad_pay_gmv", "current_ad_pay_gmv"],
    "pay_gmv_fen": ["pay_gmv_fen", "pay_gmv"],
    "verified_gmv_fen": ["verified_gmv_fen", "verify_gmv"],
    "verified_count": ["verified_count", "verify_cert_cnt"],
    "refund_gmv_fen": ["refund_gmv_fen", "refund_gmv"],
    "audience_age": ["audience_age", "age", "age_range"],
    "audience_gender": ["audience_gender", "gender"],
    "region": ["region", "province", "city"],
    "hour": ["hour", "stat_hour"],
    "video_id": ["video_id", "item_id"],
    "campaign_id": ["campaign_id"],
    "plan_id": ["plan_id"],
    "creative_id": ["creative_id"],
    "store_id": ["store_id"],
    "stat_date": ["stat_date", "date_str"],
}


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
    assert result["regions"]["city"][0]["name"] == "贵阳市"
    assert result["regions"]["province"] == []
    assert result["regions"]["supports_effectiveness_decision"] is False
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


def test_backend_derives_nested_field_coverage_and_real_sources_without_browser_claims():
    captures = [
        {
            "page_path": "/dito/pc/ad/analysis",
            "endpoint": "/api/dito/query",
            "captured_at": datetime(2026, 7, 13, 3, 0, tzinfo=timezone.utc),
            "request_payload": {"end_date": "2026-07-13"},
            "response_payload": {
                "code": 0,
                "data": {
                    "result": {
                        "summary": {"metrics": {"current_ad_cost": 12000}},
                        "extra": {"canonicalFields": ["verified_gmv_fen"]},
                    }
                },
            },
        },
        {
            "page_path": "/dito/pc/business/page",
            "endpoint": "/api/lowcode_api/query",
            "captured_at": datetime(2026, 7, 13, 3, 0, 1, tzinfo=timezone.utc),
            "request_payload": {"filters": {"end_date": "2026-07-13"}},
            "response_payload": {
                "code": 0,
                "data": {"result": {"list": [{"verify_gmv": 18000, "date_str": "2026-07-13"}]}},
            },
        },
    ]

    quality = build_investment_overview(captures, [], None)["data_quality"]

    assert quality["required_fields"] == [
        "spend_fen",
        "verified_gmv_fen",
        "stat_date",
    ]
    assert quality["required_analysis_fields"] == ["attribution_quality"]
    assert quality["available_analysis_fields"] == ["attribution_quality"]
    assert quality["missing_analysis_fields"] == []
    assert quality["available_fields"] == ["spend_fen", "verified_gmv_fen", "stat_date"]
    assert quality["field_sources"]["spend_fen"] == [
        {"page_path": "/dito/pc/ad/analysis", "endpoint": "/api/dito/query", "stat_end": "2026-07-13"}
    ]
    assert quality["field_sources"]["verified_gmv_fen"] == [
        {"page_path": "/dito/pc/business/page", "endpoint": "/api/lowcode_api/query", "stat_end": "2026-07-13"}
    ]
    assert quality["attribution_quality"] == "period_estimate"
    assert quality["period_consistent"] is True
    assert quality["missing"] == []


def test_mismatched_periods_are_not_merged_and_block_recommendation():
    captures = [
        {
            "page_path": "/dito/pc/ad/analysis",
            "endpoint": "/api/dito/query",
            "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
            "request_payload": {"end_date": "2026-07-13"},
            "response_payload": {"data": {"total_ad_cost": 12000, "date_str": "2026-07-13"}},
        },
        {
            "page_path": "/dito/pc/business/page",
            "endpoint": "/api/dito/query",
            "captured_at": datetime(2026, 7, 12, tzinfo=timezone.utc),
            "request_payload": {"end_date": "2026-07-12"},
            "response_payload": {"data": {"verify_gmv": 18000, "date_str": "2026-07-12"}},
        },
    ]

    result = build_investment_overview(captures, [], None)

    assert result["summary"]["ad_cost_fen"] == 12000
    assert result["summary"]["verify_gmv_fen"] is None
    assert result["summary"]["verify_roi"] is None
    assert result["data_quality"]["period_consistent"] is True
    assert result["data_quality"]["attribution_quality"] == "missing"
    assert "verified_gmv_fen" in result["data_quality"]["missing"]
    assert result["ai_recommendation"]["action"] == "collect_more_data"


def test_guidance_is_deterministic_and_has_minimum_recommendation_fields():
    quality = build_investment_overview([], [], None)["data_quality"]

    assert quality["missing"] == ["spend_fen", "verified_gmv_fen", "stat_date"]
    assert quality["required_analysis_fields"] == ["attribution_quality"]
    assert quality["available_analysis_fields"] == []
    assert quality["missing_analysis_fields"] == ["attribution_quality"]
    assert quality["collection_guidance"] == [
        {"field": "spend_fen", "page": "投放 → 广告分析", "action": "open_and_refresh"},
        {"field": "verified_gmv_fen", "page": "经营 → 经营概览", "action": "open_and_refresh"},
        {"field": "stat_date", "page": "经营 → 经营概览", "action": "open_and_refresh"},
    ]


@pytest.mark.parametrize(
    ("canonical", "alias"),
    [(canonical, alias) for canonical, aliases in FRONTEND_CANONICAL_ALIASES.items() for alias in aliases],
)
def test_backend_alias_catalog_matches_every_frontend_alias(canonical, alias):
    value = "2026-07-13" if canonical == "stat_date" else ("dimension" if canonical not in analysis_service._NUMERIC_FIELDS else 1)
    assert canonical in _scan_canonical_fields({"data": {alias: value}})


def test_response_row_period_overrides_request_fallback_and_detects_mixed_rows():
    capture = {
        "page_path": "/dito/pc/ad/analysis",
        "endpoint": "/api/dito/query",
        "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
        "request_payload": {"end_date": "2026-07-13"},
        "response_payload": {"data": {"rows": [
            {"date_str": "2026-07-12", "spend_fen": 10000},
            {"stat_date": "2026-07-13", "verified_gmv_fen": 15000},
        ]}},
    }

    quality = build_investment_overview([capture], [], None)["data_quality"]

    assert quality["field_sources"]["spend_fen"][0]["stat_end"] == "2026-07-12"
    assert quality["field_sources"]["verified_gmv_fen"][0]["stat_end"] == "2026-07-13"
    assert quality["period_consistent"] is False
    assert quality["attribution_quality"] == "missing"


def test_response_business_period_drives_latest_period_and_allows_consistent_roi():
    capture = {
        "page_path": "/dito/pc/ad/analysis", "endpoint": "/api/dito/query",
        "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
        "request_payload": {"end_date": "2026-07-13"},
        "response_payload": {"data": {"rows": [{
            "date_str": "2026-07-12", "spend_fen": 10000, "verified_gmv_fen": 15000,
        }]}},
    }
    result = build_investment_overview([capture], [], None)
    assert result["period"]["stat_end"] == "2026-07-12"
    assert result["summary"]["verify_roi"] == 1.5
    assert result["data_quality"]["period_consistent"] is True
    assert result["data_quality"]["field_sources"]["spend_fen"][0]["stat_end"] == "2026-07-12"


def test_historical_response_period_does_not_block_latest_selected_period():
    def capture(response_date, cost, verify):
        return {
            "page_path": "/dito/pc/ad/analysis", "endpoint": "/api/dito/query",
            "captured_at": datetime.fromisoformat(f"{response_date}T03:00:00+00:00"),
            "request_payload": {"end_date": "2026-07-13"},
            "response_payload": {"data": {"rows": [{
                "date_str": response_date, "spend_fen": cost, "verified_gmv_fen": verify,
            }]}},
        }
    result = build_investment_overview([
        capture("2026-07-11", 999999, 888888),
        capture("2026-07-12", 10000, 12000),
    ], [], None)
    assert result["period"]["stat_end"] == "2026-07-12"
    assert result["summary"]["ad_cost_fen"] == 10000
    assert result["summary"]["verify_gmv_fen"] == 12000
    assert result["summary"]["verify_roi"] == 1.2
    assert result["data_quality"]["period_consistent"] is True


def test_mixed_metric_response_periods_in_selected_analysis_block_roi():
    capture = {
        "page_path": "/dito/pc/ad/analysis", "endpoint": "/api/dito/query",
        "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
        "request_payload": {"end_date": "2026-07-13"},
        "response_payload": {"data": {"rows": [
            {"date_str": "2026-07-12", "spend_fen": 10000},
            {"date_str": "2026-07-11", "verified_gmv_fen": 15000},
        ]}},
    }
    result = build_investment_overview([capture], [], None)
    assert result["period"]["stat_end"] == "2026-07-12"
    assert result["summary"]["verify_roi"] is None
    assert result["data_quality"]["period_consistent"] is False
    assert result["data_quality"]["attribution_quality"] == "missing"


def test_daily_ad_trend_periods_do_not_conflict_with_selected_summary_metrics():
    captures = [
        {
            "page_path": "/dito/pc/ad/analysis", "endpoint": "/api/dito/query",
            "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
            "request_payload": {"end_date": "2026-07-13"},
            "response_payload": {"data": {
                "BudgetCardInfo": {"summary": {"total_ad_cost": 132717}},
                "indicatorTrend": {"data": [
                    {"date_str": "2026-07-11", "total_ad_cost": 18000},
                    {"date_str": "2026-07-12", "total_ad_cost": 19000},
                    {"date_str": "2026-07-13", "total_ad_cost": 20000},
                ]},
            }},
        },
        {
            "page_path": "/dito/pc/business/page", "endpoint": "/api/dito/query",
            "captured_at": datetime(2026, 7, 13, 0, 0, 1, tzinfo=timezone.utc),
            "request_payload": {"end_date": "2026-07-13"},
            "response_payload": {"data": {"summary": {
                "stat_date": "2026-07-13", "verify_gmv": 116000,
            }}},
        },
    ]
    result = build_investment_overview(captures, [], None)
    assert result["summary"]["ad_cost_fen"] == 132717
    assert result["summary"]["verify_gmv_fen"] == 116000
    assert result["summary"]["verify_roi"] == 0.87
    assert result["data_quality"]["period_consistent"] is True


def test_selected_summary_metric_period_mismatch_still_blocks_roi():
    captures = [
        {
            "page_path": "/dito/pc/ad/analysis", "endpoint": "/api/dito/query",
            "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
            "request_payload": {"end_date": "2026-07-13"},
            "response_payload": {"data": {"summary": {
                "stat_date": "2026-07-12", "total_ad_cost": 10000,
            }}},
        },
        {
            "page_path": "/dito/pc/business/page", "endpoint": "/api/dito/query",
            "captured_at": datetime(2026, 7, 13, 0, 0, 1, tzinfo=timezone.utc),
            "request_payload": {"end_date": "2026-07-13"},
            "response_payload": {"data": {"summary": {
                "stat_date": "2026-07-13", "verify_gmv": 15000,
            }}},
        },
    ]
    result = build_investment_overview(captures, [], None)
    assert result["summary"]["ad_cost_fen"] == 10000
    assert result["summary"]["verify_gmv_fen"] == 15000
    assert result["summary"]["verify_roi"] is None
    assert result["data_quality"]["period_consistent"] is False
    assert result["data_quality"]["attribution_quality"] == "missing"


def test_required_available_missing_invariant_for_all_attribution_states():
    missing = build_investment_overview([], [], None)["data_quality"]
    assert set(missing["required_fields"]) - set(missing["available_fields"]) == set(missing["missing"])
    assert set(missing["required_analysis_fields"]) - set(missing["available_analysis_fields"]) == set(missing["missing_analysis_fields"])

    base = {
        "page_path": "/dito/pc/ad/analysis", "endpoint": "/api/dito/query",
        "request_payload": {"end_date": "2026-07-13"},
        "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
    }
    estimated = build_investment_overview([{**base, "response_payload": {"data": {"spend_fen": 1, "verified_gmv_fen": 2, "stat_date": "2026-07-13"}}}], [], None)["data_quality"]
    exact = build_investment_overview([{**base, "response_payload": {"data": {"spend_fen": 1, "verified_gmv_fen": 2, "stat_date": "2026-07-13", "video_id": "v", "plan_id": "p"}}}], [], None)["data_quality"]
    for quality, expected in ((estimated, "period_estimate"), (exact, "exact")):
        assert quality["attribution_quality"] == expected
        assert set(quality["required_fields"]) - set(quality["available_fields"]) == set(quality["missing"])
        assert quality["available_analysis_fields"] == ["attribution_quality"]
        assert quality["missing_analysis_fields"] == []


def test_wide_array_stops_consuming_at_node_budget():
    class CountingList(list):
        yielded = 0

        def __iter__(self):
            for value in super().__iter__():
                type(self).yielded += 1
                yield value

    rows = CountingList({"plays": index} for index in range(1000))
    fields = _scan_canonical_fields(rows, max_nodes=25)
    assert CountingList.yielded <= 25
    assert fields["plays"]["count"] < 25


def test_build_scans_each_capture_once(monkeypatch):
    original = analysis_service._analyze_capture
    calls = []

    def counted(capture):
        calls.append(capture)
        return original(capture)

    monkeypatch.setattr(analysis_service, "_analyze_capture", counted)
    captures = [
        {"page_path": "/a", "response_payload": {"plays": 1}},
        {"page_path": "/b", "response_payload": {"plays": 2}},
    ]
    build_investment_overview(captures, [], None)
    assert calls == captures


def test_direct_platform_identifiers_allow_exact_but_estimates_and_missing_never_upgrade():
    exact_capture = {
        "page_path": "/dito/pc/ad/analysis",
        "endpoint": "/api/dito/query",
        "captured_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
        "request_payload": {"end_date": "2026-07-13"},
        "response_payload": {
            "data": {
                "rows": [{
                    "current_ad_cost": 10000,
                    "verify_gmv": 15000,
                    "date_str": "2026-07-13",
                    "video_id": "v1",
                    "creative_id": "c1",
                    "plan_id": "p1",
                }]
            }
        },
    }
    exact = build_investment_overview([exact_capture], [], None)["data_quality"]
    assert exact["attribution_quality"] == "exact"

    estimated_capture = {
        **exact_capture,
        "response_payload": {"data": {"rows": [{
            "current_ad_cost": 10000,
            "verify_gmv": 15000,
            "date_str": "2026-07-13",
            "store_id": "s1",
        }]}},
    }
    estimated = build_investment_overview([estimated_capture], [], None)["data_quality"]
    assert estimated["attribution_quality"] == "period_estimate"

    missing = build_investment_overview([{**exact_capture, "response_payload": {"data": {"video_id": "v1"}}}], [], None)["data_quality"]
    assert missing["attribution_quality"] == "missing"


def test_scanner_rejects_bool_nan_and_infinity_and_bounds_paths_depth_and_nodes():
    payload = {
        "data": {
            "total_ad_cost": True,
            "verify_gmv": float("nan"),
            "pay_gmv": float("inf"),
            "rows": [{"item_play_cnt": index} for index in range(20)],
        }
    }
    deep = payload["data"]
    for _ in range(45):
        deep["child"] = {}
        deep = deep["child"]
    deep["refund_gmv"] = 99

    fields = _scan_canonical_fields(payload)

    assert "spend_fen" not in fields
    assert "verified_gmv_fen" not in fields
    assert "pay_gmv_fen" not in fields
    assert "refund_gmv_fen" not in fields
    assert fields["plays"]["count"] == 20
    assert len(fields["plays"]["paths"]) == 8


def test_existing_summary_contract_remains_backward_compatible():
    result = build_investment_overview([], [], None)
    assert set(result["summary"]) == {
        "ad_cost_fen", "ad_pay_gmv_fen", "pay_gmv_fen", "verify_gmv_fen",
        "refund_gmv_fen", "verify_cert_count", "ad_pay_roi", "verify_roi",
        "cost_per_verify_fen", "refund_rate",
    }
    assert result["data_quality"]["is_estimated_verify_attribution"] is True
