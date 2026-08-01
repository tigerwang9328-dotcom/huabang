"""upgrade legacy b19 Kingdee metadata to the historical-book contract

Revision ID: b20f6a7d8e9f
Revises: b19d3e5f7a01
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b20f6a7d8e9f"
down_revision: Union[str, None] = "b19d3e5f7a01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Repair the previously deployed b19 shape without touching other schemas.

    Fresh databases already receive the target shape from b19.  PostgreSQL's
    IF EXISTS clauses make this migration safe for both fresh and legacy b19
    databases, while the validation refuses to fabricate source identity.
    """
    op.execute(
        """
        SET LOCAL app.mumaren_kingdee_import = 'on';

        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM finance_center_mumaren.finance_center_mumaren_balance_snapshots
            WHERE source_system = 'kingdee'
              AND (
                source_payload IS NULL
                OR NOT (source_payload ? 'source_balance')
                OR NOT ((source_payload -> 'source_balance') ? 'FAccountID')
                OR NOT ((source_payload -> 'source_balance') ? 'FYear')
                OR NOT ((source_payload -> 'source_balance') ? 'FPeriod')
                OR NOT ((source_payload -> 'source_balance') ? 'FDetailID')
                OR NOT ((source_payload -> 'source_balance') ? 'FCurrencyID')
              )
          ) THEN
            RAISE EXCEPTION 'cannot upgrade legacy Kingdee balance snapshots without complete immutable source identity';
          END IF;
        END;
        $$;

        ALTER TABLE finance_center_mumaren.finance_center_mumaren_kingdee_import_batches
          DROP CONSTRAINT IF EXISTS ck_mumaren_kingdee_batch_source;
        ALTER TABLE finance_center_mumaren.finance_center_mumaren_balance_snapshots
          DROP CONSTRAINT IF EXISTS ck_mumaren_finance_balance_snapshot_source,
          DROP CONSTRAINT IF EXISTS uq_mumaren_finance_balance_snapshot;

        UPDATE finance_center_mumaren.finance_center_mumaren_balance_snapshots
        SET source_key = 'FAccountID=' || (source_payload -> 'source_balance' ->> 'FAccountID')
                       || '|FYear=' || (source_payload -> 'source_balance' ->> 'FYear')
                       || '|FPeriod=' || (source_payload -> 'source_balance' ->> 'FPeriod')
                       || '|FDetailID=' || (source_payload -> 'source_balance' ->> 'FDetailID')
                       || '|FCurrencyID=' || (source_payload -> 'source_balance' ->> 'FCurrencyID')
        WHERE source_system = 'kingdee';

        UPDATE finance_center_mumaren.finance_center_mumaren_books
          SET source_system = 'kingdee_history'
          WHERE source_system = 'kingdee';
        UPDATE finance_center_mumaren.finance_center_mumaren_accounts
          SET source_system = 'kingdee_history'
          WHERE source_system = 'kingdee';
        UPDATE finance_center_mumaren.finance_center_mumaren_fiscal_periods
          SET source_system = 'kingdee_history'
          WHERE source_system = 'kingdee';
        UPDATE finance_center_mumaren.finance_center_mumaren_vouchers
          SET source_system = 'kingdee_history'
          WHERE source_system = 'kingdee';
        UPDATE finance_center_mumaren.finance_center_mumaren_voucher_lines
          SET source_system = 'kingdee_history'
          WHERE source_system = 'kingdee';
        UPDATE finance_center_mumaren.finance_center_mumaren_balance_snapshots
          SET source_system = 'kingdee_history'
          WHERE source_system = 'kingdee';
        UPDATE finance_center_mumaren.finance_center_mumaren_kingdee_import_batches
          SET source_system = 'kingdee_history'
          WHERE source_system = 'kingdee';

        ALTER TABLE finance_center_mumaren.finance_center_mumaren_kingdee_import_batches
          ADD CONSTRAINT ck_mumaren_kingdee_batch_source CHECK (source_system = 'kingdee_history');
        ALTER TABLE finance_center_mumaren.finance_center_mumaren_balance_snapshots
          ADD CONSTRAINT ck_mumaren_finance_balance_snapshot_source CHECK (source_system = 'kingdee_history');

        DROP INDEX IF EXISTS finance_center_mumaren.uq_mumaren_finance_book_kingdee_source;
        DROP INDEX IF EXISTS finance_center_mumaren.uq_mumaren_finance_account_kingdee_source;
        DROP INDEX IF EXISTS finance_center_mumaren.uq_mumaren_finance_period_kingdee_source;
        DROP INDEX IF EXISTS finance_center_mumaren.uq_mumaren_finance_voucher_kingdee_source;
        DROP INDEX IF EXISTS finance_center_mumaren.uq_mumaren_finance_line_kingdee_source;
        CREATE UNIQUE INDEX uq_mumaren_finance_book_kingdee_source
          ON finance_center_mumaren.finance_center_mumaren_books(source_system, source_database, source_key)
          WHERE source_system = 'kingdee_history';
        CREATE UNIQUE INDEX uq_mumaren_finance_account_kingdee_source
          ON finance_center_mumaren.finance_center_mumaren_accounts(book_id, source_system, source_key)
          WHERE source_system = 'kingdee_history';
        CREATE UNIQUE INDEX uq_mumaren_finance_period_kingdee_source
          ON finance_center_mumaren.finance_center_mumaren_fiscal_periods(book_id, source_system, source_key)
          WHERE source_system = 'kingdee_history';
        CREATE UNIQUE INDEX uq_mumaren_finance_voucher_kingdee_source
          ON finance_center_mumaren.finance_center_mumaren_vouchers(book_id, source_system, source_database, source_key)
          WHERE source_system = 'kingdee_history';
        CREATE UNIQUE INDEX uq_mumaren_finance_line_kingdee_source
          ON finance_center_mumaren.finance_center_mumaren_voucher_lines(voucher_id, source_system, source_key)
          WHERE source_system = 'kingdee_history';
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "b20 expands legacy balance snapshots from one account-period row to multiple immutable source rows; "
        "downgrade would discard source evidence, so restore the rehearsal backup instead."
    )
