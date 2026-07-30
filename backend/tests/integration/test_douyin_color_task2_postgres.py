"""Opt-in real PostgreSQL acceptance for the Task 2 ingest state machine.

Run only through ``scripts/run_douyin_color_task2_postgres_acceptance.sh``.
That script refuses production-looking database names before this module imports
the application database configuration.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select, text, update


pytestmark = pytest.mark.skipif(
    os.environ.get("DOUYIN_TASK2_POSTGRES_ACCEPTANCE") != "1",
    reason="requires an explicitly provisioned disposable PostgreSQL database",
)


def _response(analysis_type: int) -> dict[str, object]:
    return {
        "analysis_type": analysis_type,
        "http_status": 200,
        "business_status_code": 0,
        "response_data": {
            "analysis_trend": {"current_item": [{"key": "00:00", "value": 100}]},
            "status_code": 0,
            "status_msg": "not persisted",
        },
    }


def _part_payload(
    *, client_batch_id: str, part_number: int, part_count: int, creator_id: str,
    video_id: str = "7666046377541012755", duplicate_records: bool = True, skip_only: bool = False,
) -> dict[str, object]:
    record = (
        {"video_id": video_id, "source_type": "graphic", "skip_reason": "non_video"}
        if skip_only else {
            "video_id": video_id,
            "source_type": "video",
            "duration_ms": 1_000,
            "retention": _response(1),
            "platform_bounce": _response(7),
        }
    )
    return {
        "schema_version": 1,
        "client_batch_id": client_batch_id,
        "script_version": "3.1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "installation_id": "task2-postgres-acceptance",
        "observed_creator_id": creator_id,
        "part_number": part_number,
        "part_count": part_count,
        "part_hash": (f"{part_number:x}" * 64)[:64],
        "records": [record, record] if duplicate_records and not skip_only else [record],
    }


@pytest.mark.asyncio
async def test_task2_postgres_acceptance_concurrent_part_is_idempotent_and_expiry_commits():
    from app.core.database import AsyncSessionLocal, engine
    from app.main import app
    from app.models.douyin_color_analytics import (
        CollectionBatch,
        CollectionBatchPart,
        CollectionItem,
        DouyinCreatorAccount,
        DouyinUploadToken,
        Video,
        VideoAnalysisSnapshot,
    )
    from app.services.douyin_color_security_service import creator_fingerprint, hash_upload_token

    try:
        async with engine.connect() as connection:
            database_name = (await connection.execute(text("SELECT current_database()"))).scalar_one()
        assert database_name.startswith("huabang_ai_douyin_task2_test"), database_name

        creator_id = f"task2-creator-{uuid.uuid4().hex}"
        client_batch_id = f"task2-{uuid.uuid4().hex[:20]}"
        token_value = f"dyup_{uuid.uuid4().hex}"
        async with AsyncSessionLocal() as db:
            await db.execute(update(DouyinCreatorAccount).where(
                DouyinCreatorAccount.status == "active",
            ).values(status="inactive"))
            account = DouyinCreatorAccount(
                account_key=f"task2-{uuid.uuid4().hex[:20]}",
                display_name="Task 2 PostgreSQL acceptance",
                expected_creator_fingerprint=creator_fingerprint(creator_id),
                status="active",
            )
            db.add(account)
            await db.flush()
            db.add(DouyinUploadToken(
                account_id=account.id,
                token_hash=hash_upload_token(token_value),
                token_prefix=token_value[:12],
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            ))
            await db.commit()
            account_id = account.id

        payload = _part_payload(
            client_batch_id=client_batch_id,
            part_number=1,
            part_count=1,
            creator_id=creator_id,
        )

        async def post_json(path: str, body: bytes | None = None):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://task2.acceptance") as client:
                return await client.post(
                    path,
                    content=body,
                    headers={"authorization": f"Bearer {token_value}", "content-encoding": "gzip"} if body else {
                        "authorization": f"Bearer {token_value}",
                    },
                )

        compressed_payload = gzip.compress(json.dumps(payload).encode("utf-8"))
        initial, retried = await asyncio.gather(
            post_json(f"/api/v1/douyin-color-analytics/collection-batches/{client_batch_id}/parts", compressed_payload),
            post_json(f"/api/v1/douyin-color-analytics/collection-batches/{client_batch_id}/parts", compressed_payload),
        )
        assert initial.status_code == retried.status_code == 200
        assert {initial.json()["data"]["idempotent"], retried.json()["data"]["idempotent"]} == {False, True}

        async with AsyncSessionLocal() as db:
            batch = (await db.execute(select(CollectionBatch).where(
                CollectionBatch.account_id == account_id,
                CollectionBatch.client_batch_id == client_batch_id,
            ))).scalar_one()
            assert batch.item_count == batch.success_count == 2
            assert batch.skipped_count == batch.failure_count == 0
            assert (await db.execute(select(func.count()).select_from(CollectionBatchPart).where(
                CollectionBatchPart.batch_id == batch.id,
            ))).scalar_one() == 1
            assert (await db.execute(select(func.count()).select_from(CollectionItem).where(
                CollectionItem.batch_id == batch.id,
            ))).scalar_one() == 2
            assert (await db.execute(select(func.count()).select_from(Video).where(
                Video.account_id == account_id,
            ))).scalar_one() == 1
            assert (await db.execute(select(func.count()).select_from(VideoAnalysisSnapshot).where(
                VideoAnalysisSnapshot.account_id == account_id,
            ))).scalar_one() == 2

        snapshot_batch_id = f"task2-snapshot-{uuid.uuid4().hex[:16]}"
        snapshot_video_id = "7666046377541012756"
        snapshot_setup_part = _part_payload(
            client_batch_id=snapshot_batch_id,
            part_number=1,
            part_count=3,
            creator_id=creator_id,
            video_id="7666046377541012757",
            duplicate_records=False,
            skip_only=True,
        )
        first_snapshot_part = _part_payload(
            client_batch_id=snapshot_batch_id,
            part_number=2,
            part_count=3,
            creator_id=creator_id,
            video_id=snapshot_video_id,
            duplicate_records=False,
        )
        second_snapshot_part = _part_payload(
            client_batch_id=snapshot_batch_id,
            part_number=3,
            part_count=3,
            creator_id=creator_id,
            video_id=snapshot_video_id,
            duplicate_records=False,
        )
        setup_response = await post_json(
            f"/api/v1/douyin-color-analytics/collection-batches/{snapshot_batch_id}/parts",
            gzip.compress(json.dumps(snapshot_setup_part).encode("utf-8")),
        )
        assert setup_response.status_code == 200
        async with AsyncSessionLocal() as db:
            db.add(Video(
                account_id=account_id,
                video_id_string=snapshot_video_id,
                creator_detail_path=f"/creator-micro/work-management/work-detail/{snapshot_video_id}",
                source_type="video",
                first_collected_at=datetime.now(timezone.utc),
                last_collected_at=datetime.now(timezone.utc),
                collection_status="pending",
            ))
            await db.commit()
        first_part_response, second_part_response = await asyncio.gather(
            post_json(
                f"/api/v1/douyin-color-analytics/collection-batches/{snapshot_batch_id}/parts",
                gzip.compress(json.dumps(first_snapshot_part).encode("utf-8")),
            ),
            post_json(
                f"/api/v1/douyin-color-analytics/collection-batches/{snapshot_batch_id}/parts",
                gzip.compress(json.dumps(second_snapshot_part).encode("utf-8")),
            ),
        )
        assert first_part_response.status_code == second_part_response.status_code == 200
        assert not first_part_response.json()["data"]["idempotent"]
        assert not second_part_response.json()["data"]["idempotent"]

        async with AsyncSessionLocal() as db:
            snapshot_batch = (await db.execute(select(CollectionBatch).where(
                CollectionBatch.account_id == account_id,
                CollectionBatch.client_batch_id == snapshot_batch_id,
            ))).scalar_one()
            assert snapshot_batch.item_count == 5
            assert snapshot_batch.success_count == 4
            assert snapshot_batch.skipped_count == 1
            assert (await db.execute(select(func.count()).select_from(CollectionBatchPart).where(
                CollectionBatchPart.batch_id == snapshot_batch.id,
            ))).scalar_one() == 3
            assert (await db.execute(select(func.count()).select_from(CollectionItem).where(
                CollectionItem.batch_id == snapshot_batch.id,
            ))).scalar_one() == 5
            snapshot_video = (await db.execute(select(Video).where(
                Video.account_id == account_id,
                Video.video_id_string == snapshot_video_id,
            ))).scalar_one()
            assert (await db.execute(select(func.count()).select_from(VideoAnalysisSnapshot).where(
                VideoAnalysisSnapshot.account_id == account_id,
                VideoAnalysisSnapshot.video_id == snapshot_video.id,
            ))).scalar_one() == 2

        async with AsyncSessionLocal() as db:
            expired_batch_id = f"task2-expire-{uuid.uuid4().hex[:16]}"
            expired_payload = _part_payload(
                client_batch_id=expired_batch_id,
                part_number=1,
                part_count=2,
                creator_id=creator_id,
            )
        expired_response = await post_json(
            f"/api/v1/douyin-color-analytics/collection-batches/{expired_batch_id}/parts",
            gzip.compress(json.dumps(expired_payload).encode("utf-8")),
        )
        assert expired_response.status_code == 200

        async with AsyncSessionLocal() as db:
            expired = (await db.execute(select(CollectionBatch).where(
                CollectionBatch.account_id == account_id,
                CollectionBatch.client_batch_id == expired_batch_id,
            ))).scalar_one()
            expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await db.commit()

        response = await post_json(f"/api/v1/douyin-color-analytics/collection-batches/{expired_batch_id}/finalize")
        assert response.status_code == 409
        assert response.json()["message"] == "batch_expired"

        async with AsyncSessionLocal() as db:
            persisted = (await db.execute(select(CollectionBatch).where(
                CollectionBatch.account_id == account_id,
                CollectionBatch.client_batch_id == expired_batch_id,
            ))).scalar_one()
            assert persisted.status == "expired"
    finally:
        await engine.dispose()
