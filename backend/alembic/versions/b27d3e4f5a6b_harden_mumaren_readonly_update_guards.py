"""harden readonly Kingdee book ownership guards

Revision ID: b27d3e4f5a6b
Revises: b26f2a3b4c5d

An UPDATE must protect both the old owner and the new owner.  Otherwise a
row could be moved out of a readonly Kingdee book and subsequently changed.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b27d3e4f5a6b"
down_revision: Union[str, None] = "b26f2a3b4c5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_center_mumaren.protect_mumaren_book_scoped_row()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(NEW.book_id);
          ELSIF TG_OP = 'DELETE' THEN
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(OLD.book_id);
          ELSE
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(OLD.book_id);
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(NEW.book_id);
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$;

        CREATE OR REPLACE FUNCTION finance_center_mumaren.protect_mumaren_voucher_line()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE old_voucher_book_id BIGINT;
        DECLARE new_voucher_book_id BIGINT;
        DECLARE account_book_id BIGINT;
        BEGIN
          IF TG_OP = 'INSERT' THEN
            SELECT book_id INTO new_voucher_book_id
              FROM finance_center_mumaren.finance_center_mumaren_vouchers WHERE id = NEW.voucher_id;
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(new_voucher_book_id);
          ELSIF TG_OP = 'DELETE' THEN
            SELECT book_id INTO old_voucher_book_id
              FROM finance_center_mumaren.finance_center_mumaren_vouchers WHERE id = OLD.voucher_id;
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(old_voucher_book_id);
            RETURN OLD;
          ELSE
            SELECT book_id INTO old_voucher_book_id
              FROM finance_center_mumaren.finance_center_mumaren_vouchers WHERE id = OLD.voucher_id;
            SELECT book_id INTO new_voucher_book_id
              FROM finance_center_mumaren.finance_center_mumaren_vouchers WHERE id = NEW.voucher_id;
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(old_voucher_book_id);
            PERFORM finance_center_mumaren.assert_mumaren_writable_book(new_voucher_book_id);
          END IF;
          SELECT book_id INTO account_book_id
            FROM finance_center_mumaren.finance_center_mumaren_accounts WHERE id = NEW.account_id;
          IF new_voucher_book_id IS DISTINCT FROM account_book_id THEN
            RAISE EXCEPTION 'voucher line account must belong to the voucher book';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )


def downgrade() -> None:
    # Retain the stricter permanent-readonly boundary during an application rollback.
    pass
