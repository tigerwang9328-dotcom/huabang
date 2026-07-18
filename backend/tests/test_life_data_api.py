"""Tests for the token-authenticated life-data ingest endpoint."""

import hashlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1 import life_data
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.schemas.life_data import (
    LifeDataCollectorStatusRequest,
    LifeDataIngestRequest,
)


PATH = "/api/v1/life-data/ingest"
STATUS_PATH = "/api/v1/life-data/status"
ACCOUNT_ID = "1798826701211732"
VALID_TOKEN = "collector-secret"


def payload(**overrides):
    body = {
        "schema_version": "1.0",
        "event_id": "event-20260712-0001",
        "account_id": ACCOUNT_ID,
        "page_path": "/flow/content/analysis/video",
        "endpoint": "/api/dito/query",
        "request_payload": {"offset": 0, "limit": 100},
        "response_payload": {
            "code": 0,
            "data": {
                "itemRank": {
                    "data": [{"item_id": "video-1", "item_play_cnt": 2_001}]
                }
            },
        },
        "captured_at": "2026-07-12T01:02:03Z",
    }
    body.update(overrides)
    return body


def status_payload(**overrides):
    body = {
        "schema_version": "1.0",
        "account_id": ACCOUNT_ID,
        "status": "online",
        "queue_depth": 0,
        "last_error": None,
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def isolate_ingest_dependencies(monkeypatch):
    """Keep API tests independent from PostgreSQL and Task 2 internals."""

    async def override_get_db():
        yield object()

    app.dependency_overrides[get_db] = override_get_db

    monkeypatch.setattr(
        settings,
        "LIFE_DATA_COLLECTOR_TOKEN_SHA256",
        hashlib.sha256(VALID_TOKEN.encode()).hexdigest(),
    )
    monkeypatch.setattr(settings, "LIFE_DATA_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setattr(settings, "LIFE_DATA_MAX_PAYLOAD_BYTES", 2_000_000)

    redis = SimpleNamespace(eval=AsyncMock(return_value=1))

    async def fake_get_redis():
        return redis

    monkeypatch.setattr(life_data, "get_redis", fake_get_redis, raising=False)

    async def fake_ingest(self, db, body):
        assert self.task_creator_id == settings.LIFE_DATA_TASK_CREATOR_ID
        assert self.alert_threshold == 2_000
        assert body.account_id == ACCOUNT_ID
        return SimpleNamespace(
            duplicate=False,
            videos_seen=1,
            snapshots_created=1,
            tasks_created=1,
        )

    monkeypatch.setattr(
        life_data.LifeDataIngestService,
        "ingest",
        fake_ingest,
    )

    async def fake_update_status(self, db, body):
        assert self.task_creator_id == settings.LIFE_DATA_TASK_CREATOR_ID
        assert body.account_id == ACCOUNT_ID

    monkeypatch.setattr(
        life_data.LifeDataIngestService,
        "update_status",
        fake_update_status,
        raising=False,
    )

    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def valid_token():
    return VALID_TOKEN


def test_ingest_rejects_missing_token(client):
    response = client.post(PATH, json=payload())

    assert response.status_code == 401


def test_ingest_rejects_unconfigured_token(client, valid_token, monkeypatch):
    monkeypatch.setattr(settings, "LIFE_DATA_COLLECTOR_TOKEN_SHA256", "")

    response = client.post(
        PATH,
        json=payload(),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 503


def test_ingest_rejects_invalid_token(client):
    response = client.post(
        PATH,
        json=payload(),
        headers={"X-Collector-Token": "wrong-token"},
    )

    assert response.status_code == 401


def test_ingest_rejects_wrong_account(client, valid_token):
    response = client.post(
        PATH,
        json=payload(account_id="wrong"),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 403


def test_ingest_accepts_valid_business_json(client, valid_token):
    response = client.post(
        PATH,
        json=payload(),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "duplicate": False,
        "videos_seen": 1,
        "snapshots_created": 1,
        "tasks_created": 1,
    }


def test_ingest_rejects_payload_over_configured_limit(client, valid_token):
    response = client.post(
        PATH,
        json=payload(response_payload={"blob": "x" * 2_000_001}),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 413


def test_ingest_rejects_raw_content_length_above_exact_limit(
    client,
    valid_token,
    monkeypatch,
):
    monkeypatch.setattr(settings, "LIFE_DATA_MAX_PAYLOAD_BYTES", 512)
    encoded = json.dumps(payload(), separators=(",", ":")).encode("utf-8")

    response = client.post(
        PATH,
        content=encoded,
        headers={
            "Content-Type": "application/json",
            "Content-Length": "513",
            "X-Collector-Token": valid_token,
        },
    )

    assert response.status_code == 413


def test_ingest_allows_raw_content_length_at_exact_limit(
    client,
    valid_token,
    monkeypatch,
):
    encoded = json.dumps(payload(), separators=(",", ":")).encode("utf-8")
    monkeypatch.setattr(settings, "LIFE_DATA_MAX_PAYLOAD_BYTES", len(encoded))

    response = client.post(
        PATH,
        content=encoded,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(encoded)),
            "X-Collector-Token": valid_token,
        },
    )

    assert response.status_code == 200


def test_ingest_rate_limit_uses_atomic_redis_script_and_fixed_account_key(
    client,
    valid_token,
    monkeypatch,
):
    redis = SimpleNamespace(eval=AsyncMock(return_value=60))

    async def fake_get_redis():
        return redis

    monkeypatch.setattr(life_data, "get_redis", fake_get_redis, raising=False)

    response = client.post(
        PATH,
        json=payload(),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 200
    redis.eval.assert_awaited_once()
    script, key_count, key, window_seconds = redis.eval.await_args.args
    assert "INCR" in script
    assert "EXPIRE" in script
    assert key_count == 1
    assert key == f"rate_limit:life_data_ingest:{ACCOUNT_ID}"
    assert window_seconds == 60


def test_ingest_rate_limit_rejects_request_61(client, valid_token, monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(return_value=61))

    async def fake_get_redis():
        return redis

    monkeypatch.setattr(life_data, "get_redis", fake_get_redis, raising=False)

    response = client.post(
        PATH,
        json=payload(),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 429


def test_ingest_rate_limit_fails_open_without_logging_token(
    client,
    valid_token,
    monkeypatch,
    caplog,
):
    redis = SimpleNamespace(
        eval=AsyncMock(side_effect=RuntimeError(f"redis down: {valid_token}"))
    )

    async def fake_get_redis():
        return redis

    monkeypatch.setattr(life_data, "get_redis", fake_get_redis, raising=False)

    with caplog.at_level(logging.WARNING, logger=life_data.__name__):
        response = client.post(
            PATH,
            json=payload(),
            headers={"X-Collector-Token": valid_token},
        )

    assert response.status_code == 200
    redis.eval.assert_awaited_once()
    assert valid_token not in caplog.text


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"event_id": "too-short"},
        {"endpoint": "/api/msg/query"},
        {"request_payload": []},
        {"response_payload": []},
        {"authorization": "must-not-be-accepted"},
    ],
)
def test_ingest_rejects_invalid_schema(client, valid_token, invalid_fields):
    response = client.post(
        PATH,
        json=payload(**invalid_fields),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 400
    assert response.json()["success"] is False


@pytest.mark.parametrize(
    "field_name,sensitive_payload",
    [
        ("request_payload", {"nested": {"Authorization": "secret"}}),
        ("response_payload", {"items": [{"COOKIE": "secret"}]}),
        ("response_payload", {"headers": {"set_cookie": "secret"}}),
        ("request_payload", {"headers": {"x_tt_ls_session_id": "secret"}}),
        ("response_payload", {"root-life-account-id": "secret"}),
        ("request_payload", {"life-account-id": "secret"}),
    ],
)
def test_schema_rejects_nested_sensitive_session_fields(
    field_name,
    sensitive_payload,
):
    with pytest.raises(ValidationError):
        LifeDataIngestRequest.model_validate(
            payload(**{field_name: sensitive_payload})
        )


def test_schema_allows_business_life_account_id_field():
    body = LifeDataIngestRequest.model_validate(
        payload(request_payload={"life_account_id": "7319301636050913280"})
    )

    assert body.request_payload["life_account_id"] == "7319301636050913280"


@pytest.mark.parametrize("schema_version", ["1", "1.1", "2.0"])
def test_schema_rejects_unsupported_schema_version(schema_version):
    with pytest.raises(ValidationError):
        LifeDataIngestRequest.model_validate(payload(schema_version=schema_version))


@pytest.mark.parametrize("response_code", [None, -1, 1, "0", False])
def test_schema_requires_exact_success_response_code(response_code):
    response_payload = payload()["response_payload"]
    response_payload["code"] = response_code

    with pytest.raises(ValidationError):
        LifeDataIngestRequest.model_validate(
            payload(response_payload=response_payload)
        )


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"item_id": "missing-play-count"}],
        [{"item_play_cnt": 2_001}],
        ["not-an-object"],
    ],
)
def test_schema_requires_valid_item_rank_row_for_video_page(rows):
    response_payload = {"code": 0, "data": {"itemRank": {"data": rows}}}

    with pytest.raises(ValidationError):
        LifeDataIngestRequest.model_validate(
            payload(response_payload=response_payload)
        )


def test_schema_allows_non_video_page_without_item_rank_rows():
    body = LifeDataIngestRequest.model_validate(
        payload(
            page_path="/trade/overview",
            response_payload={"code": 0, "data": {"overview": {"gmv": 39810}}},
        )
    )

    assert body.page_path == "/trade/overview"


def test_schema_rejects_sensitive_key_in_deep_json_without_recursion_error():
    nested = {"authorization": "secret"}
    for _ in range(1_100):
        nested = {"nested": nested}

    with pytest.raises(ValidationError):
        LifeDataIngestRequest.model_validate(payload(request_payload=nested))


def test_status_accepts_online_heartbeat(client, valid_token):
    response = client.post(
        STATUS_PATH,
        json=status_payload(queue_depth=3),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"accepted": True}


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        (status_payload(account_id="wrong"), 403),
        (status_payload(), 401),
    ],
)
def test_status_enforces_fixed_account_and_token(
    client,
    valid_token,
    body,
    expected_status,
):
    headers = {} if expected_status == 401 else {"X-Collector-Token": valid_token}

    response = client.post(STATUS_PATH, json=body, headers=headers)

    assert response.status_code == expected_status


def test_status_reuses_content_limit(client, valid_token, monkeypatch):
    monkeypatch.setattr(settings, "LIFE_DATA_MAX_PAYLOAD_BYTES", 64)

    response = client.post(
        STATUS_PATH,
        json=status_payload(last_error="x" * 50),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 413


def test_status_reuses_redis_rate_limit(client, valid_token, monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(return_value=61))

    async def fake_get_redis():
        return redis

    monkeypatch.setattr(life_data, "get_redis", fake_get_redis, raising=False)

    response = client.post(
        STATUS_PATH,
        json=status_payload(),
        headers={"X-Collector-Token": valid_token},
    )

    assert response.status_code == 429


@pytest.mark.parametrize(
    "invalid_body",
    [
        status_payload(status="error", last_error=None),
        status_payload(status="error", last_error="   "),
        status_payload(status="offline"),
        status_payload(queue_depth=-1),
        status_payload(queue_depth=501),
        status_payload(last_error="x" * 501),
        status_payload(extra_field="forbidden"),
        status_payload(schema_version="1.1"),
    ],
)
def test_status_schema_rejects_invalid_contract(invalid_body):
    with pytest.raises(ValidationError):
        LifeDataCollectorStatusRequest.model_validate(invalid_body)


def test_status_schema_requires_error_text_and_allows_online_without_it():
    error = LifeDataCollectorStatusRequest.model_validate(
        status_payload(status="error", queue_depth=7, last_error="network timeout")
    )
    online = LifeDataCollectorStatusRequest.model_validate(status_payload())

    assert error.last_error == "network timeout"
    assert online.last_error is None


def test_ingest_and_status_schema_accept_full_collector_queue_depth():
    ingest = LifeDataIngestRequest.model_validate(
        payload(queue_depth=500)
    )
    status = LifeDataCollectorStatusRequest.model_validate(
        status_payload(queue_depth=500)
    )

    assert ingest.queue_depth == 500
    assert status.queue_depth == 500


def test_status_schema_accepts_bounded_group_health():
    body = LifeDataCollectorStatusRequest.model_validate(
        status_payload(
            template_count=7,
            last_full_success_at="2026-07-13T03:22:07Z",
            groups={
                "video": {
                    "status": "healthy",
                    "template_count": 1,
                    "last_success_at": "2026-07-13T03:22:07Z",
                    "last_error": None,
                },
                "advertising": {
                    "status": "missing",
                    "template_count": 0,
                    "last_success_at": None,
                    "last_error": None,
                },
            },
        )
    )

    assert body.template_count == 7
    assert body.groups["video"].status == "healthy"


def test_status_schema_rejects_unknown_group_name():
    with pytest.raises(ValidationError):
        LifeDataCollectorStatusRequest.model_validate(
            status_payload(
                groups={
                    "unknown": {
                        "status": "healthy",
                        "template_count": 1,
                    }
                }
            )
        )
