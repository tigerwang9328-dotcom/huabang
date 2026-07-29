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
    command_id: str | None = None
    status: str = "reserved"
    void_reason: str | None = None


class VoucherNumberAllocator:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, str, str], int] = {}
        self._reservations: dict[int, VoucherNumberReservation] = {}
        self._reservations_by_command: dict[str, int] = {}
        self._next_id = 1

    def reserve(
        self,
        book: str,
        period: str,
        voucher_group: str,
        *,
        command_id: str | None = None,
    ) -> VoucherNumberReservation:
        key = (book, period, voucher_group)
        normalized_command_id = (command_id or "").strip() or None
        if normalized_command_id and normalized_command_id in self._reservations_by_command:
            existing = self._reservations[self._reservations_by_command[normalized_command_id]]
            if (existing.book, existing.period, existing.voucher_group) != key:
                raise ValueError("command id was already used for a different reservation scope")
            return existing
        next_number = self._counters.get(key, 0) + 1
        self._counters[key] = next_number
        reservation = VoucherNumberReservation(
            self._next_id,
            book,
            period,
            voucher_group,
            f"{next_number:04d}",
            command_id=normalized_command_id,
        )
        self._reservations[reservation.reservation_id] = reservation
        if normalized_command_id:
            self._reservations_by_command[normalized_command_id] = reservation.reservation_id
        self._next_id += 1
        return reservation

    def void(self, reservation_id: int, reason: str) -> VoucherNumberReservation:
        reservation = self._reservations[reservation_id]
        if not reason.strip():
            raise ValueError("void reason is required")
        reservation.status = "voided"
        reservation.void_reason = reason
        return reservation
