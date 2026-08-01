#!/usr/bin/env python3
"""Read-only post-release verifier for the Finance V2 historical release.

This tool deliberately uses the dedicated ``fin_app`` connection and never
executes DDL or DML.  A successful result proves only the initial read-only
release boundary: published history is visible and all V2 write gates remain
closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402


WRITE_GATES = ("draft_enabled", "review_enabled", "post_enabled", "period_close_enabled", "source_sync_enabled")


def _sync_finance_url() -> str:
    return settings.FINANCE_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)


def inspect_readonly_release() -> dict:
    """Collect only facts visible to the production Finance V2 application role."""

    engine = create_engine(_sync_finance_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return {
                "current_user": connection.scalar(text("SELECT current_user")),
                "history_vouchers": int(connection.scalar(text("SELECT count(*) FROM fin_read.history_voucher"))),
                "history_entries": int(connection.scalar(text("SELECT count(*) FROM fin_read.history_voucher_line"))),
                "current_vouchers": int(connection.scalar(text("SELECT count(*) FROM fin_current.voucher"))),
                "enabled_write_gates": [
                    dict(row)
                    for row in connection.execute(
                        text(
                            """
                            SELECT scope_type, scope_key, gate_name
                            FROM fin_current.feature_gate
                            WHERE enabled = true
                              AND gate_name = ANY(:gate_names)
                            ORDER BY id
                            """
                        ),
                        {"gate_names": list(WRITE_GATES)},
                    ).mappings()
                ],
            }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Finance V2 production read-only release")
    parser.add_argument("--expected-history-vouchers", dest="expected_history_vouchers", required=True, type=int)
    parser.add_argument("--expected-history-entries", dest="expected_history_entries", required=True, type=int)
    parser.add_argument("--expected-current-vouchers", dest="expected_current_vouchers", default=0, type=int)
    args = parser.parse_args()

    facts = inspect_readonly_release()
    violations: list[str] = []
    if facts["current_user"] != "fin_app":
        violations.append("Finance V2 verifier is not using fin_app")
    if facts["history_vouchers"] != args.expected_history_vouchers:
        violations.append("published history voucher count differs from the approved manifest")
    if facts["history_entries"] != args.expected_history_entries:
        violations.append("published history entry count differs from the approved manifest")
    if facts["current_vouchers"] != args.expected_current_vouchers:
        violations.append("current-voucher count is nonzero during the read-only release")
    if facts["enabled_write_gates"]:
        violations.append("one or more Finance V2 write gates are enabled")

    print(
        json.dumps(
            {
                "status": "ready" if not violations else "no_go",
                "facts": facts,
                "violations": violations,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
