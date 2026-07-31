from datetime import datetime, timezone
from datetime import time
import json
from pathlib import Path

import pytest


def test_batch_hash_is_ordered_by_part_number_and_rejects_missing_or_duplicate_numbers():
    from app.services.douyin_color_ingest_service import IngestProtocolError, compute_batch_hash

    ordered = compute_batch_hash([(2, "b" * 64), (1, "a" * 64)], expected_part_count=2)

    assert ordered == compute_batch_hash([(1, "a" * 64), (2, "b" * 64)], expected_part_count=2)
    with pytest.raises(IngestProtocolError, match="missing_parts"):
        compute_batch_hash([(1, "a" * 64)], expected_part_count=2)
    with pytest.raises(IngestProtocolError, match="part_content_conflict"):
        compute_batch_hash([(1, "a" * 64), (1, "b" * 64)], expected_part_count=2)


def test_part_number_must_be_inside_the_frozen_batch_range():
    from app.services.douyin_color_ingest_service import IngestProtocolError, validate_part_number

    validate_part_number(part_number=2, part_count=2)
    with pytest.raises(IngestProtocolError, match="part_number_invalid"):
        validate_part_number(part_number=3, part_count=2)


def test_snapshot_hash_is_stable_for_equivalent_json_and_distinguishes_curve_changes():
    from app.services.douyin_color_ingest_service import canonical_snapshot_hash

    original = {"analysis_type": 1, "curve": [{"key": "00:00", "value": 1.0}]}
    reordered = {"curve": [{"value": 1.0, "key": "00:00"}], "analysis_type": 1}

    assert canonical_snapshot_hash(original) == canonical_snapshot_hash(reordered)
    assert canonical_snapshot_hash(original) != canonical_snapshot_hash(
        {"analysis_type": 1, "curve": [{"key": "00:00", "value": 0.9}]}
    )


def test_snapshot_hash_is_computed_by_the_server_not_accepted_from_the_collector():
    from app.services.douyin_color_ingest_service import canonical_snapshot_hash, response_snapshot_hash, whitelist_raw_response

    response = {"analysis_trend": {"current_item": [{"key": "00:00", "value": 100}]}}

    expected = canonical_snapshot_hash(whitelist_raw_response({"response_data": response}))
    assert response_snapshot_hash({"response_data": response, "source_snapshot_hash": "0" * 64}) == expected
    assert response_snapshot_hash({"response_data": response, "source_snapshot_hash": "f" * 64}) == expected


def test_raw_response_whitelist_retains_only_curve_evidence_fields():
    from app.services.douyin_color_ingest_service import IngestProtocolError, whitelist_raw_response

    response = {
        "analysis_trend": {
            "current_item": [{"key": "00:00", "value": 100}],
            "similar_author": [{"key": "00:00", "value": 98}],
        },
        "status_code": 0,
        "status_msg": "not persisted",
        "valley_list": [{"untrusted": "not persisted"}],
    }

    assert whitelist_raw_response({"response_data": response}) == {
        "analysis_trend": {
            "current_item": [{"key": "00:00", "value": 100}],
            "similar_author": [{"key": "00:00", "value": 98}],
        },
        "status_code": 0,
    }
    with pytest.raises(IngestProtocolError, match="raw_response_field_forbidden"):
        whitelist_raw_response({"response_data": {"unexpected": "field"}})


def test_batch_counters_are_based_on_materialized_collection_items():
    from app.services.douyin_color_ingest_service import summarize_item_statuses

    assert summarize_item_statuses(["success", "empty_curve", "skipped_non_video"]) == {
        "item_count": 3,
        "success_count": 1,
        "skipped_count": 1,
        "failure_count": 1,
    }


def test_analysis_response_normalization_keeps_retention_and_bounce_as_separate_snapshots():
    from app.services.douyin_color_ingest_service import normalize_analysis_response

    normalized = normalize_analysis_response({
        "analysis_type": 1,
        "http_status": 200,
        "business_status_code": 0,
        "response_data": {"analysis_trend": {"current_item": [{"key": "00:00", "value": 100}]}},
    })

    assert normalized["item_status"] == "success"
    assert normalized["analysis_type"] == 1
    assert normalized["normalized_curve"] == [{"second": 0, "value": 1.0}]
    assert normalize_analysis_response({
        "analysis_type": 7,
        "http_status": 200,
        "business_status_code": 0,
        "response_data": {"analysis_trend": {"current_item": []}},
    })["item_status"] == "empty_curve"


def test_analysis_response_maps_429_and_business_failure_without_a_snapshot_curve():
    from app.services.douyin_color_ingest_service import normalize_analysis_response

    assert normalize_analysis_response({"analysis_type": 1, "http_status": 429})["item_status"] == "rate_limited"
    assert normalize_analysis_response({
        "analysis_type": 7,
        "http_status": 200,
        "business_status_code": 1001,
        "response_data": {"analysis_trend": {"current_item": []}},
    })["item_status"] == "business_failed"


def test_video_payload_expands_to_one_record_per_analysis_type_and_preserves_skips():
    from app.services.douyin_color_ingest_service import expand_collection_record

    video_records = expand_collection_record({
        "video_id": "7666046377541012755",
        "duration_ms": 1000,
        "source_type": "video",
        "retention": {"analysis_type": 1, "http_status": 200, "business_status_code": 0, "response_data": {"analysis_trend": {"current_item": []}}},
        "platform_bounce": {"analysis_type": 7, "http_status": 200, "business_status_code": 0, "response_data": {"analysis_trend": {"current_item": []}}},
    })
    skipped_records = expand_collection_record({
        "video_id": "7662342839439478769", "source_type": "graphic", "skip_reason": "no_video_duration",
    })

    assert [record["analysis_type"] for record in video_records] == [1, 7]
    assert all(record["video_id"] == "7666046377541012755" for record in video_records)
    assert skipped_records == [{
        "video_id": "7662342839439478769", "analysis_type": None, "item_status": "skipped_non_video",
        "error_category": "no_video_duration",
    }]


def test_historical_48_item_fixture_expands_to_46_independent_retention_and_bounce_pairs():
    from app.services.douyin_color_ingest_service import expand_collection_record, normalize_analysis_response, whitelist_raw_response

    fixture_path = Path(__file__).parent / "fixtures" / "douyin" / "historical-20260728.sanitized.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    expanded = [record for video in fixture["videos"] for record in expand_collection_record(video)]
    skipped = [record for item in fixture["skipped_items"] for record in expand_collection_record(item)]

    assert len(fixture["catalog_items"]) == 48
    assert len(expanded) == 92
    assert [record["analysis_type"] for record in expanded].count(1) == 46
    assert [record["analysis_type"] for record in expanded].count(7) == 46
    assert len(skipped) == 2
    assert all(record["item_status"] == "skipped_non_video" for record in skipped)
    statuses = [normalize_analysis_response(record)["item_status"] for record in expanded]
    assert "success" in statuses
    for record in expanded:
        if normalize_analysis_response(record)["item_status"] in {"success", "empty_curve"}:
            assert "analysis_trend" in whitelist_raw_response(record)
    assert normalize_analysis_response(fixture["edge_cases"]["http_429"])["item_status"] == "rate_limited"
    assert normalize_analysis_response(fixture["edge_cases"]["business_error"])["item_status"] == "business_failed"
    assert normalize_analysis_response(fixture["edge_cases"]["empty_curve"]["retention"])["item_status"] == "empty_curve"


def test_part_contract_freezes_batch_identity_and_allows_only_identical_retries():
    from app.services.douyin_color_ingest_service import IngestProtocolError, validate_part_contract

    frozen = {
        "account_id": 1,
        "part_count": 2,
        "schema_version": 1,
        "observed_creator_fingerprint": "a" * 64,
        "installation_id": "install-1",
    }
    incoming = {**frozen, "part_number": 1, "part_hash": "b" * 64}

    validate_part_contract(frozen, incoming, existing_part_hash=None)
    validate_part_contract(frozen, incoming, existing_part_hash="b" * 64)
    with pytest.raises(IngestProtocolError, match="part_count_conflict"):
        validate_part_contract(frozen, {**incoming, "part_count": 3}, existing_part_hash=None)
    with pytest.raises(IngestProtocolError, match="part_content_conflict"):
        validate_part_contract(frozen, incoming, existing_part_hash="c" * 64)


def test_batch_expiry_is_exactly_24_hours_and_does_not_expire_completed_batch():
    from app.services.douyin_color_ingest_service import batch_is_expired

    now = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)

    assert batch_is_expired("receiving", now, now)
    assert not batch_is_expired("receiving", now, now.replace(hour=11, minute=59))
    assert not batch_is_expired("completed", now, now)


def test_collector_health_distinguishes_expected_offline_from_unexpected_offline():
    from app.services.douyin_color_ingest_service import derive_collector_status

    now = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    assert derive_collector_status(
        last_heartbeat_at=now.replace(minute=59),
        now=now,
        expected_online=True,
        document_visibility="visible",
        auth_failed=False,
        upload_blocked=False,
    ) == "online_active"
    assert derive_collector_status(
        last_heartbeat_at=now.replace(hour=11),
        now=now,
        expected_online=True,
        document_visibility="hidden",
        auth_failed=False,
        upload_blocked=False,
    ) == "offline_unexpected"
    assert derive_collector_status(
        last_heartbeat_at=now.replace(hour=11),
        now=now,
        expected_online=False,
        document_visibility="hidden",
        auth_failed=False,
        upload_blocked=False,
    ) == "offline_expected"


def test_expected_online_schedule_uses_weekday_mask_and_supports_overnight_windows():
    from app.services.douyin_color_ingest_service import is_expected_online

    monday_noon = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)
    assert is_expected_online(
        now_local=monday_noon,
        schedules=[{"weekday_mask": 1, "start": time(9), "end": time(18)}],
    )
    assert not is_expected_online(
        now_local=monday_noon,
        schedules=[{"weekday_mask": 2, "start": time(9), "end": time(18)}],
    )
    assert is_expected_online(
        now_local=datetime(2026, 7, 28, 1, tzinfo=timezone.utc),
        schedules=[{"weekday_mask": 1, "start": time(22), "end": time(2)}],
    )


def test_collector_router_exposes_only_the_frozen_v31_ingest_operations():
    from app.api.v1.douyin_color_analytics import router

    paths = {route.path for route in router.routes}

    assert "/douyin-color-analytics/collector-config" in paths
    assert "/douyin-color-analytics/collector-heartbeats" in paths
    assert "/douyin-color-analytics/collector-events" in paths
    assert "/douyin-color-analytics/collection-batches/{client_batch_id}/parts" in paths
    assert "/douyin-color-analytics/collection-batches/{client_batch_id}/missing-parts" in paths
    assert "/douyin-color-analytics/collection-batches/{client_batch_id}/finalize" in paths
    assert "/douyin-color-analytics/collection-batches/{client_batch_id}/abandon" in paths
    assert "/douyin-color-analytics/collection-batches/{client_batch_id}" in paths
    assert "/douyin-color-analytics/videos/{video_id_string}/analysis-snapshots" in paths
    assert "/douyin-color-analytics/accounts" in paths
    assert any(route.path == "/douyin-color-analytics/accounts" and "POST" in route.methods for route in router.routes)
    assert any(
        route.path == "/douyin-color-analytics/accounts/{account_id}/upload-tokens" and "POST" in route.methods
        for route in router.routes
    )
    assert any(
        route.path == "/douyin-color-analytics/accounts/{account_id}/expected-schedules" and "POST" in route.methods
        for route in router.routes
    )


def test_v1_router_registers_the_douyin_collector_router():
    from app.api.v1.router import api_router

    assert any(route.path == "/api/v1/douyin-color-analytics/collector-config" for route in api_router.routes)


def test_collector_config_exposes_the_frozen_v31_capacity_and_version_contract(monkeypatch):
    from types import SimpleNamespace
    from app.api.v1 import douyin_color_analytics

    monkeypatch.setattr(
        douyin_color_analytics,
        "settings",
        SimpleNamespace(DOUYIN_COLOR_COLLECTION_ENABLED=True),
        raising=False,
    )
    payload = douyin_color_analytics.collector_config_payload(account_key="account-a")

    assert payload == {
        "account_key": "account-a",
        "schema_version": 1,
        "supported_schema_versions": [1],
        "minimum_script_version": "3.1.0",
        "recommended_script_version": "3.1.0",
        "collection_enabled": True,
        "max_part_records": 50,
        "max_part_uncompressed_bytes": 5 * 1024 * 1024,
        "max_local_batches": 100,
        "max_local_bytes": 500 * 1024 * 1024,
        "global_start_interval_ms": 1000,
        "max_in_flight_requests": 2,
        "batch_expiry_hours": 24,
    }


def test_collector_config_defaults_to_disabled_until_the_stage_gate_is_enabled(monkeypatch):
    from types import SimpleNamespace
    from app.api.v1 import douyin_color_analytics

    monkeypatch.setattr(
        douyin_color_analytics,
        "settings",
        SimpleNamespace(DOUYIN_COLOR_COLLECTION_ENABLED=False),
        raising=False,
    )

    assert douyin_color_analytics.collector_config_payload(account_key="account-a")["collection_enabled"] is False
