import pytest


def test_annotation_rejects_anything_other_than_one_clear_primary_or_no_garment():
    from app.services.douyin_color_annotation_service import (
        AnnotationValidationError,
        validate_primary_assignment,
    )

    validate_primary_assignment("clear_primary", style_id=10, color_id=20)
    validate_primary_assignment("multi_focus", style_id=None, color_id=None)
    validate_primary_assignment("unclear", style_id=None, color_id=None)

    with pytest.raises(AnnotationValidationError, match="clear_primary_requires_style_and_color"):
        validate_primary_assignment("clear_primary", style_id=10, color_id=None)
    with pytest.raises(AnnotationValidationError, match="non_primary_forbids_style_and_color"):
        validate_primary_assignment("multi_focus", style_id=10, color_id=20)
    with pytest.raises(AnnotationValidationError, match="focus_status_invalid"):
        validate_primary_assignment("outfit", style_id=None, color_id=None)


def test_annotation_snap_rounds_to_curve_resolution_and_rejects_over_duration():
    from app.services.douyin_color_annotation_service import AnnotationValidationError, snap_clip_bounds

    assert snap_clip_bounds(
        input_start_ms=1201,
        input_end_ms=2899,
        curve_resolution_ms=1000,
        video_duration_ms=5000,
    ) == (1000, 3000)

    with pytest.raises(AnnotationValidationError, match="clip_exceeds_video_duration"):
        snap_clip_bounds(
            input_start_ms=4200,
            input_end_ms=5001,
            curve_resolution_ms=1000,
            video_duration_ms=5000,
        )


def test_annotation_version_and_workflow_are_conservative():
    from app.services.douyin_color_annotation_service import (
        AnnotationConflictError,
        AnnotationValidationError,
        assert_expected_version,
        validate_annotation_transition,
    )

    assert_expected_version(current_version=3, expected_version=3)
    with pytest.raises(AnnotationConflictError, match="annotation_version_conflict"):
        assert_expected_version(current_version=3, expected_version=2)

    validate_annotation_transition("draft", "submitted")
    validate_annotation_transition("submitted", "approved")
    validate_annotation_transition("submitted", "rejected")
    validate_annotation_transition("rejected", "draft")
    validate_annotation_transition("deleted", "draft")
    with pytest.raises(AnnotationValidationError, match="annotation_transition_invalid"):
        validate_annotation_transition("approved", "submitted")


def test_only_approved_clear_primary_with_resolved_overlap_is_color_ranking_eligible():
    from app.services.douyin_color_annotation_service import is_color_ranking_eligible

    assert is_color_ranking_eligible(
        focus_status="clear_primary", annotation_status="approved", overlap_status="not_required"
    )
    assert is_color_ranking_eligible(
        focus_status="clear_primary", annotation_status="approved", overlap_status="approved"
    )
    assert not is_color_ranking_eligible(
        focus_status="multi_focus", annotation_status="approved", overlap_status="not_required"
    )
    assert not is_color_ranking_eligible(
        focus_status="unclear", annotation_status="approved", overlap_status="not_required"
    )
    assert not is_color_ranking_eligible(
        focus_status="clear_primary", annotation_status="submitted", overlap_status="not_required"
    )


def test_cross_color_temporal_overlap_requires_reviewer_approval_but_same_color_does_not():
    from app.services.douyin_color_annotation_service import overlap_requirement

    assert overlap_requirement(
        start_ms=1000, end_ms=3000, color_id=11,
        other_start_ms=2000, other_end_ms=4000, other_color_id=12,
    ) == "pending_approval"
    assert overlap_requirement(
        start_ms=1000, end_ms=3000, color_id=11,
        other_start_ms=2000, other_end_ms=4000, other_color_id=11,
    ) == "not_required"
    assert overlap_requirement(
        start_ms=1000, end_ms=2000, color_id=11,
        other_start_ms=2000, other_end_ms=4000, other_color_id=12,
    ) == "not_required"


def test_annotation_routes_have_account_scoped_crud_workflow_and_permission_boundaries():
    from app.api.v1.douyin_color_analytics import router

    routes = {(route.path, frozenset(route.methods or [])) for route in router.routes}
    expected_paths = {
        "/douyin-color-analytics/styles",
        "/douyin-color-analytics/styles/{style_id}",
        "/douyin-color-analytics/styles/{style_id}/colors",
        "/douyin-color-analytics/skus",
        "/douyin-color-analytics/video-clips",
        "/douyin-color-analytics/video-clips/{clip_id}",
        "/douyin-color-analytics/video-clips/{clip_id}/submit",
        "/douyin-color-analytics/video-clips/{clip_id}/approve",
        "/douyin-color-analytics/video-clips/{clip_id}/reject",
        "/douyin-color-analytics/video-clips/{clip_id}/restore",
    }
    assert expected_paths <= {path for path, _ in routes}
    assert ("/douyin-color-analytics/video-clips", frozenset({"POST"})) in routes
    assert ("/douyin-color-analytics/video-clips/{clip_id}", frozenset({"PATCH"})) in routes
    assert ("/douyin-color-analytics/video-clips/{clip_id}", frozenset({"DELETE"})) in routes


def test_annotation_request_schema_accepts_a_whole_outfit_and_rejects_invalid_parts():
    from pydantic import ValidationError

    from app.schemas.douyin_color_analytics import VideoClipCreateRequest

    accepted = VideoClipCreateRequest(
        account_id=1,
        video_id=2,
        input_start_ms=0,
        input_end_ms=1100,
        curve_resolution_ms=1000,
        focus_status="clear_primary",
        outfit_parts_json=[
            {"position": "top", "style_id": 3, "sku_code": "TOP-RED-M"},
            {"position": "bottom", "style_id": 5, "sku_code": "PANTS-BLACK-L"},
        ],
    )
    assert accepted.focus_status.value == "clear_primary"
    assert len(accepted.outfit_parts_json) == 2
    with pytest.raises(ValidationError):
        VideoClipCreateRequest(
            account_id=1,
            video_id=2,
            input_start_ms=0,
            input_end_ms=1100,
            curve_resolution_ms=1000,
            focus_status="multi_focus",
            outfit_parts_json=[{"position": "top", "style_id": 3}],
        )
    with pytest.raises(ValidationError):
        VideoClipCreateRequest(
            account_id=1,
            video_id=2,
            input_start_ms=0,
            input_end_ms=1100,
            curve_resolution_ms=1000,
            focus_status="clear_primary",
            outfit_parts_json=[{"position": "top", "style_id": 3}],
        )


def test_annotation_clip_response_and_routes_preserve_whole_outfit_and_real_product_archive_contract():
    from pathlib import Path

    route_source = (Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "douyin_color_annotation_routes.py").read_text(encoding="utf-8")

    assert '"outfit_parts_json": clip.outfit_parts_json' in route_source
    assert 'payload.outfit_parts_json' in route_source
    assert 'product-archive/styles' in route_source
    assert 'dim.dim_sku' in route_source
    assert 'dwd.v_apparel_inventory_balance' in route_source
def test_annotation_mutations_lock_clip_versions_and_return_explicit_product_conflicts():
    from pathlib import Path

    route_source = (Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "douyin_color_annotation_routes.py").read_text(encoding="utf-8")

    assert "with_for_update()" in route_source
    assert "style_code_conflict" in route_source
    assert "color_code_conflict" in route_source
    assert "sku_code_conflict" in route_source

@pytest.mark.asyncio
async def test_annotation_account_is_derived_from_the_single_active_account_and_rejects_client_hint_mismatch():
    from fastapi import HTTPException

    from app.api.v1.douyin_color_annotation_routes import _annotation_account

    class ScalarResult:
        def __init__(self, accounts):
            self._accounts = accounts

        def all(self):
            return self._accounts

    class Result:
        def __init__(self, accounts):
            self._accounts = accounts

        def scalars(self):
            return ScalarResult(self._accounts)

    class Db:
        async def execute(self, _query):
            return Result([type("Account", (), {"id": 7})()])

    assert (await _annotation_account(Db(), account_hint=7)).id == 7
    with pytest.raises(HTTPException) as error:
        await _annotation_account(Db(), account_hint=8)
    assert error.value.status_code == 403
    assert error.value.detail == "account_scope_mismatch"


def test_annotation_clip_validation_locks_the_parent_video_before_overlap_query():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "douyin_color_annotation_routes.py").read_text(encoding="utf-8")

    assert "select(Video).where(Video.account_id == account_id, Video.id == payload.video_id).with_for_update()" in source
    assert "_scoped_record(db, DouyinCreatorAccount" not in source

@pytest.mark.asyncio
async def test_snapshot_account_scope_is_derived_from_the_only_active_account():
    from app.services.douyin_color_annotation_service import (
        AnnotationPermissionError,
        resolve_single_active_account,
    )

    class ScalarResult:
        def all(self):
            return [type("Account", (), {"id": 11})()]

    class Result:
        def scalars(self):
            return ScalarResult()

    class Db:
        async def execute(self, _query):
            return Result()

    assert (await resolve_single_active_account(Db(), account_hint=11)).id == 11
    with pytest.raises(AnnotationPermissionError, match="account_scope_mismatch"):
        await resolve_single_active_account(Db(), account_hint=12)
