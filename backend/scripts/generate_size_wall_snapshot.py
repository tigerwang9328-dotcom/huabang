"""Build the idempotent size-wall candidate snapshot."""

import argparse
import asyncio
import json
from datetime import date

from app.core.database import AsyncSessionLocal, engine
from app.services.size_wall_service import SizeWallService


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, help="Optional sales analysis date (YYYY-MM-DD)")
    return parser.parse_args()


async def main(analysis_date: date | None) -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await SizeWallService().build_snapshot(db, analysis_date)
            await db.commit()
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            await db.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.date))
