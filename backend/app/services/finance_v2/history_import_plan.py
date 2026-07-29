"""Pure, no-database planning primitives for Finance V2 history imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol

from app.services.finance_v2.history_domain import classify_source_record


class _SourceRecord(Protocol):
    source_pk: str
    source_hash: str


class HistoryPublicationError(ValueError):
    pass


@dataclass(frozen=True)
class HistoryImportPlan:
    new_records: tuple[_SourceRecord, ...]
    idempotent_source_pks: tuple[str, ...]
    conflicts: tuple[tuple[str, str, str], ...]


def plan_history_import(records: Iterable[_SourceRecord], existing_hashes: Mapping[str, str]) -> HistoryImportPlan:
    """Classify source facts without importing ORM models or mutating a table."""

    new_records: list[_SourceRecord] = []
    idempotent: list[str] = []
    conflicts: list[tuple[str, str, str]] = []
    seen: dict[str, str] = {}
    for record in records:
        previous_in_request = seen.get(record.source_pk)
        if previous_in_request is not None and previous_in_request != record.source_hash:
            conflicts.append((record.source_pk, previous_in_request, record.source_hash))
            continue
        if previous_in_request is not None:
            continue
        seen[record.source_pk] = record.source_hash
        existing_hash = existing_hashes.get(record.source_pk)
        classification = classify_source_record(existing_hash, record.source_hash)
        if classification == "new":
            new_records.append(record)
        elif classification == "already_imported":
            idempotent.append(record.source_pk)
        else:
            conflicts.append((record.source_pk, str(existing_hash), record.source_hash))
    return HistoryImportPlan(tuple(new_records), tuple(sorted(idempotent)), tuple(sorted(conflicts)))
