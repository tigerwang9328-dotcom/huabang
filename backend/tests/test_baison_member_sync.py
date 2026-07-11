import pytest
from datetime import date
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.api.v1 import member as member_api
from app.integrations.baison.services import member_service


@pytest.mark.asyncio
async def test_sync_members_upserts_normalized_profile_without_committing():
    await engine.dispose()
    assert hasattr(member_service, "sync_members")
    sync_members = member_service.sync_members
    raw = {
        "DM": "TEST-CODEX-MEMBER",
        "MC": "测试会员",
        "SJ": "13800000000",
        "CKDM": "285204",
        "XFJE": "123.45",
        "XFCS": "2",
        "ZJRQ": "2026-07-01",
        "STATUS": "1",
    }

    async with AsyncSessionLocal() as db:
        result = await sync_members(db, members=[member_service.normalize_member(raw)])
        row = (await db.execute(text("""
            SELECT member_no, total_amount, total_count, status
            FROM dim.dim_member
            WHERE member_no = 'TEST-CODEX-MEMBER'
        """))).mappings().one()
        await db.rollback()
    await engine.dispose()
    assert result["ok"] is True
    assert result["member_count"] == 1
    assert row["member_no"] == "TEST-CODEX-MEMBER"
    assert float(row["total_amount"]) == 123.45
    assert row["total_count"] == 2
    assert row["status"] == "active"


@pytest.mark.asyncio
async def test_rebuild_member_visits_generates_sleeping_member_task():
    await engine.dispose()
    assert hasattr(member_service, "rebuild_member_visits")
    rebuild_member_visits = member_service.rebuild_member_visits
    sleeping = member_service.normalize_member({
        "DM": "TEST-CODEX-SLEEPING",
        "MC": "沉睡测试会员",
        "CKDM": "TEST_STORE",
        "XFJE": "999.00",
        "XFCS": "3",
        "ZJRQ": "2025-01-01",
        "STATUS": "1",
    })

    async with AsyncSessionLocal() as db:
        await member_service.sync_members(db, members=[sleeping])
        result = await rebuild_member_visits(
            db,
            store_codes=["TEST_STORE"],
            limit_per_store=1,
        )
        row = (await db.execute(text("""
            SELECT member_no, store_code, visit_status, sleep_days
            FROM dm.dm_member_visit_list
            WHERE visit_date = CURRENT_DATE
              AND member_no = 'TEST-CODEX-SLEEPING'
        """))).mappings().one()
        await db.rollback()
    await engine.dispose()
    assert result["visit_count"] == 1
    assert row["store_code"] == "TEST_STORE"
    assert row["visit_status"] == "pending"
    assert row["sleep_days"] > 90


@pytest.mark.asyncio
async def test_pos_member_base_sql_compiles_against_postgres():
    await engine.dispose()
    assert hasattr(member_api, "POS_MEMBER_BASE_SQL")
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("EXPLAIN " + member_api.POS_MEMBER_BASE_SQL + " SELECT COUNT(*) FROM grouped"),
            {
                "store_codes": ["285204"],
                "sd": date(2026, 7, 9),
                "ed": date(2026, 7, 9),
                "kw": "",
            },
        )
        await db.rollback()
    await engine.dispose()
