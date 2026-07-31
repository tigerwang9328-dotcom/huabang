"""Task: Color performance report snapshot generation primitives.

Covers v3.1 report snapshots for color_performance_snapshots:
- generate_report_snapshot: pure function returning a new snapshot dict
  and an updated list where all prior snapshots have is_current=False
- revision increments from max(existing revisions) + 1 (starts at 1)
- new snapshot is marked is_current=True and carries snapshot_data_json
"""

import json

from app.services.douyin_color_report_service import generate_report_snapshot


def test_first_snapshot_revision_is_one_when_no_existing():
    """Generating the first snapshot yields revision=1."""

    new_snapshot, _updated = generate_report_snapshot(
        account_id=1001,
        observation_window="t7",
        position_segment="all",
        metric_version="v3.1",
        snapshot_data={"average_retention": 0.42},
        source_data_cutoff_at="2026-07-31T00:00:00+00:00",
        existing_snapshots=[],
    )
    assert new_snapshot["report_revision"] == 1


def test_new_snapshot_revision_increments_from_max():
    """revision = max(existing revisions) + 1."""

    existing = [
        {"id": 1, "report_revision": 1, "is_current": True},
        {"id": 2, "report_revision": 3, "is_current": False},
    ]
    new_snapshot, _updated = generate_report_snapshot(
        account_id=1001,
        observation_window="t7",
        position_segment="all",
        metric_version="v3.1",
        snapshot_data={"average_retention": 0.55},
        source_data_cutoff_at="2026-07-31T00:00:00+00:00",
        existing_snapshots=existing,
    )
    assert new_snapshot["report_revision"] == 4


def test_new_snapshot_is_current_true():
    """Newly generated snapshot is marked is_current=True."""

    new_snapshot, _updated = generate_report_snapshot(
        account_id=1001,
        observation_window="t7",
        position_segment="all",
        metric_version="v3.1",
        snapshot_data={"average_retention": 0.42},
        source_data_cutoff_at="2026-07-31T00:00:00+00:00",
        existing_snapshots=[],
    )
    assert new_snapshot["is_current"] is True


def test_old_snapshots_is_current_set_to_false():
    """All prior snapshots must have is_current flipped to False."""

    existing = [
        {"id": 1, "report_revision": 1, "is_current": True},
        {"id": 2, "report_revision": 2, "is_current": True},
    ]
    _new_snapshot, updated = generate_report_snapshot(
        account_id=1001,
        observation_window="t7",
        position_segment="all",
        metric_version="v3.1",
        snapshot_data={"average_retention": 0.42},
        source_data_cutoff_at="2026-07-31T00:00:00+00:00",
        existing_snapshots=existing,
    )
    for snap in updated[:-1]:
        assert snap["is_current"] is False
    # The new snapshot is the last element.
    assert updated[-1]["is_current"] is True


def test_new_snapshot_contains_required_fields():
    """The generated snapshot carries all required identifying fields."""

    new_snapshot, _updated = generate_report_snapshot(
        account_id=1001,
        observation_window="t30",
        position_segment="front",
        metric_version="v3.1",
        snapshot_data={"average_retention": 0.42},
        source_data_cutoff_at="2026-07-31T00:00:00+00:00",
        existing_snapshots=[],
    )
    for field in (
        "account_id",
        "observation_window",
        "position_segment",
        "metric_version",
        "snapshot_data_json",
        "source_data_cutoff_at",
    ):
        assert field in new_snapshot, f"missing field: {field}"
    assert new_snapshot["account_id"] == 1001
    assert new_snapshot["observation_window"] == "t30"
    assert new_snapshot["position_segment"] == "front"
    assert new_snapshot["metric_version"] == "v3.1"
    assert new_snapshot["source_data_cutoff_at"] == "2026-07-31T00:00:00+00:00"


def test_snapshot_data_serialized_to_json_string():
    """snapshot_data is serialized into snapshot_data_json as a JSON string."""

    payload = {"average_retention": 0.42, "sample_count": 12}
    new_snapshot, _updated = generate_report_snapshot(
        account_id=1001,
        observation_window="t7",
        position_segment="all",
        metric_version="v3.1",
        snapshot_data=payload,
        source_data_cutoff_at="2026-07-31T00:00:00+00:00",
        existing_snapshots=[],
    )
    assert isinstance(new_snapshot["snapshot_data_json"], str)
    assert json.loads(new_snapshot["snapshot_data_json"]) == payload


def test_updated_snapshots_appends_new_snapshot_at_end():
    """Returned list contains all old snapshots plus the new one at the end."""

    existing = [
        {"id": 1, "report_revision": 1, "is_current": True},
    ]
    new_snapshot, updated = generate_report_snapshot(
        account_id=1001,
        observation_window="t7",
        position_segment="all",
        metric_version="v3.1",
        snapshot_data={"average_retention": 0.42},
        source_data_cutoff_at="2026-07-31T00:00:00+00:00",
        existing_snapshots=existing,
    )
    assert len(updated) == 2
    assert updated[-1] is new_snapshot


def test_existing_snapshots_list_not_mutated():
    """The caller's existing_snapshots list must not be mutated in place."""

    existing = [{"id": 1, "report_revision": 1, "is_current": True}]
    original_snapshot = dict(existing[0])
    generate_report_snapshot(
        account_id=1001,
        observation_window="t7",
        position_segment="all",
        metric_version="v3.1",
        snapshot_data={"average_retention": 0.42},
        source_data_cutoff_at="2026-07-31T00:00:00+00:00",
        existing_snapshots=existing,
    )
    assert existing[0] == original_snapshot
