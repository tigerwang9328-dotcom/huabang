"""Validate/import the canonical Kingdee three-book snapshot into current books.

Without --execute this command is a database-free dry run.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.mumaren_finance_center.kingdee_books import KingdeeBooksImportError, import_kingdee_books


async def _run(manifest: Path, *, execute: bool, batch_key: str | None) -> dict:
    if not execute:
        return (await import_kingdee_books(None, manifest, execute=False, batch_key=batch_key)).__dict__
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        async with db.begin():
            return (await import_kingdee_books(db, manifest, execute=True, batch_key=batch_key)).__dict__


def main() -> int:
    parser = argparse.ArgumentParser(description="Import canonical Kingdee three books into isolated current finance books")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--execute", action="store_true", help="write only after a successful dry run")
    parser.add_argument("--batch-key", help="idempotency key; source checksum changes are rejected")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(_run(args.manifest, execute=args.execute, batch_key=args.batch_key)), ensure_ascii=False, sort_keys=True))
        return 0
    except KingdeeBooksImportError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
