"""Generate the idempotent daily boss command-center snapshot."""

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.store_whitelist import ALLOWED_INVENTORY_CODES
from app.core.database import AsyncSessionLocal, engine
from app.services.command_center_service import run_daily_command_center


MEMBER_BALANCE_CHECK_SQL = """
    SELECT COUNT(*) AS member_count,
           COUNT(*) FILTER (WHERE current_balance < 0) AS negative_count,
           COALESCE(SUM(current_balance) FILTER (WHERE current_balance > 0), 0) AS positive_balance
    FROM dim.dim_member
    WHERE UPPER(register_store)=ANY(:codes)
      AND COALESCE(status,'active')='active'
"""


def member_balance_check_params() -> dict[str, list[str]]:
    return {"codes": sorted(ALLOWED_INVENTORY_CODES)}


def parse_args() -> argparse.Namespace:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str((now - timedelta(days=1)).date()))
    parser.add_argument("--inventory-date", default=str(now.date()))
    parser.add_argument("--creator-id", type=int, default=1)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    report_date = date.fromisoformat(args.date)
    inventory_date = date.fromisoformat(args.inventory_date)
    async with AsyncSessionLocal() as db:
        try:
            result = await run_daily_command_center(
                db,
                report_date=report_date,
                inventory_date=inventory_date,
                creator_id=args.creator_id,
            )
            balances = (
                await db.execute(text(MEMBER_BALANCE_CHECK_SQL), member_balance_check_params())
            ).mappings().one()
            result["member_balance_check"] = {
                "member_count": int(balances["member_count"] or 0),
                "negative_count": int(balances["negative_count"] or 0),
                "positive_balance": float(balances["positive_balance"] or 0),
            }
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            await db.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
