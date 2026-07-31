"""Business rules for v3.1's one-primary-garment clip annotations."""

from __future__ import annotations


from sqlalchemy import select

from app.models.douyin_color_analytics import DouyinCreatorAccount


_FOCUS_STATUSES = {"clear_primary", "multi_focus", "unclear"}
_WORKFLOW_TRANSITIONS = {
    "draft": {"submitted", "deleted"},
    "submitted": {"approved", "rejected", "deleted"},
    "rejected": {"draft", "deleted"},
    "approved": {"deleted"},
    "deleted": {"draft"},
}


class AnnotationValidationError(ValueError):
    """A request violates the frozen annotation contract."""


class AnnotationConflictError(AnnotationValidationError):
    """A request is well-formed but conflicts with the current version/state."""


def validate_primary_assignment(focus_status: str, *, style_id: int | None, color_id: int | None) -> None:
    """Permit exactly one primary garment, or explicitly no garment assignment."""

    if focus_status not in _FOCUS_STATUSES:
        raise AnnotationValidationError("focus_status_invalid")
    if focus_status == "clear_primary":
        if style_id is None or color_id is None:
            raise AnnotationValidationError("clear_primary_requires_style_and_color")
        return
    if style_id is not None or color_id is not None:
        raise AnnotationValidationError("non_primary_forbids_style_and_color")


def snap_clip_bounds(
    *, input_start_ms: int, input_end_ms: int, curve_resolution_ms: int, video_duration_ms: int | None
) -> tuple[int, int]:
    """Snap outward to curve samples, preserving the operator's selected interval."""

    if video_duration_ms is None or video_duration_ms <= 0:
        raise AnnotationValidationError("video_duration_required")
    if input_start_ms < 0 or input_end_ms <= input_start_ms or curve_resolution_ms <= 0:
        raise AnnotationValidationError("clip_bounds_invalid")
    start_ms = (input_start_ms // curve_resolution_ms) * curve_resolution_ms
    end_ms = ((input_end_ms + curve_resolution_ms - 1) // curve_resolution_ms) * curve_resolution_ms
    if end_ms > video_duration_ms:
        raise AnnotationValidationError("clip_exceeds_video_duration")
    if end_ms <= start_ms:
        raise AnnotationValidationError("clip_bounds_invalid")
    return start_ms, end_ms


def assert_expected_version(*, current_version: int, expected_version: int) -> None:
    if current_version != expected_version:
        raise AnnotationConflictError("annotation_version_conflict")


def validate_annotation_transition(current_status: str, target_status: str) -> None:
    if target_status not in _WORKFLOW_TRANSITIONS.get(current_status, set()):
        raise AnnotationValidationError("annotation_transition_invalid")


def overlap_requirement(
    *,
    start_ms: int,
    end_ms: int,
    color_id: int | None,
    other_start_ms: int,
    other_end_ms: int,
    other_color_id: int | None,
) -> str:
    """Cross-colour temporal overlaps need a reviewer; boundaries that meet do not overlap."""

    if color_id is None or other_color_id is None or color_id == other_color_id:
        return "not_required"
    if start_ms < other_end_ms and other_start_ms < end_ms:
        return "pending_approval"
    return "not_required"


def is_color_ranking_eligible(*, focus_status: str, annotation_status: str, overlap_status: str) -> bool:
    """Keep multi-focus and unclear clips out of all single-colour ranking inputs."""

    return (
        focus_status == "clear_primary"
        and annotation_status == "approved"
        and overlap_status in {"not_required", "approved"}
    )


def assert_account_scope(*, record_account_id: int, requested_account_id: int) -> None:
    """Prevent a caller from reusing an ID belonging to another creator account."""

    if record_account_id != requested_account_id:
        raise AnnotationValidationError("account_scope_mismatch")

class AnnotationPermissionError(AnnotationValidationError):
    """The caller supplied an account hint outside the first-release scope."""


async def resolve_single_active_account(db, *, account_hint: int | None = None) -> DouyinCreatorAccount:
    """Resolve the one active account without letting a request choose another account."""

    accounts = (await db.execute(select(DouyinCreatorAccount).where(
        DouyinCreatorAccount.status == "active",
    ))).scalars().all()
    if len(accounts) != 1:
        raise AnnotationConflictError("active_account_not_configured")
    account = accounts[0]
    if account_hint is not None and account_hint != account.id:
        raise AnnotationPermissionError("account_scope_mismatch")
    return account
