from sqlalchemy import BigInteger, Date, DateTime, Integer, JSON, String, Text

from app.models.life_data import (
    LifeDataAlertEvent,
    LifeDataCapture,
    LifeDataCollectorState,
    LifeDataVideoSnapshot,
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
            "updated_at": DateTime,
        },
    }

    for model, expected in expected_column_types.items():
        assert set(model.__table__.columns.keys()) == set(expected)
        for column_name, column_type in expected.items():
            assert isinstance(model.__table__.columns[column_name].type, column_type)
