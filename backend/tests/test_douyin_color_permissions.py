"""Tests for the 6 Douyin color analytics permission roles (Task 12).

Validates the role-to-permission-code mapping completeness so that
downstream ``require_permission`` calls are backed by a known registry.
"""

import pytest


EXPECTED_ROLE_CODES = frozenset({
    "douyin.admin",
    "douyin.auditor",
    "douyin.operator",
    "douyin.annotator",
    "douyin.analyst",
    "douyin.viewer",
})


def test_registry_exposes_all_six_role_codes():
    from app.api.v1.douyin_color_analytics import DOUYIN_ROLE_PERMISSIONS

    assert set(DOUYIN_ROLE_PERMISSIONS) == EXPECTED_ROLE_CODES


def test_permission_code_universe_covers_every_role_and_annotation_codes():
    from app.api.v1.douyin_color_analytics import DOUYIN_PERMISSION_CODES

    # Each role code is itself a permission code.
    for role in EXPECTED_ROLE_CODES:
        assert role in DOUYIN_PERMISSION_CODES
    # Annotation-specific codes used by existing routes are present.
    assert "douyin.annotation.edit" in DOUYIN_PERMISSION_CODES
    assert "douyin.annotation.approve" in DOUYIN_PERMISSION_CODES


def test_admin_role_grants_every_permission_code():
    from app.api.v1.douyin_color_analytics import (
        DOUYIN_PERMISSION_CODES,
        DOUYIN_ROLE_PERMISSIONS,
    )

    assert DOUYIN_ROLE_PERMISSIONS["douyin.admin"] == set(DOUYIN_PERMISSION_CODES)


def test_viewer_role_only_has_view_permission():
    from app.api.v1.douyin_color_analytics import DOUYIN_ROLE_PERMISSIONS

    assert DOUYIN_ROLE_PERMISSIONS["douyin.viewer"] == {"douyin.viewer"}


def test_every_role_includes_viewer_read_permission():
    from app.api.v1.douyin_color_analytics import DOUYIN_ROLE_PERMISSIONS

    for role, perms in DOUYIN_ROLE_PERMISSIONS.items():
        assert "douyin.viewer" in perms, f"role {role} is missing douyin.viewer"


def test_annotator_role_grants_annotation_edit():
    from app.api.v1.douyin_color_analytics import DOUYIN_ROLE_PERMISSIONS

    annotator_perms = DOUYIN_ROLE_PERMISSIONS["douyin.annotator"]
    assert "douyin.annotation.edit" in annotator_perms
    assert "douyin.annotation.approve" not in annotator_perms


def test_admin_grants_annotation_approve_but_annotator_does_not():
    from app.api.v1.douyin_color_analytics import DOUYIN_ROLE_PERMISSIONS

    assert "douyin.annotation.approve" in DOUYIN_ROLE_PERMISSIONS["douyin.admin"]
    assert "douyin.annotation.approve" not in DOUYIN_ROLE_PERMISSIONS["douyin.annotator"]


def test_every_role_permission_set_is_subset_of_universe():
    from app.api.v1.douyin_color_analytics import (
        DOUYIN_PERMISSION_CODES,
        DOUYIN_ROLE_PERMISSIONS,
    )

    universe = set(DOUYIN_PERMISSION_CODES)
    for role, perms in DOUYIN_ROLE_PERMISSIONS.items():
        assert perms <= universe, f"role {role} has permissions outside the universe: {perms - universe}"


def test_operator_role_grants_operator_and_viewer_only():
    from app.api.v1.douyin_color_analytics import DOUYIN_ROLE_PERMISSIONS

    assert DOUYIN_ROLE_PERMISSIONS["douyin.operator"] == {"douyin.operator", "douyin.viewer"}


def test_auditor_role_grants_auditor_and_viewer_only():
    from app.api.v1.douyin_color_analytics import DOUYIN_ROLE_PERMISSIONS

    assert DOUYIN_ROLE_PERMISSIONS["douyin.auditor"] == {"douyin.auditor", "douyin.viewer"}


def test_analyst_role_grants_analyst_and_viewer_only():
    from app.api.v1.douyin_color_analytics import DOUYIN_ROLE_PERMISSIONS

    assert DOUYIN_ROLE_PERMISSIONS["douyin.analyst"] == {"douyin.analyst", "douyin.viewer"}
