from pathlib import Path


def test_readonly_trigger_upgrade_checks_both_old_and_new_owners():
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "b27d3e4f5a6b_harden_mumaren_readonly_update_guards.py"
    source = migration.read_text(encoding="utf-8")

    assert "assert_mumaren_writable_book(OLD.book_id)" in source
    assert "assert_mumaren_writable_book(NEW.book_id)" in source
    assert "old_voucher_book_id" in source
    assert "new_voucher_book_id" in source
    assert "assert_mumaren_writable_book(old_voucher_book_id)" in source
    assert "assert_mumaren_writable_book(new_voucher_book_id)" in source
