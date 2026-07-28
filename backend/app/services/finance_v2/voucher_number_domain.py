"""Deterministic reservation semantics; persistence must use matching row locks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VoucherNumberReservation:
    reservation_id: int
    book: str
    period: str
    voucher_group: str
    voucher_no: str
    status: str = "reserved"
    void_reason: str | None = None


class VoucherNumberAllocator:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, str, str], int] = {}
        self._reservations: dict[int, VoucherNumberReservation] = {}
        self._next_id = 1

    def reserve(self, book: str, period: str, voucher_group: str) -> VoucherNumberReservation:
        key = (book, period, voucher_group)
        next_number = self._counters.get(key, 0) + 1
        self._counters[key] = next_number
        reservation = VoucherNumberReservation(self._next_id, book, period, voucher_group, f"{next_number:04d}")
        self._reservations[reservation.reservation_id] = reservation
        self._next_id += 1
        return reservation

    def void(self, reservation_id: int, reason: str) -> VoucherNumberReservation:
        reservation = self._reservations[reservation_id]
        if not reason.strip():
            raise ValueError("void reason is required")
        reservation.status = "void"
        reservation.void_reason = reason
        return reservation
