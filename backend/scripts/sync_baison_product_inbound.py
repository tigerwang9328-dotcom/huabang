"""Run Baison product inbound synchronization and rebuild diagnosis summary."""

import argparse
import asyncio
import json
from datetime import date, timedelta

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.integrations.baison.services.product_inbound_service import sync_product_inbound


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14, help="Inclusive number of recent days to refresh")
    return parser.parse_args()


async def main(days: int) -> None:
    end_date = date.today()
    start_date = end_date - timedelta(days=max(days, 1) - 1)
    async with AsyncSessionLocal() as db:
        try:
            result = await sync_product_inbound(
                db,
                start_date=start_date,
                end_date=end_date,
                history_start_date=start_date,
            )
            await db.commit()
            counts = (await db.execute(text("""
                SELECT
                  (SELECT count(*) FROM dwd.dwd_baison_purchase_inbound) detail_count,
                  (SELECT count(*) FROM dws.dws_product_inbound_summary) product_count,
                  (SELECT min(record_date) FROM dwd.dwd_baison_purchase_inbound) first_date,
                  (SELECT max(record_date) FROM dwd.dwd_baison_purchase_inbound) last_date
            """))).mappings().one()
            print(json.dumps({
                **result,
                "detail_count": int(counts["detail_count"]),
                "product_count": int(counts["product_count"]),
                "first_date": str(counts["first_date"] or ""),
                "last_date": str(counts["last_date"] or ""),
            }, ensure_ascii=False, default=str))
        except Exception:
            await db.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.days))
