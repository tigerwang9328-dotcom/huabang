"""Task: Color performance report snapshot generation service.

Implements v3.1 report snapshot primitives for color_performance_snapshots:
- generate_report_snapshot: pure function that builds a new snapshot dict
  (is_current=True, revision = max(existing) + 1, starts at 1) and returns
  an updated list where all prior snapshots have is_current=False.
"""

from __future__ import annotations

import json
from typing import Any


def generate_report_snapshot(
    *,
    account_id: int,
    observation_window: str,
    position_segment: str,
    metric_version: str,
    snapshot_data: Any,
    source_data_cutoff_at: Any,
    existing_snapshots: list[dict],
) -> tuple[dict, list[dict]]:
    """Generate a new color performance report snapshot.

    Pure function: does not mutate the caller's ``existing_snapshots`` list
    nor the snapshot dicts it contains.

    - New snapshot is_current=True; all prior snapshots is_current=False.
    - report_revision = max(existing revisions) + 1 (1 when none exist).
    - snapshot_data is JSON-serialized into snapshot_data_json.

    Returns ``(new_snapshot, updated_snapshots)`` where ``updated_snapshots``
    is a new list containing shallow copies of prior snapshots
    (``is_current=False``) followed by the new snapshot.
    """

    prior_revisions = [
        int(s["report_revision"])
        for s in existing_snapshots
        if s.get("report_revision") is not None
    ]
    next_revision = max(prior_revisions) + 1 if prior_revisions else 1

    superseded = [
        {**snapshot, "is_current": False}
        for snapshot in existing_snapshots
    ]

    new_snapshot = {
        "account_id": account_id,
        "observation_window": observation_window,
        "position_segment": position_segment,
        "metric_version": metric_version,
        "source_data_cutoff_at": source_data_cutoff_at,
        "report_revision": next_revision,
        "is_current": True,
        "snapshot_data_json": json.dumps(
            snapshot_data, ensure_ascii=False, sort_keys=True
        ),
    }

    return new_snapshot, [*superseded, new_snapshot]
