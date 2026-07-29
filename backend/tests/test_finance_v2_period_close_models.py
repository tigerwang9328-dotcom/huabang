from pathlib import Path

from app.models.finance_v2_period_close import FinanceV2PeriodCloseApproval, FinanceV2PeriodCloseBatch


def test_period_close_models_are_isolated_and_require_auditable_two_step_reopen_approval():
    assert FinanceV2PeriodCloseBatch.__table__.schema == "fin_current"
    assert FinanceV2PeriodCloseApproval.__table__.schema == "fin_current"

    batch_constraints = {constraint.name for constraint in FinanceV2PeriodCloseBatch.__table__.constraints}
    approval_constraints = {constraint.name for constraint in FinanceV2PeriodCloseApproval.__table__.constraints}

    assert "uq_fin_current_period_close_run" in batch_constraints
    assert "uq_fin_current_period_close_approval_step" in approval_constraints
    assert "uq_fin_current_period_close_approval_actor" in approval_constraints


def test_period_close_migration_persists_close_batches_and_two_reopen_approvals():
    versions = Path(__file__).parents[1] / "alembic" / "versions"
    migration_path = next(
        path for path in versions.glob("*.py") if "CREATE TABLE fin_current.period_close_batch" in path.read_text(encoding="utf-8")
    )
    migration = migration_path.read_text(encoding="utf-8")

    assert "CREATE TABLE fin_current.period_close_approval" in migration
    assert "uq_fin_current_period_close_approval_step" in migration
    assert "approval_step IN (1,2)" in migration
    assert "DROP TABLE IF EXISTS fin_current.period_close_approval" in migration
