"""add finance history published line read view

Revision ID: 354401508750
Revises: 7c05884df060
Create Date: 2026-07-29 14:57:01.062870

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '354401508750'
down_revision: Union[str, None] = '7c05884df060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fin_history_voucher_line_voucher_id_line_no
        ON fin_history.voucher_line (voucher_id, line_no)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW fin_read.history_voucher_line AS
        SELECT
            line.id,
            line.voucher_id,
            line.line_no,
            line.source_pk AS line_source_pk,
            line.account_code,
            line.summary,
            line.currency_code,
            line.exchange_rate,
            line.debit_amount,
            line.credit_amount,
            line.raw_dimensions,
            voucher.batch_id,
            voucher.source_system,
            voucher.source_database,
            voucher.source_pk AS voucher_source_pk,
            voucher.source_hash,
            voucher.voucher_no,
            voucher.voucher_group,
            voucher.voucher_date,
            voucher.fiscal_year,
            voucher.fiscal_period,
            b.batch_code,
            true AS historical_marker
        FROM fin_history.voucher_line line
        JOIN fin_history.voucher voucher ON voucher.id=line.voucher_id
        JOIN fin_history.import_batch b ON b.id=voucher.batch_id
        WHERE b.status='published';
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS fin_read.history_voucher_line")
    op.execute("DROP INDEX IF EXISTS fin_history.ix_fin_history_voucher_line_voucher_id_line_no")
