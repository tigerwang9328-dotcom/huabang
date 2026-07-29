"""Stage and optionally publish verified Kingdee snapshot facts into Finance V2.

The default is a read-only source and conflict plan.  Database writes require
both --execute and the dedicated fin_history_importer database identity.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal
from app.services.finance_v2.history_import_service import FinanceV2HistoryImportService, HistoryPublicationError, plan_history_import
from app.services.finance_v2.kingdee_history_loader import KingdeeHistorySourceError, load_kingdee_history_records


def _summary(records) -> dict:
    return {
        "vouchers": len(records),
        "entries": sum(len(record.lines) for record in records),
        "account_sets": {database: len(group) for database, group in sorted(_group_records(records).items())},
    }


def _group_records(records):
    grouped = defaultdict(list)
    for record in records:
        grouped[record.source_database].append(record)
    return grouped


def _batch_code(manifest_path: Path, database: str) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    run_id = str(manifest.get("run_id") or "kingdee")
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:12]
    return f"v2-{run_id}-{database}-{digest}"[:64]


async def _execute(manifest_path: Path, records, *, publish: bool) -> list[dict]:
    grouped = _group_records(records)
    results: list[dict] = []
    async with AsyncSessionLocal() as db:
        current_user = await db.scalar(text("select current_user"))
        if current_user != "fin_history_importer":
            raise HistoryPublicationError("history import must run as fin_history_importer")
        async with db.begin():
            service = FinanceV2HistoryImportService(db)
            for database, source_records in sorted(grouped.items()):
                stage = await service.stage(
                    batch_code=_batch_code(manifest_path, database),
                    source_database=database,
                    records=source_records,
                )
                result = {
                    "source_database": database,
                    "batch_id": stage.batch_id,
                    "stage_status": stage.status,
                    "new_vouchers": stage.new_record_count,
                    "idempotent_vouchers": len(stage.idempotent_source_pks),
                    "conflicts": len(stage.conflicts),
                }
                if stage.status == "loaded" and stage.batch_id is not None:
                    result["validation"] = await service.validate(stage.batch_id)
                if publish and stage.batch_id is not None:
                    batch_status = result.get("validation", {}).get("status", stage.status)
                    if batch_status == "validated":
                        result["publication"] = await service.publish(stage.batch_id)
                results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Finance V2 Kingdee history import")
    parser.add_argument("manifest", type=Path, help="native Kingdee migration manifest.json")
    parser.add_argument("--account-set", action="append", default=[], help="official source database to include; repeatable")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.publish and not args.execute:
        parser.error("--publish requires --execute")
    try:
        records = load_kingdee_history_records(args.manifest)
        if args.account_set:
            requested = set(args.account_set)
            records = [record for record in records if record.source_database in requested]
            unknown = requested.difference({record.source_database for record in records})
            if unknown:
                parser.error("requested official account set is absent: " + ", ".join(sorted(unknown)))
        if not args.execute:
            plan = plan_history_import(records, {})
            print(json.dumps({"mode": "dry_run", **_summary(records), "new_vouchers": len(plan.new_records), "conflicts": len(plan.conflicts)}, ensure_ascii=False))
            return 0
        print(json.dumps({"mode": "executed", "publish_requested": args.publish, "batches": asyncio.run(_execute(args.manifest, records, publish=args.publish))}, ensure_ascii=False))
        return 0
    except (KingdeeHistorySourceError, HistoryPublicationError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
