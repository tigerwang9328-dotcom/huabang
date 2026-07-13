import asyncio,json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.core.database import AsyncSessionLocal,engine
from app.integrations.baison.services.store_target_service import sync_store_targets
async def main():
    now=datetime.now(ZoneInfo("Asia/Shanghai"))
    async with AsyncSessionLocal() as db:
        try:
            result=await sync_store_targets(db,now.year,now.month,snapshot_date=now.date()-timedelta(days=1));await db.commit();print(json.dumps(result,ensure_ascii=False))
        except Exception: await db.rollback();raise
        finally: await engine.dispose()
if __name__=="__main__": asyncio.run(main())
