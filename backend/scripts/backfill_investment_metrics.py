"""Dry-run by default backfill for retained LifeData captures."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.life_data import LifeDataCapture
from app.services.investment_metric_service import normalize_capture, persist_metric_snapshots


async def run(*, apply: bool, batch_size: int = 200) -> dict[str, int]:
    scanned = facts = inserted = 0
    last_id = 0
    async with AsyncSessionLocal() as db:
        while True:
            rows = (
                await db.execute(
                    select(LifeDataCapture)
                    .where(
                        LifeDataCapture.account_id == settings.LIFE_DATA_ACCOUNT_ID,
                        LifeDataCapture.id > last_id,
                    )
                    .order_by(LifeDataCapture.id)
                    .limit(batch_size)
                )
            ).scalars().all()
            if not rows:
                break
            scanned += len(rows)
            facts += sum(len(normalize_capture(row)) for row in rows)
            if apply:
                inserted += len(
                    await persist_metric_snapshots(db, settings.LIFE_DATA_ACCOUNT_ID, rows)
                )
                await db.commit()
            last_id = rows[-1].id
    return {"scanned": scanned, "facts": facts, "inserted": inserted, "dry_run": int(not apply)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()
    print(asyncio.run(run(apply=args.apply, batch_size=args.batch_size)))
