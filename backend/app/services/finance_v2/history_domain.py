"""Pure state and idempotency rules for immutable Finance V2 history."""

from __future__ import annotations

from dataclasses import dataclass


class HistoryBatchError(ValueError):
    pass


@dataclass(frozen=True)
class HistoryBatchState:
    status: str


_TRANSITIONS = {
    "created": {"start_loading": "loading", "cancel": "cancelled"},
    "loading": {"mark_loaded": "loaded", "fail": "failed", "cancel": "cancelled"},
    "loaded": {"start_validation": "validating", "fail": "failed"},
    "validating": {"mark_validated": "validated", "fail": "failed", "conflict": "conflicted"},
    "validated": {"publish": "published", "fail": "failed"},
    "published": {},
    "failed": {},
    "conflicted": {},
    "cancelled": {},
    "superseded": {},
}


def transition_history_batch(state: HistoryBatchState, action: str) -> HistoryBatchState:
    target = _TRANSITIONS.get(state.status, {}).get(action)
    if target is None:
        raise HistoryBatchError(f"invalid history batch transition: {state.status} -> {action}")
    return HistoryBatchState(target)


def classify_source_record(existing_hash: str | None, incoming_hash: str) -> str:
    """Classify a source key before writing any immutable history fact."""

    if existing_hash is None:
        return "new"
    if existing_hash == incoming_hash:
        return "already_imported"
    return "conflict"
