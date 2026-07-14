import asyncio
from datetime import date
from pathlib import Path

from app.services.exception_rule_service import RULE_SOURCE_BY_CODE
from app.services.rule_engine import RULE_DEFS, RuleEngine


BACKEND = Path(__file__).resolve().parents[1]


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    async def execute(self, statement, params=None):
        self.sql = str(statement)
        self.params = params
        return _Rows(self.rows)


def test_profit_rules_use_codes_after_existing_inventory_rule_range():
    codes = [item[0] for item in RULE_DEFS]

    assert len(codes) == len(set(codes))
    assert "R022" in codes
    assert "R023" in codes
    assert RULE_SOURCE_BY_CODE["R022"] == ("dm.dm_finance_profit_daily", "/app/finance")
    assert RULE_SOURCE_BY_CODE["R023"] == ("dwd.dwd_pos_ticket", "/app/member")


def test_high_sales_low_profit_rule_requires_ready_approved_profit():
    engine = RuleEngine()
    db = _Db([("ALL", 8000, 200, 0.025)])

    findings = asyncio.run(engine._rule_r022("2026-07-13", date(2026, 7, 13), db, None))

    assert "operating_profit_status='ready'" in db.sql
    assert "finance_approved=true" in db.sql
    assert "store_code='ALL'" in db.sql
    assert db.params["min_sales"] == 5000
    assert db.params["max_margin"] == 0.05
    assert findings[0].get("store_code") is None
    assert findings[0]["evidence"]["operating_margin"] == 0.025


def test_vip_excessive_discount_rule_uses_member_sales_and_low_rate_threshold():
    engine = RuleEngine()
    db = _Db([("285204", "VIP-001", 1200, 4000, 0.3)])

    findings = asyncio.run(engine._rule_r023("2026-07-13", date(2026, 7, 13), db, None))

    assert "vip_code" in db.sql
    assert "customer_code" in db.sql
    assert "CAST(:store_code AS text) IS NULL" in db.sql
    assert "UPPER(CAST(:store_code AS text))" in db.sql
    assert "discount_rate<:min_discount_rate" in db.sql
    assert db.params["min_vip_sales"] == 1000
    assert db.params["min_discount_rate"] == 0.4
    assert findings[0]["member_no"] == "VIP-001"
    assert findings[0]["evidence"]["discount_rate"] == 0.3


def test_follow_up_migration_seeds_profit_rules_without_reusing_r016():
    migration = BACKEND / "alembic" / "versions" / "1d0e1f2a3b4c_profit_rule_config.py"
    source = migration.read_text(encoding="utf-8")

    assert "('R022'" in source
    assert "('R023'" in source
    assert "('R016'" not in source
