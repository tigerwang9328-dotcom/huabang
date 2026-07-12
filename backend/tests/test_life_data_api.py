"""Tests for the token-authenticated life-data ingest endpoint."""

import hashlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1 import life_data
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.schemas.life_data import LifeDataIngestRequest


PATH = "/api/v1/life-data/ingest"
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
            "data": {"itemRank": {"data": [{"item_id": "video-1"}]}},
        },
        "captured_at": "2026-07-12T01:02:03Z",
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


def test_schema_rejects_sensitive_key_in_deep_json_without_recursion_error():
    nested = {"authorization": "secret"}
    for _ in range(1_100):
        nested = {"nested": nested}

    with pytest.raises(ValidationError):
        LifeDataIngestRequest.model_validate(payload(request_payload=nested))
