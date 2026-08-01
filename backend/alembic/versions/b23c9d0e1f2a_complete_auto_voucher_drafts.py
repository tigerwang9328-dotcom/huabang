"""complete auto voucher drafts

Revision ID: b23c9d0e1f2a
Revises: b22c8d9e0f1a
"""
from alembic import op

revision = "b23c9d0e1f2a"
down_revision = "b22c8d9e0f1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE finance_center_mumaren.finance_center_mumaren_auto_voucher_rules
          ADD COLUMN IF NOT EXISTS debit_account_id BIGINT,
          ADD COLUMN IF NOT EXISTS credit_account_id BIGINT,
          ADD COLUMN IF NOT EXISTS default_amount NUMERIC(18, 2),
          ADD COLUMN IF NOT EXISTS summary VARCHAR(500),
          ADD COLUMN IF NOT EXISTS voucher_type VARCHAR(16) NOT NULL DEFAULT '记';
        CREATE TABLE IF NOT EXISTS finance_center_mumaren.finance_center_mumaren_auto_voucher_runs (
          id BIGSERIAL PRIMARY KEY,
          book_id BIGINT NOT NULL REFERENCES finance_center_mumaren.finance_center_mumaren_books(id),
          rule_id BIGINT NOT NULL REFERENCES finance_center_mumaren.finance_center_mumaren_auto_voucher_rules(id),
          voucher_id BIGINT NOT NULL REFERENCES finance_center_mumaren.finance_center_mumaren_vouchers(id),
          source_key VARCHAR(128) NOT NULL,
          amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
          created_by BIGINT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_mumaren_auto_voucher_run_source UNIQUE(book_id, rule_id, source_key)
        );
        CREATE INDEX IF NOT EXISTS ix_mumaren_auto_voucher_runs_voucher
          ON finance_center_mumaren.finance_center_mumaren_auto_voucher_runs(voucher_id);
        DROP TRIGGER IF EXISTS trg_mumaren_protect_readonly_book_scope
          ON finance_center_mumaren.finance_center_mumaren_auto_voucher_runs;
        CREATE TRIGGER trg_mumaren_protect_readonly_book_scope
          BEFORE INSERT OR UPDATE OR DELETE
          ON finance_center_mumaren.finance_center_mumaren_auto_voucher_runs
          FOR EACH ROW EXECUTE FUNCTION finance_center_mumaren.protect_mumaren_book_scoped_row();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS finance_center_mumaren.finance_center_mumaren_auto_voucher_runs;
        ALTER TABLE finance_center_mumaren.finance_center_mumaren_auto_voucher_rules
          DROP COLUMN IF EXISTS voucher_type,
          DROP COLUMN IF EXISTS summary,
          DROP COLUMN IF EXISTS default_amount,
          DROP COLUMN IF EXISTS credit_account_id,
          DROP COLUMN IF EXISTS debit_account_id;
    """)
