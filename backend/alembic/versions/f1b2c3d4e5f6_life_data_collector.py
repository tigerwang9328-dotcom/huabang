"""add life data collector tables

Revision ID: f1b2c3d4e5f6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-12
"""

from alembic import op


revision = "f1b2c3d4e5f6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app.life_data_capture (
            id bigserial PRIMARY KEY,
            event_id varchar(64) NOT NULL,
            account_id varchar(32) NOT NULL,
            page_path varchar(256) NOT NULL,
            endpoint varchar(256) NOT NULL,
            request_payload jsonb NOT NULL,
            response_payload jsonb NOT NULL,
            response_hash varchar(64) NOT NULL,
            captured_at timestamptz NOT NULL,
            created_at timestamptz DEFAULT now(),
            CONSTRAINT uq_life_data_capture_event_id UNIQUE (event_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_app_life_data_capture_account_id
        ON app.life_data_capture (account_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_app_life_data_capture_created_at
        ON app.life_data_capture (created_at)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app.life_data_video_snapshot (
            id bigserial PRIMARY KEY,
            account_id varchar(32) NOT NULL,
            item_id varchar(96) NOT NULL,
            title text NOT NULL,
            author_id varchar(64),
            author_name varchar(128),
            published_at timestamptz,
            stat_start date NOT NULL,
            stat_end date NOT NULL,
            play_count bigint NOT NULL DEFAULT 0,
            pay_gmv_fen bigint NOT NULL DEFAULT 0,
            verify_gmv_fen bigint NOT NULL DEFAULT 0,
            refund_gmv_fen bigint NOT NULL DEFAULT 0,
            metrics_hash varchar(64) NOT NULL,
            metrics jsonb NOT NULL,
            captured_at timestamptz NOT NULL,
            CONSTRAINT uq_life_data_video_snapshot_metrics
                UNIQUE (account_id, item_id, metrics_hash)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_app_life_data_video_snapshot_account_id
        ON app.life_data_video_snapshot (account_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_app_life_data_video_snapshot_item_id
        ON app.life_data_video_snapshot (item_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app.life_data_alert_event (
            id bigserial PRIMARY KEY,
            account_id varchar(32) NOT NULL,
            item_id varchar(96) NOT NULL,
            rule_code varchar(64) NOT NULL,
            snapshot_id bigint,
            task_id bigint,
            play_count bigint NOT NULL,
            triggered_at timestamptz NOT NULL,
            created_at timestamptz DEFAULT now(),
            CONSTRAINT uq_life_data_alert_event_rule
                UNIQUE (account_id, item_id, rule_code)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app.life_data_collector_state (
            id bigserial PRIMARY KEY,
            account_id varchar(32) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'offline',
            last_seen_at timestamptz,
            last_success_at timestamptz,
            last_error_at timestamptz,
            last_error text,
            last_event_id varchar(64),
            queue_depth integer NOT NULL DEFAULT 0,
            updated_at timestamptz DEFAULT now(),
            CONSTRAINT uq_life_data_collector_state_account_id
                UNIQUE (account_id)
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS app.life_data_collector_state")
    op.execute("DROP TABLE IF EXISTS app.life_data_alert_event")
    op.execute("DROP TABLE IF EXISTS app.life_data_video_snapshot")
    op.execute("DROP TABLE IF EXISTS app.life_data_capture")
