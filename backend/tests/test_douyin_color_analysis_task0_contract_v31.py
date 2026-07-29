"""v3.1-only Task 0 contract proof for the color-analysis upload design.

This isolated proof intentionally does not import the legacy v3.2 outfit POC,
production models, migrations, or application routers.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.poc.douyin_color_analysis_task0_contract import create_v31_contract_app


ACCOUNT_A_HEADERS = {"Authorization": "Bearer color-token-a"}
ACCOUNT_B_HEADERS = {"Authorization": "Bearer color-token-b"}
ACCOUNT_A = "color-account-a"
VIDEO_ID = "7666046377541012755"


@pytest.fixture
def client() -> TestClient:
    app = create_v31_contract_app()
    with TestClient(app) as test_client:
        yield test_client


def _part(
    *,
    client_batch_id: str,
    part_number: int,
    part_count: int = 3,
    observed_creator_id: str = "creator-a",
    records: list[dict] | None = None,
) -> dict:
    return {
        "client_batch_id": client_batch_id,
        "part_number": part_number,
        "part_count": part_count,
        "schema_version": "v3.1-task0-contract",
        "observed_creator_id": observed_creator_id,
        "records": records
        if records is not None
        else [
            {
                "video_id": VIDEO_ID,
                "analysis_type": 1,
                "source_snapshot_hash": "snapshot-1",
            }
        ],
    }


def test_v31_token_context_owns_account_and_creator_identity(client: TestClient):
    forbidden = _part(client_batch_id="identity", part_number=1)
    forbidden["account_id"] = "color-account-b"
    response = client.post("/task0/douyin-color-v31/parts", json=forbidden, headers=ACCOUNT_A_HEADERS)
    assert response.status_code == 400
    assert response.json()["detail"] == "client_account_id_forbidden"

    nested_forbidden = _part(client_batch_id="nested-identity", part_number=1)
    nested_forbidden["records"][0]["account_id"] = "color-account-b"
    nested_response = client.post(
        "/task0/douyin-color-v31/parts",
        json=nested_forbidden,
        headers=ACCOUNT_A_HEADERS,
    )
    assert nested_response.status_code == 400
    assert nested_response.json()["detail"] == "client_account_id_forbidden"

    mismatch = client.post(
        "/task0/douyin-color-v31/parts",
        json=_part(
            client_batch_id="creator-mismatch",
            part_number=1,
            observed_creator_id="creator-b",
        ),
        headers=ACCOUNT_A_HEADERS,
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"] == "observed_creator_mismatch"

    accepted = client.post(
        "/task0/douyin-color-v31/parts",
        json=_part(client_batch_id="identity", part_number=1),
        headers=ACCOUNT_A_HEADERS,
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["account_id"] == ACCOUNT_A


def test_v31_rejects_cross_account_style_and_color_references(client: TestClient):
    style = client.post(
        "/task0/douyin-color-v31/styles",
        json={"style_code": "STYLE-A"},
        headers=ACCOUNT_A_HEADERS,
    ).json()["data"]
    color = client.post(
        "/task0/douyin-color-v31/colors",
        json={"style_id": style["id"], "color_code": "BLACK"},
        headers=ACCOUNT_A_HEADERS,
    ).json()["data"]

    cross_account = _part(
        client_batch_id="cross-account",
        part_number=1,
        part_count=1,
        observed_creator_id="creator-b",
        records=[
            {
                "video_id": VIDEO_ID,
                "analysis_type": 1,
                "source_snapshot_hash": "snapshot-b",
                "style_id": style["id"],
                "color_id": color["id"],
            }
        ],
    )
    response = client.post(
        "/task0/douyin-color-v31/parts",
        json=cross_account,
        headers=ACCOUNT_B_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "style_account_mismatch"


def test_v31_snapshot_dedup_and_nullable_item_unique_semantics(client: TestClient):
    first = client.post(
        "/task0/douyin-color-v31/parts",
        json=_part(client_batch_id="snapshot-a", part_number=1, part_count=1),
        headers=ACCOUNT_A_HEADERS,
    )
    second = client.post(
        "/task0/douyin-color-v31/parts",
        json=_part(client_batch_id="snapshot-b", part_number=1, part_count=1),
        headers=ACCOUNT_A_HEADERS,
    )
    assert first.status_code == second.status_code == 200

    null_hash_items = client.post(
        "/task0/douyin-color-v31/parts",
        json=_part(
            client_batch_id="nullable-items",
            part_number=1,
            part_count=1,
            records=[
                {"item_status": "network_failed"},
                {"item_status": "network_failed"},
            ],
        ),
        headers=ACCOUNT_A_HEADERS,
    )
    assert null_hash_items.status_code == 200

    state = client.get("/task0/douyin-color-v31/contract-state", headers=ACCOUNT_A_HEADERS)
    assert state.status_code == 200
    assert state.json()["data"] == {
        "snapshot_count": 1,
        "snapshot_reference_count": 2,
        "null_raw_record_hash_item_count": 2,
    }


def test_v31_parts_are_ordered_idempotent_and_finalize_with_server_hash(client: TestClient):
    batch = "ordered-parts"
    part_two = _part(client_batch_id=batch, part_number=2)
    first_two = client.post("/task0/douyin-color-v31/parts", json=part_two, headers=ACCOUNT_A_HEADERS)
    assert first_two.status_code == 200
    retry_two = client.post("/task0/douyin-color-v31/parts", json=part_two, headers=ACCOUNT_A_HEADERS)
    assert retry_two.status_code == 200
    assert retry_two.json()["data"]["idempotent"] is True

    conflicting = _part(client_batch_id=batch, part_number=2)
    conflicting["records"][0]["source_snapshot_hash"] = "different-part-content"
    conflict = client.post("/task0/douyin-color-v31/parts", json=conflicting, headers=ACCOUNT_A_HEADERS)
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "part_content_conflict"

    count_conflict = client.post(
        "/task0/douyin-color-v31/parts",
        json=_part(client_batch_id=batch, part_number=1, part_count=4),
        headers=ACCOUNT_A_HEADERS,
    )
    assert count_conflict.status_code == 409
    assert count_conflict.json()["detail"] == "part_count_conflict"

    missing = client.get(
        f"/task0/douyin-color-v31/collection-batches/{batch}/missing-parts",
        headers=ACCOUNT_A_HEADERS,
    )
    assert missing.json()["data"]["missing_part_numbers"] == [1, 3]
    incomplete = client.post(
        f"/task0/douyin-color-v31/collection-batches/{batch}/finalize",
        headers=ACCOUNT_A_HEADERS,
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"] == "missing_parts"

    part_one = _part(client_batch_id=batch, part_number=1)
    part_three = _part(client_batch_id=batch, part_number=3)
    assert client.post("/task0/douyin-color-v31/parts", json=part_one, headers=ACCOUNT_A_HEADERS).status_code == 200
    assert client.post("/task0/douyin-color-v31/parts", json=part_three, headers=ACCOUNT_A_HEADERS).status_code == 200

    finalized = client.post(
        f"/task0/douyin-color-v31/collection-batches/{batch}/finalize",
        headers=ACCOUNT_A_HEADERS,
    )
    expected_hash = hashlib.sha256(
        "|".join(
            hashlib.sha256(
                json.dumps(part, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            for part in (part_one, part_two, part_three)
        ).encode()
    ).hexdigest()
    assert finalized.status_code == 200
    assert finalized.json()["data"] == {
        "status": "completed",
        "batch_hash": expected_hash,
        "account_id": ACCOUNT_A,
    }
