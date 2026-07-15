from pathlib import Path
from runpy import run_path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import BigInteger, Date, DateTime, Integer, JSON, String, Text

from app.models.life_data import (
    LifeDataAlertEvent,
    LifeDataCapture,
    LifeDataCollectorState,
    LifeDataVideoSnapshot,
)


_ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"
_LIFE_DATA_MIGRATION = (
    _ALEMBIC_DIR / "versions" / "f1b2c3d4e5f6_life_data_collector.py"
)
_GROUP_HEALTH_MIGRATION = (
    _ALEMBIC_DIR / "versions" / "a2b3c4d5e6f7_life_data_group_health.py"
)


def _unique_column_sets(model):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


def test_life_data_tables_and_uniques():
    assert LifeDataCapture.__table__.fullname == "app.life_data_capture"
    assert LifeDataVideoSnapshot.__table__.fullname == "app.life_data_video_snapshot"
    assert LifeDataAlertEvent.__table__.fullname == "app.life_data_alert_event"
    assert LifeDataCollectorState.__table__.fullname == "app.life_data_collector_state"

    assert ("event_id",) in _unique_column_sets(LifeDataCapture)
    assert (
        "account_id",
        "item_id",
        "metrics_hash",
    ) in _unique_column_sets(LifeDataVideoSnapshot)
    assert (
        "account_id",
        "item_id",
        "rule_code",
    ) in _unique_column_sets(LifeDataAlertEvent)
    assert ("account_id",) in _unique_column_sets(LifeDataCollectorState)


def test_life_data_models_define_required_columns():
    expected_column_types = {
        LifeDataCapture: {
            "id": BigInteger,
            "event_id": String,
            "account_id": String,
            "page_path": String,
            "endpoint": String,
            "request_payload": JSON,
            "response_payload": JSON,
            "response_hash": String,
            "captured_at": DateTime,
            "created_at": DateTime,
        },
        LifeDataVideoSnapshot: {
            "id": BigInteger,
            "account_id": String,
            "item_id": String,
            "title": Text,
            "author_id": String,
            "author_name": String,
            "published_at": DateTime,
            "stat_start": Date,
            "stat_end": Date,
            "play_count": BigInteger,
            "pay_gmv_fen": BigInteger,
            "verify_gmv_fen": BigInteger,
            "refund_gmv_fen": BigInteger,
            "metrics_hash": String,
            "metrics": JSON,
            "captured_at": DateTime,
        },
        LifeDataAlertEvent: {
            "id": BigInteger,
            "account_id": String,
            "item_id": String,
            "rule_code": String,
            "snapshot_id": BigInteger,
            "task_id": BigInteger,
            "play_count": BigInteger,
            "triggered_at": DateTime,
            "created_at": DateTime,
        },
        LifeDataCollectorState: {
            "id": BigInteger,
            "account_id": String,
            "status": String,
            "last_seen_at": DateTime,
            "last_success_at": DateTime,
            "last_error_at": DateTime,
            "last_error": Text,
            "last_event_id": String,
            "queue_depth": Integer,
            "template_count": Integer,
            "last_full_success_at": DateTime,
            "group_health": JSON,
            "updated_at": DateTime,
        },
    }

    for model, expected in expected_column_types.items():
        assert set(model.__table__.columns.keys()) == set(expected)
        for column_name, column_type in expected.items():
            assert isinstance(model.__table__.columns[column_name].type, column_type)


def test_life_data_migration_revision_chain():
    migration = run_path(str(_LIFE_DATA_MIGRATION))

    assert migration["revision"] == "f1b2c3d4e5f6"
    assert migration["down_revision"] == "a1b2c3d4e5f6"


def test_life_data_migration_has_one_resolvable_head():
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["266f6a7b8c9f"]
    assert script.get_current_head() == "266f6a7b8c9f"


def test_group_health_migration_follows_life_data_collector():
    migration = run_path(str(_GROUP_HEALTH_MIGRATION))

    assert migration["revision"] == "a2b3c4d5e6f7"
    assert migration["down_revision"] == "e5f6a7b8c9d0"
