"""protect AR/AP detail lines through their parent order book

Revision ID: b25e1f2a3b4c
Revises: b24d0e1f2a3b
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b25e1f2a3b4c"
down_revision: Union[str, None] = "b24d0e1f2a3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Prevent direct writes to AR/AP detail rows of readonly books.

    Detail rows intentionally do not own ``book_id``; their parent receivable
    or payable order owns it.  Guard both OLD and NEW parents on updates so a
    row cannot be moved into or out of a migrated Kingdee book.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_center_mumaren.protect_mumaren_ar_ap_order_line()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE target_book_id BIGINT;
        BEGIN
          IF TG_TABLE_NAME = 'finance_center_mumaren_receivable_order_lines' THEN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
              SELECT book_id INTO target_book_id
                FROM finance_center_mumaren.finance_center_mumaren_receivable_orders
                WHERE id = OLD.order_id;
              PERFORM finance_center_mumaren.assert_mumaren_writable_book(target_book_id);
            END IF;
            IF TG_OP <> 'DELETE' THEN
              SELECT book_id INTO target_book_id
                FROM finance_center_mumaren.finance_center_mumaren_receivable_orders
                WHERE id = NEW.order_id;
              PERFORM finance_center_mumaren.assert_mumaren_writable_book(target_book_id);
            END IF;
          ELSIF TG_TABLE_NAME = 'finance_center_mumaren_payable_order_lines' THEN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
              SELECT book_id INTO target_book_id
                FROM finance_center_mumaren.finance_center_mumaren_payable_orders
                WHERE id = OLD.order_id;
              PERFORM finance_center_mumaren.assert_mumaren_writable_book(target_book_id);
            END IF;
            IF TG_OP <> 'DELETE' THEN
              SELECT book_id INTO target_book_id
                FROM finance_center_mumaren.finance_center_mumaren_payable_orders
                WHERE id = NEW.order_id;
              PERFORM finance_center_mumaren.assert_mumaren_writable_book(target_book_id);
            END IF;
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$;

        DROP TRIGGER IF EXISTS trg_mumaren_protect_readonly_receivable_order_lines
          ON finance_center_mumaren.finance_center_mumaren_receivable_order_lines;
        CREATE TRIGGER trg_mumaren_protect_readonly_receivable_order_lines
          BEFORE INSERT OR UPDATE OR DELETE
          ON finance_center_mumaren.finance_center_mumaren_receivable_order_lines
          FOR EACH ROW EXECUTE FUNCTION finance_center_mumaren.protect_mumaren_ar_ap_order_line();

        DROP TRIGGER IF EXISTS trg_mumaren_protect_readonly_payable_order_lines
          ON finance_center_mumaren.finance_center_mumaren_payable_order_lines;
        CREATE TRIGGER trg_mumaren_protect_readonly_payable_order_lines
          BEFORE INSERT OR UPDATE OR DELETE
          ON finance_center_mumaren.finance_center_mumaren_payable_order_lines
          FOR EACH ROW EXECUTE FUNCTION finance_center_mumaren.protect_mumaren_ar_ap_order_line();
        """
    )


def downgrade() -> None:
    # Do not weaken the permanent historical-data integrity boundary.
    pass
