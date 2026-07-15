"""Read-only, PII-free export consumed by the personal Huabang advisor skill."""
import argparse
import asyncio
import json
from datetime import date

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.services.ai_business_advice_service import BUSINESS_ADVICE_MODULES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--module", choices=BUSINESS_ADVICE_MODULES)
    parser.add_argument("--store-code", choices=sorted(ALLOWED_STORE_CODES))
    return parser.parse_args()


async def export_context(args: argparse.Namespace) -> dict:
    async with AsyncSessionLocal() as db:
        stat_date = date.fromisoformat(args.date) if args.date else (await db.execute(text("""
            SELECT MAX(stat_date)
            FROM (
                SELECT MAX(stat_date) AS stat_date FROM ai.ai_business_advice_snapshot
                UNION ALL
                SELECT MAX(report_date) AS stat_date FROM dm.dm_boss_daily_report
            ) latest_dates
        """))).scalar_one()
        conditions = ["stat_date=:stat_date"]
        params = {"stat_date": stat_date}
        if args.module:
            conditions.append("module=:module")
            params["module"] = args.module
        if args.store_code:
            conditions.extend(["scope_type='store'", "target_code=:store_code"])
            params["store_code"] = args.store_code
        rows = (await db.execute(text(f"""
            SELECT module, scope_type, target_code, input_hash, mode, status,
                   data_status, provider, model_name, prompt_version,
                   schema_version, prompt_tokens, completion_tokens,
                   total_tokens, latency_ms, error_code, fallback_reason,
                   generated_at, safe_context, conclusion
            FROM ai.ai_business_advice_snapshot
            WHERE {' AND '.join(conditions)}
            ORDER BY CASE WHEN scope_type='company' THEN 0 ELSE 1 END,
                     target_code, module
        """), params)).mappings().all()
        health = (await db.execute(text("""
            SELECT report_date, is_cost_complete, is_finance_complete,
                   data_quality_status, source_freshness, metric_status,
                   generated_at
            FROM dm.dm_boss_daily_report
            WHERE report_date=:stat_date
        """), {"stat_date": stat_date})).mappings().first() or {}
        return {
            "ok": True,
            "stat_date": str(stat_date) if stat_date else None,
            "filters": {"module": args.module, "store_code": args.store_code},
            "data_health": dict(health),
            "unit_count": len(rows),
            "snapshot_available": bool(rows),
            "limitations": [] if rows else ["最新业务日尚无AI经营建议快照"],
            "units": [dict(row) for row in rows],
        }


async def main() -> None:
    try:
        payload = await export_context(parse_args())
        print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
