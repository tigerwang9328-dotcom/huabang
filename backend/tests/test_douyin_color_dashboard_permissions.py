"""Read-only collector status remains server-authorized for Douyin viewers."""

from pathlib import Path


def _source(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / name).read_text(encoding="utf-8")


def test_read_only_dashboard_endpoints_allow_viewer_without_granting_token_rotation():
    analytics = _source("douyin_color_analytics.py")
    annotation = _source("douyin_color_annotation_routes.py")

    health_section = analytics[analytics.index("def get_health") : analytics.index("def rotate_upload_tokens")]
    context_section = annotation[annotation.index("def annotation_context") :]
    rotate_section = analytics[analytics.index("def rotate_upload_tokens") :]

    assert '"douyin.viewer"' in health_section
    assert '"douyin.viewer"' in context_section
    assert 'require_permission("douyin.admin")' in rotate_section
