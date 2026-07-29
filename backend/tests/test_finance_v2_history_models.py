from pathlib import Path

from app.models.finance_v2_history import FinanceV2HistoryBatch, FinanceV2HistoryVoucher, FinanceV2HistoryVoucherLine


def test_history_facts_are_in_their_own_schema_and_link_to_batches():
    assert FinanceV2HistoryBatch.__table__.schema == "fin_history"
    assert FinanceV2HistoryVoucher.__table__.schema == "fin_history"
    assert FinanceV2HistoryVoucherLine.__table__.schema == "fin_history"
    assert "published" in " ".join(str(c.sqltext) for c in FinanceV2HistoryBatch.__table__.constraints if hasattr(c, "sqltext"))


def test_history_source_identity_is_immutable_and_idempotent():
    names = {constraint.name for constraint in FinanceV2HistoryVoucher.__table__.constraints}
    assert "uq_fin_history_voucher_source" in names


def test_history_migration_uses_staging_and_published_read_view():
    versions = Path(__file__).parents[1] / "alembic" / "versions"
    migration_path = next(
        path for path in versions.glob("*.py") if "CREATE TABLE fin_history.staging_voucher" in path.read_text(encoding="utf-8")
    )
    migration = migration_path.read_text(encoding="utf-8")

    assert "down_revision =" in migration
    assert "down_revision = None" not in migration
    assert "fin_history.staging_voucher" in migration
    assert "fin_read.history_voucher" in migration
    assert "published facts are immutable" in migration
