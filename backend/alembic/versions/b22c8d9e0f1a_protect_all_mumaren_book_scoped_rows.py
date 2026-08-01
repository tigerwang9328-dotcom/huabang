"""extend readonly Kingdee protection to every book-scoped finance table

Revision ID: b22c8d9e0f1a
Revises: b21a7b8c9d0e
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b22c8d9e0f1a"
down_revision: Union[str, None] = "b21a7b8c9d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the existing OLD/NEW book guard to all book_id tables.

    The voucher-line trigger remains specialised because lines obtain their
    book through voucher_id.  Every other current and future CRUD table that
    owns a book_id is covered, preventing writes to migrated Kingdee books.
    """
    op.execute(
        """
        DO $$
        DECLARE table_name TEXT;
        BEGIN
          FOR table_name IN
            SELECT c.table_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'finance_center_mumaren'
              AND c.column_name = 'book_id'
              AND c.table_name <> 'finance_center_mumaren_voucher_lines'
          LOOP
            EXECUTE format('DROP TRIGGER IF EXISTS trg_mumaren_protect_readonly_book_scope ON finance_center_mumaren.%I', table_name);
            EXECUTE format(
              'CREATE TRIGGER trg_mumaren_protect_readonly_book_scope BEFORE INSERT OR UPDATE OR DELETE ON finance_center_mumaren.%I FOR EACH ROW EXECUTE FUNCTION finance_center_mumaren.protect_mumaren_book_scoped_row()',
              table_name
            );
          END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    # Do not weaken the permanent historical-data integrity boundary.
    pass
