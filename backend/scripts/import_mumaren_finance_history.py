"""Import an explicit local Kingdee JSON manifest into Mumaren finance history.

Without ``--execute`` this command is a pure validation/dry run.  It never
connects to Kingdee or any legacy Huabang Finance/V2 service.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.mumaren_finance_center.history import HistoryImportError, import_history_manifest


async def _run(manifest: Path, *, execute: bool, imported_by: int | None) -> dict:
    if not execute:
        # The service deliberately returns before touching a database session.
        return (await import_history_manifest(None, manifest, execute=False)).__dict__
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        async with db.begin():
            return (await import_history_manifest(
                db, manifest, execute=True, imported_by=imported_by,
            )).__dict__


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Kingdee history into isolated Mumaren finance history")
    parser.add_argument("manifest", type=Path, help="explicit readonly Kingdee history JSON manifest")
    parser.add_argument("--execute", action="store_true", help="write isolated Mumaren history tables")
    parser.add_argument("--imported-by", type=int, help="Huabang operator id recorded on import batch")
    args = parser.parse_args()
    try:
        result = asyncio.run(_run(args.manifest, execute=args.execute, imported_by=args.imported_by))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except HistoryImportError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
