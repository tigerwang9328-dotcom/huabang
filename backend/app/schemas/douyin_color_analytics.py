"""Wire contracts for the frozen v3.1 Douyin color analysis module."""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


_MACHINE_IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_MACHINE_LABEL = r"^[a-z][a-z0-9_]{0,63}$"


class FocusStatus(str, Enum):
    clear_primary = "clear_primary"
    multi_focus = "multi_focus"
    unclear = "unclear"


class AnnotationStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    deleted = "deleted"


class CollectionBatchStatus(str, Enum):
    receiving = "receiving"
    completed = "completed"
    completed_with_errors = "completed_with_errors"
    expired = "expired"
    abandoned = "abandoned"
    failed = "failed"


class CollectionItemStatus(str, Enum):
    pending = "pending"
    success = "success"
    skipped_non_video = "skipped_non_video"
    empty_curve = "empty_curve"
    auth_failed = "auth_failed"
    rate_limited = "rate_limited"
    network_failed = "network_failed"
    http_failed = "http_failed"
    business_failed = "business_failed"
    upload_failed = "upload_failed"


class ObservationWindow(str, Enum):
    t2 = "t2"
    t7 = "t7"
    t30 = "t30"
    ad_hoc = "ad_hoc"


class PositionSegment(str, Enum):
    all = "all"
    front = "front"
    middle = "middle"
    rear = "rear"


class CollectorStatus(str, Enum):
    online_active = "online_active"
    online_hidden = "online_hidden"
    suspended = "suspended"
    auth_required = "auth_required"
    upload_blocked = "upload_blocked"
    offline_expected = "offline_expected"
    offline_unexpected = "offline_unexpected"


class MetricSemanticsStatus(str, Enum):
    unverified = "unverified"
    verified_lower_is_better = "verified_lower_is_better"
    verified_higher_is_better = "verified_higher_is_better"
    rejected = "rejected"


class CalculationStatus(str, Enum):
    pending = "pending"
    computed = "computed"
    insufficient_data = "insufficient_data"
    stale = "stale"
    failed = "failed"


class ReportStatus(str, Enum):
    generating = "generating"
    ready = "ready"
    stale = "stale"
    failed = "failed"


class BatchPartEnvelope(BaseModel):
    """Client envelope. Account ownership is derived exclusively from the token."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    client_batch_id: str = Field(min_length=1, max_length=64)
    script_version: str = Field(min_length=1, max_length=64)
    source_date_start: date | None = None
    source_date_end: date | None = None
    created_at: datetime
    installation_id: str = Field(min_length=1, max_length=64, pattern=_MACHINE_IDENTIFIER)
    observed_creator_id: str = Field(min_length=1, max_length=128)
    observed_account_name: str | None = Field(default=None, max_length=128)
    part_number: int = Field(ge=1)
    part_count: int = Field(ge=1)
    part_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: list[dict[str, Any]] = Field(max_length=50)


class CollectorHeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    installation_id: str = Field(min_length=1, max_length=64, pattern=_MACHINE_IDENTIFIER)
    script_version: str = Field(min_length=1, max_length=64)
    schema_version: int = Field(ge=1)
    observed_creator_id: str | None = Field(default=None, max_length=128)
    observed_account_name: str | None = Field(default=None, max_length=128)
    current_page_path: str | None = Field(default=None, max_length=512)
    current_page_type: str | None = Field(default=None, max_length=64, pattern=_MACHINE_LABEL)
    document_visibility: str | None = Field(default=None, pattern="^(visible|hidden|prerender)$")
    queued_batch_count: int = Field(ge=0)
    queued_bytes: int = Field(ge=0)
    drift_ms: int | None = None


class CollectorEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    installation_id: str = Field(min_length=1, max_length=64, pattern=_MACHINE_IDENTIFIER)
    event_type: str = Field(min_length=1, max_length=64, pattern=_MACHINE_LABEL)
    occurred_at: datetime
    error_category: str | None = Field(default=None, max_length=64, pattern=_MACHINE_LABEL)
    endpoint_name: str | None = Field(default=None, max_length=64, pattern=_MACHINE_LABEL)
    http_status: int | None = Field(default=None, ge=100, le=599)
    business_status_code: int | None = None
    retry_count: int | None = Field(default=None, ge=0, le=5)
    message: str | None = Field(default=None, max_length=500)
class GarmentStyleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int = Field(gt=0)
    style_code: str = Field(min_length=1, max_length=64)
    style_name: str = Field(min_length=1, max_length=255)
    main_image: str | None = Field(default=None, max_length=512)
    status: str = Field(default="active", pattern="^(active|inactive)$")


class GarmentStyleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style_code: str | None = Field(default=None, min_length=1, max_length=64)
    style_name: str | None = Field(default=None, min_length=1, max_length=255)
    main_image: str | None = Field(default=None, max_length=512)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class GarmentColorCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int = Field(gt=0)
    color_code: str = Field(min_length=1, max_length=64)
    color_name: str = Field(min_length=1, max_length=128)
    color_image: str | None = Field(default=None, max_length=512)
    status: str = Field(default="active", pattern="^(active|inactive)$")


class GarmentColorUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color_code: str | None = Field(default=None, min_length=1, max_length=64)
    color_name: str | None = Field(default=None, min_length=1, max_length=128)
    color_image: str | None = Field(default=None, max_length=512)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class GarmentSkuCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int = Field(gt=0)
    color_id: int = Field(gt=0)
    sku_code: str = Field(min_length=1, max_length=128)
    size_name: str | None = Field(default=None, max_length=64)
    status: str = Field(default="active", pattern="^(active|inactive)$")


class GarmentSkuUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color_id: int | None = Field(default=None, gt=0)
    sku_code: str | None = Field(default=None, min_length=1, max_length=128)
    size_name: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class VideoClipCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int = Field(gt=0)
    video_id: int = Field(gt=0)
    input_start_ms: int = Field(ge=0)
    input_end_ms: int = Field(gt=0)
    curve_resolution_ms: int = Field(gt=0)
    focus_status: FocusStatus
    style_id: int | None = Field(default=None, gt=0)
    color_id: int | None = Field(default=None, gt=0)
    focus_note: str | None = Field(default=None, max_length=1000)
    overlap_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_single_primary_garment(self):
        if self.input_end_ms <= self.input_start_ms:
            raise ValueError("clip_bounds_invalid")
        if self.focus_status is FocusStatus.clear_primary:
            if self.style_id is None or self.color_id is None:
                raise ValueError("clear_primary_requires_style_and_color")
        elif self.style_id is not None or self.color_id is not None:
            raise ValueError("non_primary_forbids_style_and_color")
        return self


class VideoClipUpdateRequest(VideoClipCreateRequest):
    expected_version: int = Field(ge=1)


class AnnotationActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
