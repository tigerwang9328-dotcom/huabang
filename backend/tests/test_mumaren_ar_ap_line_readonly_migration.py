from pathlib import Path


MIGRATIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def test_ar_ap_detail_lines_are_protected_through_their_parent_order_book():
    migrations = list(MIGRATIONS.glob("*protect_mumaren_ar_ap_order_lines.py"))

    assert len(migrations) == 1
    source = migrations[0].read_text(encoding="utf-8")

    assert "protect_mumaren_ar_ap_order_line" in source
    assert "finance_center_mumaren_receivable_order_lines" in source
    assert "finance_center_mumaren_payable_order_lines" in source
    assert "OLD.order_id" in source
    assert "NEW.order_id" in source
    assert "assert_mumaren_writable_book" in source
    assert "BEFORE INSERT OR UPDATE OR DELETE" in source
