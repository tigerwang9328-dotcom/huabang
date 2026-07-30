"""Regression contract for the production-to-Douyin Alembic merge path."""

from __future__ import annotations

import ast
from pathlib import Path


VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _revision_metadata(filename: str) -> dict[str, object]:
    tree = ast.parse((VERSIONS / filename).read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign):
            target, value = statement.target, statement.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
            values[target.id] = ast.literal_eval(value)
    return values


def test_production_finance_tip_and_douyin_head_have_explicit_merge_revision():
    """Do not stamp a production-structure acceptance database backwards."""
    assert _revision_metadata("016cfd3c1454_add_opening_balance_workflow_controls.py") == {
        "revision": "016cfd3c1454",
        "down_revision": "1fdf4577d7d8",
    }
    assert _revision_metadata("c82e5a1f9d70_add_finance_v2_reports_and_archive_metadata.py") == {
        "revision": "c82e5a1f9d70",
        "down_revision": "016cfd3c1454",
    }
    assert _revision_metadata("e951b2d0a6c4_add_finance_v2_source_inbox_and_posting_rules.py") == {
        "revision": "e951b2d0a6c4",
        "down_revision": "c82e5a1f9d70",
    }
    assert _revision_metadata("3a2d7e951b2c_merge_finance_tip_and_douyin.py") == {
        "revision": "3a2d7e951b2c",
        "down_revision": ("e951b2d0a6c4", "2d7c4a9e8b10"),
    }


def test_task2_runner_requires_the_recorded_production_revision_before_upgrade():
    runner = (Path(__file__).resolve().parents[1] / "scripts" / "run_douyin_color_task2_postgres_acceptance.sh").read_text()
    deploy_runner = (Path(__file__).resolve().parents[2] / "deploy" / "run_douyin_color_migrations.sh").read_text()
    assert 'expected_post_migration_revision="3a2d7e951b2c"' in runner
    assert "post_migration_revision=" in runner
    assert "refusing unexpected post-migration Alembic revision" in runner
    assert "HUABANG_DOUYIN_PYTHON_BIN" in deploy_runner
    assert "HUABANG_DOUYIN_CONFIRM_PRODUCTION" in deploy_runner
    assert 'expected_pre_migration_revision="e951b2d0a6c4"' in deploy_runner
