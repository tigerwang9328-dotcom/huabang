"""Remove one explicitly identified, mis-archived Kingdee history batch.

Default mode is a read-only preview.  ``--execute`` is permitted only after a
checksum-matched three-book import batch is validated or imported.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.mumaren_finance_center.kingdee_history_cleanup import (
    MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
    MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
    KingdeeHistoryCleanupError,
    KingdeeHistoryCleanupRequest,
    cleanup_misarchived_kingdee_history,
)


async def _run(request: KingdeeHistoryCleanupRequest, *, execute: bool) -> dict:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        async with db.begin():
            return (await cleanup_misarchived_kingdee_history(db, request, execute=execute)).__dict__


def main() -> int:
    parser = argparse.ArgumentParser(description="Precisely remove one mis-archived Kingdee history batch from Mumaren only")
    parser.add_argument("--kingdee-batch-key", help="exact replacement three-book import batch_key; required with --execute")
    parser.add_argument("--kingdee-manifest-checksum", help="exact SHA-256 of the validated replacement manifest; required with --execute")
    parser.add_argument("--execute", action="store_true", help="delete only after the three-book import gate succeeds")
    args = parser.parse_args()
    request = KingdeeHistoryCleanupRequest(
        MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
        args.kingdee_batch_key,
        args.kingdee_manifest_checksum,
    )
    try:
        print(json.dumps(asyncio.run(_run(request, execute=args.execute)), ensure_ascii=False, sort_keys=True))
        return 0
    except KingdeeHistoryCleanupError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
