"""prevent historical Kingdee rows from being moved out of readonly books

Revision ID: b21a7b8c9d0e
Revises: b20f6a7d8e9f
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b21a7b8c9d0e"
down_revision: Union[str, None] = "b20f6a7d8e9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reject updates that move historical rows into a writable book.

    b19 guarded only the target book on UPDATE.  This forward-only replacement
    checks both the source and target relationship, preserving historical rows
    as permanently immutable even if a caller attempts to change book_id or
    voucher_id first.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_center_mumaren.protect_mumaren_book_scoped_row()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(OLD.book_id);
            RETURN OLD;
          END IF;
          IF TG_OP = 'UPDATE' THEN
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(OLD.book_id);
          END IF;
          PERFORM finance_center_mumaren.assert_mumaren_writable_book(NEW.book_id);
          RETURN NEW;
        END;
        $$;

        CREATE OR REPLACE FUNCTION finance_center_mumaren.protect_mumaren_voucher_line()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE target_book_id BIGINT;
        DECLARE account_book_id BIGINT;
        BEGIN
          IF TG_OP IN ('UPDATE', 'DELETE') THEN
            SELECT book_id INTO target_book_id
              FROM finance_center_mumaren.finance_center_mumaren_vouchers WHERE id = OLD.voucher_id;
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(target_book_id);
          END IF;
          IF TG_OP <> 'DELETE' THEN
            SELECT book_id INTO target_book_id
              FROM finance_center_mumaren.finance_center_mumaren_vouchers WHERE id = NEW.voucher_id;
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(target_book_id);
            SELECT book_id INTO account_book_id
              FROM finance_center_mumaren.finance_center_mumaren_accounts WHERE id = NEW.account_id;
            IF target_book_id IS DISTINCT FROM account_book_id THEN
              RAISE EXCEPTION 'voucher line account must belong to the voucher book';
            END IF;
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$;
        """
    )


def downgrade() -> None:
    # b19's trigger implementation is intentionally not restored: downgrade
    # must not weaken an already migrated historical data protection boundary.
    pass
