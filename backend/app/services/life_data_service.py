"""Normalize and transactionally ingest business video data."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.app import AppActionTask
from app.models.life_data import (
    LifeDataAlertEvent,
    LifeDataCapture,
    LifeDataCollectorState,
    LifeDataVideoSnapshot,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc
RULE_CODE = "natural_play_2000"


@dataclass(frozen=True)
class NormalizedVideo:
    item_id: str
    title: str
    author_id: str | None
    author_name: str | None
    published_at: datetime | None
    play_count: int
    pay_gmv_fen: int
    verify_gmv_fen: int
    refund_gmv_fen: int
    metrics_hash: str
    metrics: dict[str, Any]


@dataclass(frozen=True)
class IngestResult:
    duplicate: bool
    videos_seen: int
    snapshots_created: int
    tasks_created: int


def extract_video_rows(response: dict) -> list[dict]:
    """Return valid rows from every nested itemRank.data list."""

    rows: list[dict] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if (
                    key.lower() == "itemrank"
                    and isinstance(child, dict)
                    and isinstance(child.get("data"), list)
                ):
                    rows.extend(
                        row
                        for row in child["data"]
                        if isinstance(row, dict)
                        and row.get("item_id") not in (None, "")
                        and row.get("item_play_cnt") not in (None, "")
                    )
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    if isinstance(response, dict):
        walk(response)
    return rows


def _first(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return default


def _to_int(value: Any, default: int = 0) -> int:
    if value in (None, "") or isinstance(value, bool):
        return default
    try:
        return int(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "") or isinstance(value, bool):
        return default
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _parse_item_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value)
        if abs(timestamp) >= 1_000_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=UTC)
    else:
        text_value = str(value).strip()
        if not text_value:
            return None
        try:
            timestamp = float(text_value)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            if abs(timestamp) >= 1_000_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=UTC)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(UTC)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(child) for child in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_video(
    row: dict,
    stat_start: date,
    stat_end: date,
    captured_at: datetime,
) -> NormalizedVideo:
    """Normalize a real itemRank row without changing fen-denominated amounts."""

    del captured_at  # Collection time must not make otherwise unchanged metrics unique.
    item_id = str(row["item_id"])
    title_value = _first(row, "item_desc", "item_title", "title")
    title = str(title_value).strip() if title_value not in (None, "") else item_id
    author_id = _optional_text(
        _first(row, "item_author_id", "author_id", "aweme_author_id")
    )
    author_name = _optional_text(
        _first(
            row,
            "item_author_nickname",
            "author_name",
            "author_nickname",
            "nickname",
        )
    )
    published_at = _parse_item_timestamp(row.get("item_create_ts"))
    play_count = _to_int(row.get("item_play_cnt"))
    pay_gmv_fen = _to_int(
        _first(
            row,
            "item_pay_gmv_all",
            "item_pay_gmv",
            "pay_gmv_fen",
            "pay_gmv",
            "item_pay_amt",
        )
    )
    verify_gmv_fen = _to_int(
        _first(
            row,
            "item_verify_gmv",
            "verify_gmv_fen",
            "verify_gmv",
            "item_verify_amt",
        )
    )
    refund_gmv_fen = _to_int(
        _first(row, "refund_gmv", "item_refund_gmv", "refund_gmv_fen")
    )

    item_like_cnt = _to_int(row.get("item_like_cnt"))
    item_comment_cnt = _to_int(row.get("item_comment_cnt"))
    item_favourite_cnt = _to_int(
        _first(row, "item_favourite_cnt", "item_favorite_cnt")
    )
    item_share_cnt = _to_int(row.get("item_share_cnt"))
    item_follow_cnt = _to_int(row.get("item_follow_cnt"))
    interaction_keys = (
        "item_like_cnt",
        "item_comment_cnt",
        "item_favourite_cnt",
        "item_favorite_cnt",
        "item_share_cnt",
        "item_follow_cnt",
    )
    has_real_interactions = any(
        row.get(key) not in (None, "") for key in interaction_keys
    )
    interaction_count = (
        item_like_cnt
        + item_comment_cnt
        + item_favourite_cnt
        + item_share_cnt
        + item_follow_cnt
        if has_real_interactions
        else _to_int(row.get("interaction_count"))
    )

    normalized_metrics = {
        "item_id": item_id,
        "play_count": play_count,
        "play_5s_rate": _to_float(
            _first(
                row,
                "play_5s_rate",
                "item_play_5s_rate",
                "item_5s_play_rate",
                "five_sec_play_rate",
            )
        ),
        "play_finish_rate": _to_float(
            _first(
                row,
                "play_finish_rate",
                "item_play_finish_rate",
                "finish_play_rate",
            )
        ),
        "avg_play_duration": _to_float(
            _first(
                row,
                "avg_play_duration",
                "item_avg_play_duration",
                "avg_play_time",
            )
        ),
        "item_duration": _to_float(row.get("item_duration")),
        "item_like_cnt": item_like_cnt,
        "item_comment_cnt": item_comment_cnt,
        "item_favourite_cnt": item_favourite_cnt,
        "item_share_cnt": item_share_cnt,
        "item_follow_cnt": item_follow_cnt,
        "interaction_count": interaction_count,
        "enter_poi_cnt": _to_int(
            _first(row, "enter_poi_cnt", "store_visit_count", "poi_visit_count")
        ),
        "pay_gmv_fen": pay_gmv_fen,
        "direct_pay_gmv_fen": _to_int(
            _first(row, "item_pay_gmv", "direct_pay_gmv_fen")
        ),
        "indirect_pay_gmv_fen": _to_int(
            _first(row, "item_indirect_pay_gmv", "indirect_pay_gmv_fen")
        ),
        "item_pay_cert_cnt": _to_int(
            _first(row, "item_pay_cert_cnt", "pay_cert_count")
        ),
        "verify_gmv_fen": verify_gmv_fen,
        "item_verify_cert_cnt": _to_int(
            _first(row, "item_verify_cert_cnt", "verify_cert_count")
        ),
        "refund_gmv_fen": refund_gmv_fen,
        "refund_cert_cnt": _to_int(
            _first(row, "refund_cert_cnt", "item_refund_cert_cnt")
        ),
        "thousand_play_pay_gmv_fen": _to_int(
            _first(row, "thous_play_pay_gmv", "thousand_play_pay_gmv_fen")
        ),
        "stat_start": stat_start.isoformat(),
        "stat_end": stat_end.isoformat(),
    }
    metrics = {
        **normalized_metrics,
        "raw_row": _json_safe(row),
    }
    return NormalizedVideo(
        item_id=item_id,
        title=title,
        author_id=author_id,
        author_name=author_name,
        published_at=published_at,
        play_count=play_count,
        pay_gmv_fen=pay_gmv_fen,
        verify_gmv_fen=verify_gmv_fen,
        refund_gmv_fen=refund_gmv_fen,
        metrics_hash=_canonical_hash(normalized_metrics),
        metrics=metrics,
    )


def should_create_alert(
    play_count: int,
    existing_alert: bool,
    threshold: int = 2000,
) -> bool:
    return play_count >= threshold and not existing_alert


def _body_mapping(body: Any) -> dict[str, Any]:
    if isinstance(body, Mapping):
        return dict(body)
    model_dump = getattr(body, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    names = (
        "schema_version",
        "event_id",
        "account_id",
        "status",
        "queue_depth",
        "last_error",
        "page_path",
        "endpoint",
        "request_payload",
        "response_payload",
        "captured_at",
    )
    return {name: getattr(body, name) for name in names}


def _captured_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value)
        if abs(timestamp) >= 1_000_000_000_000:
            timestamp /= 1000
        parsed = datetime.fromtimestamp(timestamp, tz=UTC)
    elif value not in (None, ""):
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    else:
        parsed = datetime.now(tz=UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


_START_DATE_KEYS = {
    "stat_start",
    "start_date",
    "date_start",
    "begin_date",
    "startdate",
    "begindate",
}
_END_DATE_KEYS = {
    "stat_end",
    "end_date",
    "date_end",
    "finish_date",
    "enddate",
    "finishdate",
}


def _find_nested_value(value: Any, names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in names and child not in (None, ""):
                return child
        for child in value.values():
            found = _find_nested_value(child, names)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_nested_value(child, names)
            if found not in (None, ""):
                return found
    return None


def _as_date(value: Any, fallback: date) -> date:
    if value in (None, ""):
        return fallback
    if isinstance(value, datetime):
        return value.astimezone(SHANGHAI).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    text_value = str(value).strip()
    if len(text_value) == 8 and text_value.isdigit():
        return datetime.strptime(text_value, "%Y%m%d").date()
    try:
        return date.fromisoformat(text_value[:10])
    except ValueError:
        parsed = _parse_item_timestamp(value)
        return parsed.astimezone(SHANGHAI).date() if parsed else fallback


def _stat_period(request_payload: dict, captured_at: datetime) -> tuple[date, date]:
    fallback = captured_at.astimezone(SHANGHAI).date()
    start = _as_date(_find_nested_value(request_payload, _START_DATE_KEYS), fallback)
    end = _as_date(_find_nested_value(request_payload, _END_DATE_KEYS), fallback)
    return (start, end) if start <= end else (end, start)


def _result_id(result: Any) -> Any:
    method = getattr(result, "scalar_one_or_none", None)
    if callable(method):
        return method()
    method = getattr(result, "scalar", None)
    return method() if callable(method) else None


async def _upsert_collector_state(
    db: Any,
    *,
    account_id: str,
    seen_at: datetime,
    status: str,
    queue_depth: int,
    event_id: str | None = None,
    success: bool = False,
    last_error: str | None = None,
    template_count: int | None = None,
    last_full_success_at: datetime | None = None,
    group_health: dict[str, Any] | None = None,
) -> None:
    values: dict[str, Any] = {
        "account_id": account_id,
        "status": status,
        "last_seen_at": seen_at,
        "queue_depth": queue_depth,
        "updated_at": seen_at,
    }
    if success:
        values.update(last_success_at=seen_at, last_event_id=event_id)
    if status == "error":
        values.update(last_error_at=seen_at, last_error=last_error)
    if template_count is not None:
        values["template_count"] = template_count
    if last_full_success_at is not None:
        values["last_full_success_at"] = last_full_success_at
    if group_health is not None:
        values["group_health"] = group_health

    statement = pg_insert(LifeDataCollectorState).values(**values)
    incoming_is_latest = LifeDataCollectorState.last_seen_at.is_(None) | (
        statement.excluded.last_seen_at >= LifeDataCollectorState.last_seen_at
    )
    update_values: dict[str, Any] = {
        "status": case(
            (incoming_is_latest, statement.excluded.status),
            else_=LifeDataCollectorState.status,
        ),
        "queue_depth": case(
            (incoming_is_latest, statement.excluded.queue_depth),
            else_=LifeDataCollectorState.queue_depth,
        ),
        "last_seen_at": func.greatest(
            LifeDataCollectorState.last_seen_at,
            statement.excluded.last_seen_at,
        ),
        "updated_at": func.greatest(
            LifeDataCollectorState.updated_at,
            statement.excluded.updated_at,
        ),
    }
    if success:
        update_values.update(
            last_success_at=func.greatest(
                LifeDataCollectorState.last_success_at,
                statement.excluded.last_success_at,
            ),
            last_event_id=case(
                (
                    LifeDataCollectorState.last_success_at.is_(None)
                    | (
                        statement.excluded.last_success_at
                        > LifeDataCollectorState.last_success_at
                    ),
                    statement.excluded.last_event_id,
                ),
                else_=LifeDataCollectorState.last_event_id,
            ),
        )
    if status == "error":
        update_values.update(
            last_error_at=func.greatest(
                LifeDataCollectorState.last_error_at,
                statement.excluded.last_error_at,
            ),
            last_error=case(
                (
                    LifeDataCollectorState.last_error_at.is_(None)
                    | (
                        statement.excluded.last_error_at
                        > LifeDataCollectorState.last_error_at
                    ),
                    statement.excluded.last_error,
                ),
                else_=LifeDataCollectorState.last_error,
            ),
        )
    if template_count is not None:
        update_values["template_count"] = case(
            (incoming_is_latest, statement.excluded.template_count),
            else_=LifeDataCollectorState.template_count,
        )
    if group_health is not None:
        update_values["group_health"] = case(
            (incoming_is_latest, statement.excluded.group_health),
            else_=LifeDataCollectorState.group_health,
        )
    if last_full_success_at is not None:
        update_values["last_full_success_at"] = func.greatest(
            LifeDataCollectorState.last_full_success_at,
            statement.excluded.last_full_success_at,
        )
    statement = statement.on_conflict_do_update(
        index_elements=[LifeDataCollectorState.account_id],
        set_=update_values,
    ).returning(LifeDataCollectorState.id)
    await db.execute(statement)


class LifeDataIngestService:
    def __init__(self, task_creator_id: int, alert_threshold: int = 2000):
        self.task_creator_id = task_creator_id
        self.alert_threshold = alert_threshold

    async def ingest(self, db: Any, body: Any) -> IngestResult:
        payload = _body_mapping(body)
        captured_at = _captured_at(payload.get("captured_at"))
        received_at = datetime.now(tz=UTC)
        event_id = str(payload["event_id"])
        account_id = str(payload["account_id"])
        queue_depth = _to_int(payload.get("queue_depth"))
        request_payload = payload["request_payload"]
        response_payload = payload["response_payload"]

        if not isinstance(response_payload, dict):
            raise ValueError("LifeData response_payload must be an object")
        response_code = response_payload.get("code")
        if type(response_code) is not int or response_code != 0:
            raise ValueError("LifeData response code must be 0")
        rows = extract_video_rows(response_payload)
        if (
            str(payload["page_path"]).rstrip("/")
            == "/flow/content/analysis/video"
            and not rows
        ):
            raise ValueError("LifeData video response has no valid itemRank row")

        capture_statement = (
            pg_insert(LifeDataCapture)
            .values(
                event_id=event_id,
                account_id=account_id,
                page_path=str(payload["page_path"]),
                endpoint=str(payload["endpoint"]),
                request_payload=request_payload,
                response_payload=response_payload,
                response_hash=_canonical_hash(response_payload),
                captured_at=captured_at,
            )
            .on_conflict_do_nothing(index_elements=[LifeDataCapture.event_id])
            .returning(LifeDataCapture.id)
        )
        capture_id = _result_id(await db.execute(capture_statement))
        if capture_id is None:
            await _upsert_collector_state(
                db,
                account_id=account_id,
                seen_at=received_at,
                status="online",
                queue_depth=queue_depth,
                event_id=event_id,
                success=True,
            )
            return IngestResult(True, 0, 0, 0)

        stat_start, stat_end = _stat_period(request_payload, captured_at)
        snapshots_created = 0
        tasks_created = 0

        for row in rows:
            video = normalize_video(row, stat_start, stat_end, captured_at)
            snapshot_statement = (
                pg_insert(LifeDataVideoSnapshot)
                .values(
                    account_id=account_id,
                    item_id=video.item_id,
                    title=video.title,
                    author_id=video.author_id,
                    author_name=video.author_name,
                    published_at=video.published_at,
                    stat_start=stat_start,
                    stat_end=stat_end,
                    play_count=video.play_count,
                    pay_gmv_fen=video.pay_gmv_fen,
                    verify_gmv_fen=video.verify_gmv_fen,
                    refund_gmv_fen=video.refund_gmv_fen,
                    metrics_hash=video.metrics_hash,
                    metrics=video.metrics,
                    captured_at=captured_at,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        LifeDataVideoSnapshot.account_id,
                        LifeDataVideoSnapshot.item_id,
                        LifeDataVideoSnapshot.metrics_hash,
                    ]
                )
                .returning(LifeDataVideoSnapshot.id)
            )
            snapshot_id = _result_id(await db.execute(snapshot_statement))
            if snapshot_id is not None:
                snapshots_created += 1

            if not should_create_alert(
                video.play_count,
                existing_alert=False,
                threshold=self.alert_threshold,
            ):
                continue

            alert_statement = (
                pg_insert(LifeDataAlertEvent)
                .values(
                    account_id=account_id,
                    item_id=video.item_id,
                    rule_code=RULE_CODE,
                    snapshot_id=snapshot_id,
                    play_count=video.play_count,
                    triggered_at=captured_at,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        LifeDataAlertEvent.account_id,
                        LifeDataAlertEvent.item_id,
                        LifeDataAlertEvent.rule_code,
                    ]
                )
                .returning(LifeDataAlertEvent.id)
            )
            alert_id = _result_id(await db.execute(alert_statement))
            if alert_id is None:
                continue

            evidence = {
                "video": {
                    "item_id": video.item_id,
                    "title": video.title,
                    "author_id": video.author_id,
                    "author_name": video.author_name,
                    "published_at": (
                        video.published_at.isoformat()
                        if video.published_at is not None
                        else None
                    ),
                },
                "play_count": video.play_count,
                "play_increment": None,
                "play_5s_rate": video.metrics["play_5s_rate"],
                "play_finish_rate": video.metrics["play_finish_rate"],
                "interaction_count": video.metrics["interaction_count"],
                "pay_gmv_fen": video.pay_gmv_fen,
                "verify_gmv_fen": video.verify_gmv_fen,
                "refund_gmv_fen": video.refund_gmv_fen,
                "stat_start": stat_start.isoformat(),
                "stat_end": stat_end.isoformat(),
            }
            task_statement = (
                pg_insert(AppActionTask)
                .values(
                    task_no=f"LIFE{int(alert_id):027d}",
                    title=(
                        f"\u3010\u81ea\u7136\u6d41\u91cf\u8fbe\u6807\u3011{video.title}"
                    )[:256],
                    description=(
                        f"\u89c6\u9891\u81ea\u7136\u64ad\u653e\u9996\u6b21\u8fbe\u5230"
                        f"{self.alert_threshold}\u6b21\u9608\u503c\uff0c\u8bf7\u7ed3\u5408"
                        "\u6210\u4ea4\u3001\u6838\u9500\u548c\u9000\u6b3e\u8bc1\u636e"
                        "\u4eba\u5de5\u786e\u8ba4\u662f\u5426\u5c0f\u989d\u6295\u653e\u3002"
                    ),
                    data_evidence=evidence,
                    data_evidence_text=(
                        f"\u89c6\u9891 {video.item_id} \u81ea\u7136\u64ad\u653e"
                        f"{video.play_count}\u6b21\uff0c\u7edf\u8ba1\u5468\u671f"
                        f"{stat_start.isoformat()}\u81f3{stat_end.isoformat()}\u3002"
                    ),
                    suggested_actions=[
                        "\u4eba\u5de5\u786e\u8ba4\u540e\u5f00\u5c55\u5c0f\u989d"
                        "\u6d4b\u8bd5\u6295\u653e\uff0c\u5e76\u8bb0\u5f55\u5b9e"
                        "\u9645\u6838\u9500\u4ea7\u51fa\u3002"
                    ],
                    review_metrics=[
                        "\u5b9e\u9645\u6838\u9500\u91d1\u989d\uff08\u5206\uff09",
                        "\u9000\u6b3e\u91d1\u989d\uff08\u5206\uff09",
                        "\u6210\u4ea4\u91d1\u989d\uff08\u5206\uff09",
                    ],
                    feedback_requirement=(
                        "\u8bf7\u53cd\u9988\u662f\u5426\u6295\u653e\u3001\u6295"
                        "\u5165\u91d1\u989d\u3001\u5b9e\u9645\u6838\u9500\u91d1"
                        "\u989d\u53ca\u9000\u6b3e\u60c5\u51b5\u3002"
                    ),
                    source_type="life_data_rule",
                    source_id=alert_id,
                    related_date=stat_end,
                    creator_id=self.task_creator_id,
                    due_date=None,
                    status="draft",
                    priority=8,
                    risk_level="medium",
                    requires_human_confirm=True,
                    is_deleted=False,
                )
                .on_conflict_do_nothing(index_elements=[AppActionTask.task_no])
                .returning(AppActionTask.id)
            )
            task_id = _result_id(await db.execute(task_statement))
            if task_id is None:
                continue
            tasks_created += 1
            await db.execute(
                update(LifeDataAlertEvent)
                .where(LifeDataAlertEvent.id == alert_id)
                .values(task_id=task_id)
            )

        await _upsert_collector_state(
            db,
            account_id=account_id,
            seen_at=received_at,
            status="online",
            queue_depth=queue_depth,
            event_id=event_id,
            success=True,
        )
        return IngestResult(
            duplicate=False,
            videos_seen=len(rows),
            snapshots_created=snapshots_created,
            tasks_created=tasks_created,
        )

    async def update_status(self, db: Any, body: Any) -> None:
        """Persist a heartbeat or sanitized error using server receive time."""

        payload = _body_mapping(body)
        provided_fields = getattr(body, "model_fields_set", set(payload))
        status = str(payload["status"])
        last_error = payload.get("last_error")
        if status == "error" and not str(last_error or "").strip():
            raise ValueError("error collector status requires last_error")

        await _upsert_collector_state(
            db,
            account_id=str(payload["account_id"]),
            seen_at=datetime.now(tz=UTC),
            status=status,
            queue_depth=_to_int(payload.get("queue_depth")),
            last_error=str(last_error) if last_error is not None else None,
            template_count=(
                _to_int(payload.get("template_count"))
                if "template_count" in provided_fields
                else None
            ),
            last_full_success_at=payload.get("last_full_success_at"),
            group_health=(
                {
                    str(name): {
                        str(key): (
                            value.isoformat() if isinstance(value, datetime) else value
                        )
                        for key, value in (
                            health.model_dump().items()
                            if hasattr(health, "model_dump")
                            else health.items()
                        )
                    }
                    for name, health in (payload.get("groups") or {}).items()
                }
                if "groups" in provided_fields
                else None
            ),
        )
