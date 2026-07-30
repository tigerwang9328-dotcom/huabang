"""Deterministic primitives for the frozen collector multipart protocol."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from typing import Iterable


class IngestProtocolError(ValueError):
    """A stable, client-visible protocol error code without untrusted detail."""


def is_expected_online(*, now_local: datetime, schedules: list[dict[str, object]]) -> bool:
    """Evaluate stored local schedules; bit zero is Monday and overnight spans use the prior day."""

    current_time = now_local.timetz().replace(tzinfo=None)
    weekday = now_local.weekday()
    for schedule in schedules:
        start = schedule["start"]
        end = schedule["end"]
        mask = int(schedule["weekday_mask"])
        if not isinstance(start, time) or not isinstance(end, time):
            raise IngestProtocolError("invalid_expected_schedule")
        if start <= end:
            if mask & (1 << weekday) and start <= current_time < end:
                return True
        elif current_time >= start and mask & (1 << weekday):
            return True
        elif current_time < end and mask & (1 << ((weekday - 1) % 7)):
            return True
    return False


def canonical_snapshot_hash(snapshot: object) -> str:
    """Deduplicate content rather than a collector retry or JSON key ordering."""

    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def response_snapshot_hash(record: dict[str, object]) -> str:
    """Hash the whitelisted server-side response body, never a client-supplied hash."""

    return canonical_snapshot_hash(whitelist_raw_response(record))


def _whitelist_curve_points(points: object) -> list[dict[str, object]]:
    if not isinstance(points, list):
        raise IngestProtocolError("invalid_response_data")
    approved: list[dict[str, object]] = []
    for point in points:
        if not isinstance(point, dict) or set(point) - {"key", "second", "value"}:
            raise IngestProtocolError("raw_response_field_forbidden")
        if "value" not in point or "key" not in point and "second" not in point:
            raise IngestProtocolError("invalid_curve_point")
        clean: dict[str, object] = {"value": point["value"]}
        if "key" in point:
            clean["key"] = point["key"]
        if "second" in point:
            clean["second"] = point["second"]
        approved.append(clean)
    return approved


def whitelist_raw_response(record: dict[str, object]) -> dict[str, object]:
    """Persist only the frozen raw-curve evidence schema, never diagnostic text."""

    response_data = record.get("response_data")
    if not isinstance(response_data, dict):
        raise IngestProtocolError("invalid_response_data")
    allowed_response_fields = {"analysis_trend", "status_code", "status_msg", "valley_list", "valley_related_items"}
    if set(response_data) - allowed_response_fields:
        raise IngestProtocolError("raw_response_field_forbidden")
    trend = response_data.get("analysis_trend")
    if not isinstance(trend, dict) or set(trend) - {"current_item", "similar_author"}:
        raise IngestProtocolError("raw_response_field_forbidden")
    if "current_item" not in trend:
        raise IngestProtocolError("invalid_response_data")
    approved_trend: dict[str, object] = {"current_item": _whitelist_curve_points(trend["current_item"])}
    if "similar_author" in trend:
        approved_trend["similar_author"] = _whitelist_curve_points(trend["similar_author"])
    result: dict[str, object] = {"analysis_trend": approved_trend}
    if type(response_data.get("status_code")) is int:
        result["status_code"] = response_data["status_code"]
    return result


def summarize_item_statuses(statuses: Iterable[str]) -> dict[str, int]:
    """Keep the batch counters reconciled with persisted CollectionItem rows."""

    materialized = list(statuses)
    return {
        "item_count": len(materialized),
        "success_count": sum(status == "success" for status in materialized),
        "skipped_count": sum(status == "skipped_non_video" for status in materialized),
        "failure_count": sum(status not in {"success", "skipped_non_video"} for status in materialized),
    }


def _curve_second(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and len(value) == 5 and value[2] == ":":
        minutes, seconds = value.split(":")
        return int(minutes) * 60 + int(seconds)
    raise IngestProtocolError("invalid_curve_point")


def normalize_analysis_response(record: dict[str, object]) -> dict[str, object]:
    """Normalize one approved analytics response without mixing analysis types."""

    analysis_type = record.get("analysis_type")
    if analysis_type not in (1, 7):
        raise IngestProtocolError("analysis_type_unsupported")
    http_status = record.get("http_status")
    business_status_code = record.get("business_status_code")
    if http_status != 200:
        return {
            "analysis_type": analysis_type,
            "item_status": "rate_limited" if http_status == 429 else "http_failed",
            "normalized_curve": None,
        }
    if business_status_code not in (None, 0):
        return {"analysis_type": analysis_type, "item_status": "business_failed", "normalized_curve": None}
    response_data = record.get("response_data")
    if not isinstance(response_data, dict):
        raise IngestProtocolError("invalid_response_data")
    trend = response_data.get("analysis_trend")
    if not isinstance(trend, dict) or not isinstance(trend.get("current_item"), list):
        raise IngestProtocolError("invalid_response_data")
    curve: list[dict[str, float | int]] = []
    for point in trend["current_item"]:
        if not isinstance(point, dict) or "value" not in point:
            raise IngestProtocolError("invalid_curve_point")
        raw_value = float(point["value"])
        normalized_value = raw_value / 100 if raw_value > 1 else raw_value
        if not 0 <= normalized_value <= 1:
            raise IngestProtocolError("invalid_curve_point")
        curve.append({"second": _curve_second(point.get("second", point.get("key"))), "value": normalized_value})
    curve.sort(key=lambda point: int(point["second"]))
    return {
        "analysis_type": analysis_type,
        "item_status": "success" if curve else "empty_curve",
        "normalized_curve": curve,
    }


def expand_collection_record(record: dict[str, object]) -> list[dict[str, object]]:
    """Split a catalog video into independent retention and platform-bounce inputs."""

    video_id = record.get("video_id")
    if not isinstance(video_id, str) or not video_id:
        raise IngestProtocolError("video_id_invalid")
    if record.get("source_type") not in (None, "video") or (
        "retention" not in record and "platform_bounce" not in record
    ):
        return [{
            "video_id": video_id,
            "analysis_type": None,
            "item_status": "skipped_non_video",
            "error_category": str(record.get("skip_reason") or "non_video"),
        }]
    expanded: list[dict[str, object]] = []
    for field in ("retention", "platform_bounce"):
        analysis = record.get(field)
        if not isinstance(analysis, dict):
            raise IngestProtocolError("analysis_response_missing")
        expanded.append({
            **analysis,
            "video_id": video_id,
            "duration_ms": record.get("duration_ms"),
            "source_type": "video",
            "sanitized_title": record.get("sanitized_title"),
            "published_at_epoch_seconds": record.get("published_at_epoch_seconds"),
        })
    return expanded


def validate_part_number(*, part_number: int, part_count: int) -> None:
    """Keep part identities within the immutable declared batch cardinality."""

    if not 1 <= part_number <= part_count:
        raise IngestProtocolError("part_number_invalid")


def derive_collector_status(
    *,
    last_heartbeat_at: datetime | None,
    now: datetime,
    expected_online: bool,
    document_visibility: str | None,
    auth_failed: bool,
    upload_blocked: bool,
    suspended: bool = False,
) -> str:
    """Map trusted heartbeat facts to the frozen, alert-safe collector status."""

    if auth_failed:
        return "auth_required"
    if upload_blocked:
        return "upload_blocked"
    if suspended:
        return "suspended"
    if last_heartbeat_at is not None and last_heartbeat_at >= now - timedelta(minutes=5):
        return "online_hidden" if document_visibility == "hidden" else "online_active"
    if expected_online and (
        last_heartbeat_at is None or last_heartbeat_at <= now - timedelta(minutes=10)
    ):
        return "offline_unexpected"
    return "offline_expected"


def compute_batch_hash(parts: Iterable[tuple[int, str]], *, expected_part_count: int) -> str:
    """Hash complete parts in their canonical numeric order."""

    parts_by_number: dict[int, str] = {}
    for part_number, part_hash in parts:
        if part_number in parts_by_number:
            raise IngestProtocolError("part_content_conflict")
        parts_by_number[part_number] = part_hash
    expected_numbers = set(range(1, expected_part_count + 1))
    if set(parts_by_number) != expected_numbers:
        raise IngestProtocolError("missing_parts")
    return hashlib.sha256(
        "|".join(parts_by_number[number] for number in range(1, expected_part_count + 1)).encode("ascii")
    ).hexdigest()


def validate_part_contract(
    frozen: dict[str, object], incoming: dict[str, object], *, existing_part_hash: str | None
) -> bool:
    """Enforce immutable batch identity and return whether this is an idempotent retry."""

    for field, error_code in (
        ("account_id", "creator_account_mismatch"),
        ("part_count", "part_count_conflict"),
        ("schema_version", "schema_version_conflict"),
        ("observed_creator_fingerprint", "creator_account_mismatch"),
        ("installation_id", "installation_conflict"),
    ):
        if frozen[field] != incoming[field]:
            raise IngestProtocolError(error_code)
    incoming_hash = str(incoming["part_hash"])
    if existing_part_hash is None:
        return False
    if existing_part_hash != incoming_hash:
        raise IngestProtocolError("part_content_conflict")
    return True


def batch_is_expired(status: str, expires_at: datetime, now: datetime) -> bool:
    """Only unfinished receiving batches expire at their server-set deadline."""

    return status == "receiving" and expires_at <= now
