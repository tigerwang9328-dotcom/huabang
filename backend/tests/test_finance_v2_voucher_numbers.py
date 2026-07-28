from app.services.finance_v2.voucher_number_domain import VoucherNumberAllocator


def test_voucher_numbers_are_period_scoped_and_voided_numbers_are_not_reused():
    allocator = VoucherNumberAllocator()
    first = allocator.reserve("book-1", "2026-08", "记")
    allocator.void(first.reservation_id, "posting failed")
    second = allocator.reserve("book-1", "2026-08", "记")

    assert first.voucher_no == "0001"
    assert first.status == "void"
    assert second.voucher_no == "0002"


def test_voucher_numbers_restart_only_for_a_different_book_or_period():
    allocator = VoucherNumberAllocator()
    allocator.reserve("book-1", "2026-08", "记")

    assert allocator.reserve("book-1", "2026-09", "记").voucher_no == "0001"
    assert allocator.reserve("book-2", "2026-08", "记").voucher_no == "0001"
