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
