"""Run one Baison member profile synchronization."""

import asyncio
import json

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.integrations.baison.services.member_service import rebuild_member_visits, sync_members
from app.services.member_segment_service import rebuild_member_segments


async def main() -> None:
    async with AsyncSessionLocal() as db:
        try:
            sync_result = await sync_members(db)
            visit_result = await rebuild_member_visits(db, limit_per_store=50)
            segment_result = await rebuild_member_segments(db)
            await db.commit()
            counts = (
                await db.execute(text("""
                    SELECT
                      (SELECT COUNT(*) FROM ods.ods_baison_member) AS ods_count,
                      (SELECT COUNT(*) FROM dim.dim_member) AS dim_count
                """))
            ).mappings().one()
            result = {
                "fetched": sync_result["member_count"],
                "members": sync_result["member_count"],
                "batch_no": sync_result["batch_no"],
                "visit_count": visit_result["visit_count"],
                "segment_member_count": segment_result.get("member_count", 0),
                "segment_risk_count": segment_result.get("risk_count", 0),
                "segment_wakeup_count": segment_result.get("wakeup_count", 0),
                "ods_count": int(counts["ods_count"]),
                "dim_count": int(counts["dim_count"]),
            }
            print(json.dumps(result, ensure_ascii=False))
        except Exception:
            await db.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
