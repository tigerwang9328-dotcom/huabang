"""Schemas for the life-data collector ingest API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


LifeDataEndpoint = Literal[
    "/api/dito/query",
    "/api/lowcode_api/query",
]

_NORMALIZED_SENSITIVE_KEYS = {
    "cookie",
    "set-cookie",
    "authorization",
    "x-tt-ls-session-id",
}
# Snake-case account IDs are valid business fields, so only header spellings are blocked.
_HYPHENATED_ACCOUNT_HEADER_KEYS = {
    "root-life-account-id",
    "life-account-id",
}
_VIDEO_PAGE_PATH = "/flow/content/analysis/video"


def _contains_sensitive_session_key(value: Any) -> bool:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, nested_value in current.items():
                lowered_key = str(key).casefold()
                normalized_key = lowered_key.replace("_", "-")
                if (
                    normalized_key in _NORMALIZED_SENSITIVE_KEYS
                    or lowered_key in _HYPHENATED_ACCOUNT_HEADER_KEYS
                ):
                    return True
                pending.append(nested_value)
        elif isinstance(current, list):
            pending.extend(current)
    return False


def _has_valid_item_rank_row(value: Any) -> bool:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if (
                    str(key).casefold() == "itemrank"
                    and isinstance(child, dict)
                    and isinstance(child.get("data"), list)
                    and any(
                        isinstance(row, dict)
                        and row.get("item_id") not in (None, "")
                        and row.get("item_play_cnt") not in (None, "")
                        for row in child["data"]
                    )
                ):
                    return True
                pending.append(child)
        elif isinstance(current, list):
            pending.extend(current)
    return False


class LifeDataIngestRequest(BaseModel):
    """One captured business response from the life-data collector."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    event_id: str = Field(min_length=16, max_length=64)
    account_id: str = Field(min_length=1, max_length=32)
    page_path: str = Field(min_length=1, max_length=256)
    endpoint: LifeDataEndpoint
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    captured_at: datetime
    queue_depth: int = Field(default=0, ge=0, le=500)

    @field_validator("request_payload", "response_payload")
    @classmethod
    def reject_sensitive_session_fields(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if _contains_sensitive_session_key(value):
            raise ValueError("业务 JSON 不得包含会话或鉴权字段")
        return value

    @model_validator(mode="after")
    def validate_business_response(self) -> "LifeDataIngestRequest":
        response_code = self.response_payload.get("code")
        if type(response_code) is not int or response_code != 0:
            raise ValueError("LifeData 响应 code 必须为 0")
        if (
            self.page_path.rstrip("/") == _VIDEO_PAGE_PATH
            and not _has_valid_item_rank_row(self.response_payload)
        ):
            raise ValueError("视频页响应必须包含有效 itemRank 数据")
        return self


class LifeDataIngestResponse(BaseModel):
    """Stable counters returned after ingesting one event."""

    duplicate: bool
    videos_seen: int = Field(ge=0)
    snapshots_created: int = Field(ge=0)
    tasks_created: int = Field(ge=0)


class LifeDataCollectorGroupHealth(BaseModel):
    """Health of one bounded LifeData API group."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "error", "missing"]
    template_count: int = Field(default=0, ge=0, le=80)
    last_success_at: datetime | None = None
    last_error: str | None = Field(default=None, max_length=500)


class LifeDataCollectorStatusRequest(BaseModel):
    """One server-timestamped collector heartbeat or error report."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    account_id: str = Field(min_length=1, max_length=32)
    status: Literal["online", "error"]
    queue_depth: int = Field(default=0, ge=0, le=500)
    last_error: str | None = Field(default=None, max_length=500)
    template_count: int = Field(default=0, ge=0, le=80)
    last_full_success_at: datetime | None = None
    groups: dict[str, LifeDataCollectorGroupHealth] = Field(default_factory=dict)

    @field_validator("groups")
    @classmethod
    def allow_known_groups_only(
        cls,
        value: dict[str, LifeDataCollectorGroupHealth],
    ) -> dict[str, LifeDataCollectorGroupHealth]:
        unknown = set(value) - {"video", "business", "advertising", "other"}
        if unknown:
            raise ValueError("包含未知采集分组")
        return value

    @model_validator(mode="after")
    def require_error_message(self) -> "LifeDataCollectorStatusRequest":
        if self.status == "error" and not (self.last_error or "").strip():
            raise ValueError("error 状态必须包含 last_error")
        return self


class LifeDataCollectorStatusResponse(BaseModel):
    """Acknowledgement returned without echoing collector details."""

    accepted: Literal[True] = True
