"""Opt-in real PostgreSQL acceptance for Task 4 annotation invariants.

Run only through ``scripts/run_douyin_color_task4_postgres_acceptance.sh``.
The runner accepts only an explicitly pre-provisioned isolated database at the
current Alembic head; it never reuses a production database.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError


pytestmark = pytest.mark.skipif(
    os.environ.get("DOUYIN_TASK4_POSTGRES_ACCEPTANCE") != "1",
    reason="requires an explicitly provisioned disposable PostgreSQL database",
)


def _account(*, status: str, suffix: str):
    from app.models.douyin_color_analytics import DouyinCreatorAccount

    return DouyinCreatorAccount(
        account_key=f"task4-{suffix}",
        display_name="Task 4 PostgreSQL acceptance",
        expected_creator_fingerprint=uuid.uuid4().hex,
        status=status,
    )


async def _seed_annotation_records(db, *, account_id: int, suffix: str):
    from app.models.douyin_color_analytics import GarmentColor, GarmentStyle, Video

    now = datetime.now(timezone.utc)
    style = GarmentStyle(
        account_id=account_id,
        style_code=f"T4-{suffix}",
        style_name="Task 4 style",
        status="active",
    )
    db.add(style)
    await db.flush()
    first_color = GarmentColor(
        account_id=account_id,
        style_id=style.id,
        color_code=f"A-{suffix}",
        color_name="Color A",
        status="active",
    )
    second_color = GarmentColor(
        account_id=account_id,
        style_id=style.id,
        color_code=f"B-{suffix}",
        color_name="Color B",
        status="active",
    )
    video = Video(
        account_id=account_id,
        video_id_string=f"task4-video-{suffix}",
        creator_detail_path=f"/creator-micro/work-management/work-detail/task4-{suffix}",
        source_type="video",
        duration_ms=10_000,
        first_collected_at=now,
        last_collected_at=now,
        collection_status="pending",
    )
    db.add_all([first_color, second_color, video])
    await db.flush()
    return style, first_color, second_color, video


def _clip_payload(*, account_id: int, video_id: int, style_id: int, color_id: int, start_ms: int, end_ms: int):
    from app.schemas.douyin_color_analytics import VideoClipCreateRequest

    return VideoClipCreateRequest(
        account_id=account_id,
        video_id=video_id,
        style_id=style_id,
        color_id=color_id,
        input_start_ms=start_ms,
        input_end_ms=end_ms,
        curve_resolution_ms=1_000,
        focus_status="clear_primary",
    )


@pytest.mark.asyncio
async def test_task4_postgres_annotation_scope_locking_and_audit_rollback():
    from app.api.v1.douyin_color_annotation_routes import (
        _annotation_account,
        _request_account,
        create_video_clip,
    )
    from app.core.database import AsyncSessionLocal, engine
    from app.models.douyin_color_analytics import VideoClip
    from app.models.sys import SysOperationLog

    suffix = uuid.uuid4().hex[:12]
    actor = type("Task4Actor", (), {"id": 900_001, "username": "task4-postgres"})()
    try:
        async with engine.connect() as connection:
            database_name = (await connection.execute(text("SELECT current_database()"))).scalar_one()
        assert database_name.startswith("huabang_ai_douyin_task4_test_"), database_name

        async with AsyncSessionLocal() as db:
            active = _account(status="active", suffix=f"active-{suffix}")
            inactive = _account(status="inactive", suffix=f"inactive-{suffix}")
            db.add_all([active, inactive])
            await db.commit()
            active_account_id, inactive_account_id = active.id, inactive.id

        async with AsyncSessionLocal() as db:
            assert (await _annotation_account(db)).id == active_account_id
            with pytest.raises(HTTPException) as mismatch:
                await _request_account(db, query_account_id=inactive_account_id)
            assert mismatch.value.status_code == 403
            assert mismatch.value.detail == "account_scope_mismatch"

        async with AsyncSessionLocal() as setup_db:
            style, color_a, color_b, video = await _seed_annotation_records(
                setup_db, account_id=active_account_id, suffix=suffix,
            )
            await setup_db.commit()
            style_id, color_a_id, color_b_id, video_id = style.id, color_a.id, color_b.id, video.id

        first_payload = _clip_payload(
            account_id=active_account_id, video_id=video_id, style_id=style_id,
            color_id=color_a_id, start_ms=1_000, end_ms=4_000,
        )
        second_payload = _clip_payload(
            account_id=active_account_id, video_id=video_id, style_id=style_id,
            color_id=color_b_id, start_ms=2_000, end_ms=5_000,
        )
        async with AsyncSessionLocal() as first_db:
            await create_video_clip(first_payload, request=None, current_user=actor, db=first_db)

            async def create_second_clip():
                async with AsyncSessionLocal() as second_db:
                    response = await create_video_clip(
                        second_payload, request=None, current_user=actor, db=second_db,
                    )
                    await second_db.commit()
                    return response

            second_task = asyncio.create_task(create_second_clip())
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(second_task), timeout=0.25)
            await first_db.commit()
            second_response = await asyncio.wait_for(second_task, timeout=5)
        assert second_response.data["overlap_status"] == "pending_approval"

        async with AsyncSessionLocal() as db:
            clip_statuses = (await db.execute(select(VideoClip.overlap_status).where(
                VideoClip.account_id == active_account_id,
                VideoClip.video_id == video_id,
            ))).scalars().all()
            assert sorted(clip_statuses) == ["not_required", "pending_approval"]
            audit_count_before_failure = (await db.execute(
                select(func.count()).select_from(SysOperationLog).where(
                    SysOperationLog.action == "create_video_clip",
                )
            )).scalar_one()

        async with engine.begin() as connection:
            await connection.execute(text("""
                CREATE OR REPLACE FUNCTION sys.task4_reject_operation_log() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'task4_audit_write_failure'; END; $$
            """))
            await connection.execute(text("""
                CREATE TRIGGER task4_reject_operation_log_before_insert
                BEFORE INSERT ON sys.sys_operation_log
                FOR EACH ROW EXECUTE FUNCTION sys.task4_reject_operation_log()
            """))

        async with AsyncSessionLocal() as setup_db:
            rollback_style, rollback_color_a, _, rollback_video = await _seed_annotation_records(
                setup_db, account_id=active_account_id, suffix=f"rollback-{suffix}",
            )
            await setup_db.commit()
            rollback_style_id, rollback_color_id, rollback_video_id = (
                rollback_style.id, rollback_color_a.id, rollback_video.id,
            )

        async with AsyncSessionLocal() as db:
            failing_payload = _clip_payload(
                account_id=active_account_id, video_id=rollback_video_id, style_id=rollback_style_id,
                color_id=rollback_color_id, start_ms=0, end_ms=1_000,
            )
            with pytest.raises(DBAPIError, match="task4_audit_write_failure"):
                await create_video_clip(failing_payload, request=None, current_user=actor, db=db)
            await db.rollback()

        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(func.count()).select_from(VideoClip).where(
                VideoClip.account_id == active_account_id,
                VideoClip.video_id == rollback_video_id,
            ))).scalar_one() == 0
            assert (await db.execute(select(func.count()).select_from(SysOperationLog).where(
                SysOperationLog.action == "create_video_clip",
            ))).scalar_one() == audit_count_before_failure
    finally:
        await engine.dispose()
