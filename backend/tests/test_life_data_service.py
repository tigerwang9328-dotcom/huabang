import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from app.services.life_data_service import (
    LifeDataIngestService,
    extract_video_rows,
    normalize_video,
    should_create_alert,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "life_data_video_response.json"
CAPTURED_AT = datetime(2026, 7, 12, 1, 2, 3, tzinfo=timezone.utc)
STAT_START = date(2026, 7, 5)
STAT_END = date(2026, 7, 11)


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def make_body(event_id: str = "event-000000000001") -> dict:
    return {
        "schema_version": "1",
        "event_id": event_id,
        "account_id": "1798826701211732",
        "page_path": "/flow/content/analysis/video",
        "endpoint": "/api/dito/query",
        "request_payload": {
            "biz_params": {
                "common_params": {
                    "start_date": "2026-07-05",
                    "end_date": "2026-07-11",
                }
            }
        },
        "response_payload": load_fixture(),
        "captured_at": CAPTURED_AT.isoformat(),
    }


def test_extract_and_normalize_video_fixture_uses_real_api_keys():
    rows = extract_video_rows(load_fixture())
    video = normalize_video(rows[0], STAT_START, STAT_END, CAPTURED_AT)

    assert video.item_id == "video-over-2000"
    assert video.title == "summer outfit video"
    assert video.author_name == "example creator"
    assert video.play_count == 34310
    assert video.pay_gmv_fen == 5700
    assert video.verify_gmv_fen == 0
    assert video.refund_gmv_fen == 125
    assert video.published_at == datetime(2026, 7, 10, 0, 30, tzinfo=timezone.utc)
    assert video.metrics["play_5s_rate"] == 0.49048197
    assert video.metrics["interaction_count"] == 321
    assert video.metrics["direct_pay_gmv_fen"] == 4500
    assert video.metrics["indirect_pay_gmv_fen"] == 1200
    assert video.metrics["raw_row"]["item_pay_gmv"] == 4500
    assert video.metrics["raw_row"]["item_verify_cert_cnt"] == 3
    assert video.metrics["raw_row"]["enter_poi_cnt"] == 42
    assert video.metrics["raw_row"]["thous_play_pay_gmv"] == 131


def test_normalize_video_uses_item_id_when_title_is_empty():
    row = extract_video_rows(load_fixture())[0]
    row["item_desc"] = ""
    row["item_title"] = ""

    video = normalize_video(row, STAT_START, STAT_END, CAPTURED_AT)

    assert video.title == "video-over-2000"


@pytest.mark.parametrize(
    ("raw_timestamp", "expected"),
    [
        ("2026-07-10 08:30:00", datetime(2026, 7, 10, 0, 30, tzinfo=timezone.utc)),
        (1783643400, datetime(2026, 7, 10, 0, 30, tzinfo=timezone.utc)),
        (1783643400000, datetime(2026, 7, 10, 0, 30, tzinfo=timezone.utc)),
        ("", None),
        (None, None),
    ],
)
def test_normalize_video_accepts_real_timestamp_variants(raw_timestamp, expected):
    row = extract_video_rows(load_fixture())[0]
    row["item_create_ts"] = raw_timestamp

    video = normalize_video(row, STAT_START, STAT_END, CAPTURED_AT)

    assert video.published_at == expected


def test_metrics_hash_is_stable_for_key_order_and_capture_time():
    row = extract_video_rows(load_fixture())[0]
    reversed_row = dict(reversed(list(row.items())))

    first = normalize_video(row, STAT_START, STAT_END, CAPTURED_AT)
    second = normalize_video(
        reversed_row,
        STAT_START,
        STAT_END,
        datetime(2026, 7, 12, 2, 3, 4, tzinfo=timezone.utc),
    )

    assert first.metrics_hash == second.metrics_hash


def test_metrics_hash_ignores_title_and_unknown_raw_fields():
    row = extract_video_rows(load_fixture())[0]
    changed = deepcopy(row)
    changed["item_desc"] = "a renamed title"
    changed["new_unknown_field"] = {"future": "api metadata"}

    first = normalize_video(row, STAT_START, STAT_END, CAPTURED_AT)
    second = normalize_video(changed, STAT_START, STAT_END, CAPTURED_AT)

    assert first.metrics_hash == second.metrics_hash
    assert second.metrics["raw_row"]["new_unknown_field"] == {
        "future": "api metadata"
    }
    assert "raw" not in second.metrics


def test_metrics_hash_changes_when_normalized_play_count_changes():
    row = extract_video_rows(load_fixture())[0]
    changed = deepcopy(row)
    changed["item_play_cnt"] = row["item_play_cnt"] + 1

    first = normalize_video(row, STAT_START, STAT_END, CAPTURED_AT)
    second = normalize_video(changed, STAT_START, STAT_END, CAPTURED_AT)

    assert first.metrics_hash != second.metrics_hash


def test_extract_video_rows_ignores_non_video_item_rank_entries():
    body = load_fixture()
    body["data"]["rankings"]["itemRank"]["data"].extend(
        [
            {"item_id": "missing-play-count"},
            {"item_play_cnt": 100},
            "not-a-dict",
        ]
    )

    rows = extract_video_rows(body)

    assert [row["item_id"] for row in rows] == ["video-over-2000"]


def test_threshold_is_inclusive_and_once():
    assert should_create_alert(play_count=2000, existing_alert=False) is True
    assert should_create_alert(play_count=1999, existing_alert=False) is False
    assert should_create_alert(play_count=34310, existing_alert=True) is False


class FakeResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value


def statement_values(statement) -> dict:
    values = {}
    for key, bound in getattr(statement, "_values", {}).items():
        name = getattr(key, "key", key)
        values[name] = getattr(bound, "value", bound)
    return values


class FakeAsyncSession:
    def __init__(self):
        self.captures = {}
        self.snapshots = {}
        self.alerts = {}
        self.tasks = []
        self.collector_state_writes = []
        self.calls = []

    async def execute(self, statement):
        table_name = getattr(getattr(statement, "table", None), "name", None)
        values = statement_values(statement)
        self.calls.append((table_name, values, statement))

        if getattr(statement, "is_update", False):
            return FakeResult()

        if table_name == "life_data_capture":
            event_id = values["event_id"]
            if event_id in self.captures:
                return FakeResult()
            capture_id = len(self.captures) + 1
            self.captures[event_id] = values
            return FakeResult(capture_id)

        if table_name == "life_data_video_snapshot":
            key = (
                values["account_id"],
                values["item_id"],
                values["metrics_hash"],
            )
            if key in self.snapshots:
                return FakeResult()
            snapshot_id = len(self.snapshots) + 101
            self.snapshots[key] = values
            return FakeResult(snapshot_id)

        if table_name == "life_data_alert_event":
            key = (
                values["account_id"],
                values["item_id"],
                values["rule_code"],
            )
            if key in self.alerts:
                return FakeResult()
            alert_id = len(self.alerts) + 1001
            self.alerts[key] = values
            return FakeResult(alert_id)

        if table_name == "app_action_task":
            task_id = len(self.tasks) + 2001
            self.tasks.append(values)
            return FakeResult(task_id)

        if table_name == "life_data_collector_state":
            self.collector_state_writes.append(values)
            return FakeResult(3001)

        raise AssertionError(f"Unexpected statement table: {table_name}")


@pytest.mark.asyncio
async def test_ingest_creates_snapshot_alert_task_and_online_state():
    db = FakeAsyncSession()
    service = LifeDataIngestService(task_creator_id=1, alert_threshold=2000)

    received_before = datetime.now(timezone.utc)
    result = await service.ingest(db, make_body())
    received_after = datetime.now(timezone.utc)

    assert result.duplicate is False
    assert result.videos_seen == 1
    assert result.snapshots_created == 1
    assert result.tasks_created == 1
    assert len(db.tasks) == 1
    task = db.tasks[0]
    assert task["status"] == "draft"
    assert task["priority"] == 8
    assert task["risk_level"] == "medium"
    assert task["source_type"] == "life_data_rule"
    assert task["requires_human_confirm"] is True
    assert task["due_date"] is None
    assert task["creator_id"] == 1
    text_fields = [
        task["title"],
        task["description"],
        task["data_evidence_text"],
        task["feedback_requirement"],
        *task["suggested_actions"],
        *task["review_metrics"],
    ]
    assert all(any("\u4e00" <= char <= "\u9fff" for char in text) for text in text_fields)
    assert task["data_evidence"]["play_count"] == 34310
    assert task["data_evidence"]["pay_gmv_fen"] == 5700
    assert task["data_evidence"]["verify_gmv_fen"] == 0
    assert task["data_evidence"]["refund_gmv_fen"] == 125
    assert task["data_evidence"]["stat_start"] == "2026-07-05"
    assert task["data_evidence"]["stat_end"] == "2026-07-11"
    state = db.collector_state_writes[-1]
    assert state["status"] == "online"
    assert received_before <= state["last_seen_at"] <= received_after
    assert state["last_success_at"] == state["last_seen_at"]
    assert state["updated_at"] == state["last_seen_at"]
    assert state["last_event_id"] == "event-000000000001"


@pytest.mark.asyncio
async def test_ingest_duplicate_event_refreshes_seen_without_more_work():
    db = FakeAsyncSession()
    service = LifeDataIngestService(task_creator_id=1, alert_threshold=2000)
    body = make_body()

    await service.ingest(db, body)
    duplicate_before = datetime.now(timezone.utc)
    duplicate = await service.ingest(db, body)
    duplicate_after = datetime.now(timezone.utc)

    assert duplicate.duplicate is True
    assert duplicate.videos_seen == 0
    assert duplicate.snapshots_created == 0
    assert duplicate.tasks_created == 0
    assert len(db.snapshots) == 1
    assert len(db.alerts) == 1
    assert len(db.tasks) == 1
    assert len(db.collector_state_writes) == 2
    duplicate_state = db.collector_state_writes[-1]
    assert duplicate_before <= duplicate_state["last_seen_at"] <= duplicate_after
    assert duplicate_state["last_success_at"] == duplicate_state["last_seen_at"]
    assert duplicate_state["updated_at"] == duplicate_state["last_seen_at"]
    assert duplicate_state["last_event_id"] == "event-000000000001"


@pytest.mark.asyncio
async def test_collector_state_upsert_keeps_all_timestamps_monotonic():
    db = FakeAsyncSession()
    service = LifeDataIngestService(task_creator_id=1, alert_threshold=2000)

    await service.ingest(db, make_body())

    state_statement = next(
        statement
        for table_name, _values, statement in reversed(db.calls)
        if table_name == "life_data_collector_state"
    )
    sql = str(state_statement.compile(dialect=postgresql.dialect())).lower()
    assert "last_seen_at = greatest(" in sql
    assert "last_success_at = greatest(" in sql
    assert "updated_at = greatest(" in sql
    assert "last_event_id = case when" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_payload",
    [
        {"code": 1, "data": {"itemRank": {"data": []}}},
        {
            "code": 0,
            "data": {
                "itemRank": {"data": [{"item_id": "missing-play-count"}]}
            },
        },
    ],
)
async def test_ingest_defensively_rejects_invalid_video_response_without_success_state(
    response_payload,
):
    db = FakeAsyncSession()
    service = LifeDataIngestService(task_creator_id=1, alert_threshold=2000)
    body = make_body()
    body["response_payload"] = response_payload

    with pytest.raises(ValueError):
        await service.ingest(db, body)

    assert db.captures == {}
    assert db.collector_state_writes == []


@pytest.mark.asyncio
async def test_ingest_unchanged_metrics_adds_capture_but_no_snapshot_or_task():
    db = FakeAsyncSession()
    service = LifeDataIngestService(task_creator_id=1, alert_threshold=2000)

    await service.ingest(db, make_body("event-000000000001"))
    unchanged = await service.ingest(db, make_body("event-000000000002"))

    assert unchanged.duplicate is False
    assert unchanged.videos_seen == 1
    assert unchanged.snapshots_created == 0
    assert unchanged.tasks_created == 0
    assert len(db.captures) == 2
    assert len(db.snapshots) == 1
    assert len(db.alerts) == 1
    assert len(db.tasks) == 1


@pytest.mark.asyncio
async def test_ingest_creates_alert_only_when_play_count_crosses_threshold():
    db = FakeAsyncSession()
    service = LifeDataIngestService(task_creator_id=1, alert_threshold=2000)
    results = []

    for index, play_count in enumerate((1999, 2000, 2100), start=1):
        body = make_body(f"event-crossing-{index:04d}")
        row = extract_video_rows(body["response_payload"])[0]
        row["item_play_cnt"] = play_count
        results.append(await service.ingest(db, body))

    assert [result.tasks_created for result in results] == [0, 1, 0]
    assert len(db.snapshots) == 3
    assert len(db.alerts) == 1
    assert len(db.tasks) == 1


@pytest.mark.asyncio
async def test_ingest_period_falls_back_to_shanghai_capture_date_and_orders_dates():
    db = FakeAsyncSession()
    service = LifeDataIngestService(task_creator_id=1, alert_threshold=2000)
    body = make_body()
    body["request_payload"] = {
        "nested": {
            "start_date": "2026-07-15",
            "end_date": "2026-07-14",
        }
    }

    await service.ingest(db, body)

    snapshot = next(iter(db.snapshots.values()))
    assert snapshot["stat_start"] == date(2026, 7, 14)
    assert snapshot["stat_end"] == date(2026, 7, 15)

    fallback_db = FakeAsyncSession()
    fallback_body = make_body("event-000000000003")
    fallback_body["request_payload"] = {}
    fallback_body["captured_at"] = "2026-07-12T17:00:00+00:00"

    await service.ingest(fallback_db, fallback_body)

    fallback_snapshot = next(iter(fallback_db.snapshots.values()))
    assert fallback_snapshot["stat_start"] == date(2026, 7, 13)
    assert fallback_snapshot["stat_end"] == date(2026, 7, 13)
