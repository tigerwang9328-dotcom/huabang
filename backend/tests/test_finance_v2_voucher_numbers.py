from app.services.finance_v2.voucher_number_domain import VoucherNumberAllocator
from app.services.finance_v2.voucher_number_service import FinanceV2VoucherNumberService
import pytest


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _ReservationDb:
    def __init__(self, counter):
        self.counter = counter
        self.calls = 0
        self.added = []

    async def execute(self, _statement):
        self.calls += 1
        if self.calls == 1:
            return _Result()
        if self.calls == 3:
            return _Result(self.counter)
        return _Result()

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        pass


def test_voucher_numbers_are_period_scoped_and_voided_numbers_are_not_reused():
    allocator = VoucherNumberAllocator()
    first = allocator.reserve("book-1", "2026-08", "记")
    allocator.void(first.reservation_id, "posting failed")
    second = allocator.reserve("book-1", "2026-08", "记")

    assert first.voucher_no == "0001"
    assert first.status == "voided"
    assert second.voucher_no == "0002"


def test_voucher_numbers_restart_only_for_a_different_book_or_period():
    allocator = VoucherNumberAllocator()
    allocator.reserve("book-1", "2026-08", "记")

    assert allocator.reserve("book-1", "2026-09", "记").voucher_no == "0001"
    assert allocator.reserve("book-2", "2026-08", "记").voucher_no == "0001"


def test_repeated_command_id_returns_the_original_reservation_without_consuming_a_number():
    allocator = VoucherNumberAllocator()

    first = allocator.reserve("book-1", "2026-08", "记", command_id="post:command-1")
    repeated = allocator.reserve("book-1", "2026-08", "记", command_id="post:command-1")
    next_reservation = allocator.reserve("book-1", "2026-08", "记", command_id="post:command-2")

    assert repeated.reservation_id == first.reservation_id
    assert repeated.voucher_no == "0001"
    assert next_reservation.voucher_no == "0002"


def test_reused_command_id_with_different_scope_is_rejected():
    allocator = VoucherNumberAllocator()
    allocator.reserve("book-1", "2026-08", "记", command_id="post:command-1")

    try:
        allocator.reserve("book-2", "2026-08", "记", command_id="post:command-1")
    except ValueError as error:
        assert "scope" in str(error)
    else:
        raise AssertionError("a command id must not reserve a second voucher number")


@pytest.mark.asyncio
async def test_database_reservation_locks_and_advances_the_period_counter_before_posting():
    counter = type("Counter", (), {"next_number": 7})()
    db = _ReservationDb(counter)

    reservation = await FinanceV2VoucherNumberService(db).reserve(
        book_id=3,
        period_id=9,
        voucher_group="记",
        command_id="post-command-7",
        voucher_id=17,
    )

    assert reservation.voucher_no == "0007"
    assert reservation.status == "reserved"
    assert counter.next_number == 8
