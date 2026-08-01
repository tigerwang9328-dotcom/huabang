"""Invariant checks for immutable Finance V2 source-preview receipts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceIdentity:
    source_system: str
    source_pk: str
    source_hash: str


@dataclass(frozen=True)
class SourceReceiptDecision:
    status: str
    creates_inbox_item: bool
    creates_draft: bool
    exception_code: str | None = None


def classify_source_receipt(*, existing: SourceIdentity | None, incoming: SourceIdentity) -> SourceReceiptDecision:
    """Classify one source key without ever creating a current-account draft.

    A source identity is immutable: a repeat with its original hash is safe to
    ignore, while a changed hash is an exception that must be handled by a
    controlled version/reversal process rather than an upsert.
    """

    if existing is None:
        return SourceReceiptDecision("received", True, False)
    if (existing.source_system, existing.source_pk) != (incoming.source_system, incoming.source_pk):
        raise ValueError("existing source identity does not match incoming source identity")
    if existing.source_hash == incoming.source_hash:
        return SourceReceiptDecision("already_imported", False, False)
    return SourceReceiptDecision("conflicted", False, False, "source_hash_changed")
