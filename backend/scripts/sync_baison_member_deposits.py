"""Backfill or refresh Baison member stored-value logs in monthly windows."""

import argparse
import asyncio
import calendar
import json
from datetime import date, timedelta

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.integrations.baison.services.member_deposit_service import sync_member_deposits


def parse_args():
    today = date.today()
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=date.fromisoformat, default=today - timedelta(days=13))
    parser.add_argument("--end-date", type=date.fromisoformat, default=today)
    return parser.parse_args()


def monthly_windows(start_date: date, end_date: date):
    cursor = start_date
    while cursor <= end_date:
        month_end = date(cursor.year, cursor.month, calendar.monthrange(cursor.year, cursor.month)[1])
        window_end = min(month_end, end_date)
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


async def main(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise ValueError("start date must not be after end date")
    fetched = 0
    windows = 0
    async with AsyncSessionLocal() as db:
        try:
            for window_start, window_end in monthly_windows(start_date, end_date):
                result = await sync_member_deposits(db, window_start, window_end)
                await db.commit()
                fetched += result["log_count"]
                windows += 1
            row = (await db.execute(text("""
              SELECT count(*) detail_count,
                     count(*) FILTER (WHERE change_type='0') recharge_count,
                     coalesce(sum(money_change) FILTER (WHERE change_type='0'),0) recharge_amount,
                     min(biz_date) first_date, max(biz_date) last_date,
                     array_agg(DISTINCT store_code ORDER BY store_code) stores
              FROM dwd.dwd_baison_member_deposit_log
            """))).mappings().one()
            print(json.dumps({
                "ok": True, "windows": windows, "fetched": fetched,
                "detail_count": int(row["detail_count"]),
                "recharge_count": int(row["recharge_count"]),
                "recharge_amount": float(row["recharge_amount"]),
                "first_date": str(row["first_date"] or ""),
                "last_date": str(row["last_date"] or ""),
                "stores": row["stores"] or [],
            }, ensure_ascii=False))
        except Exception:
            await db.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.start_date, args.end_date))
