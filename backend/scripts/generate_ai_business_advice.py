"""Generate the 72 company/store module AI business-advice snapshots."""
import argparse
import asyncio
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.database import AsyncSessionLocal, engine
from app.services.ai_business_advice_service import run_business_advice_batch


def parse_args() -> argparse.Namespace:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str((now - timedelta(days=1)).date()))
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with AsyncSessionLocal() as db:
        try:
            result = await run_business_advice_batch(db, date.fromisoformat(args.date))
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            await db.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
