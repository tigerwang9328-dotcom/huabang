"""Create the account-isolated Douyin collection core.

Revision ID: 20260730_01_douyin_color_core
Revises:
"""

from alembic import op


revision = "20260730_01_douyin_color_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE douyin.douyin_creator_accounts (
            id bigserial PRIMARY KEY,
            account_key varchar(64) NOT NULL,
            display_name varchar(128) NOT NULL,
            expected_creator_fingerprint varchar(64) NOT NULL,
            expected_account_name varchar(128),
            status varchar(16) NOT NULL DEFAULT 'preconfigured',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_douyin_creator_account_status CHECK (status IN ('preconfigured','inactive','active','disabled')),
            CONSTRAINT uq_douyin_creator_account_key UNIQUE (account_key),
            CONSTRAINT uq_douyin_creator_account_creator_fingerprint UNIQUE (expected_creator_fingerprint)
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_douyin_creator_one_active_account ON douyin.douyin_creator_accounts(status) WHERE status = 'active'")
    op.execute("""
        CREATE TABLE douyin.douyin_upload_tokens (
            id bigserial PRIMARY KEY,
            account_id bigint NOT NULL REFERENCES douyin.douyin_creator_accounts(id) ON DELETE RESTRICT,
            token_hash varchar(64) NOT NULL UNIQUE,
            token_prefix varchar(16) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'active',
            last_used_at timestamptz, expires_at timestamptz,
            created_by bigint, created_at timestamptz NOT NULL DEFAULT now(),
            revoked_by bigint, revoked_at timestamptz
        )
    """)
    op.execute("""
        CREATE TABLE douyin.collector_instances (
            id bigserial PRIMARY KEY,
            account_id bigint NOT NULL REFERENCES douyin.douyin_creator_accounts(id) ON DELETE RESTRICT,
            installation_id varchar(64) NOT NULL, script_version varchar(64) NOT NULL, schema_version varchar(64) NOT NULL,
            last_heartbeat_at timestamptz, last_success_at timestamptz, current_status varchar(32) NOT NULL DEFAULT 'offline_expected',
            current_page_path varchar(512), current_page_type varchar(64), document_visibility varchar(16),
            queued_batch_count integer NOT NULL DEFAULT 0, queued_bytes bigint NOT NULL DEFAULT 0, last_error_category varchar(64),
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_douyin_collector_instance UNIQUE (account_id, installation_id),
            CONSTRAINT ck_douyin_collector_page_path CHECK (current_page_path IS NULL OR (current_page_path LIKE '/creator-micro/%' AND current_page_path NOT LIKE '%?%' AND current_page_path NOT LIKE '%#%'))
        )
    """)
    op.execute("""
        CREATE TABLE douyin.videos (
            id bigserial PRIMARY KEY,
            account_id bigint NOT NULL REFERENCES douyin.douyin_creator_accounts(id) ON DELETE RESTRICT,
            video_id_string varchar(64) NOT NULL, title text, published_at timestamptz, duration_ms bigint,
            cover_path varchar(512), creator_detail_path varchar(512) NOT NULL, source_type varchar(32) NOT NULL,
            first_collected_at timestamptz, last_collected_at timestamptz, collection_status varchar(32) NOT NULL DEFAULT 'pending',
            CONSTRAINT uq_douyin_video_account_id UNIQUE (account_id, id),
            CONSTRAINT uq_douyin_video_account_external_id UNIQUE (account_id, video_id_string)
        )
    """)
    op.execute("""
        CREATE TABLE douyin.collection_batches (
            id bigserial PRIMARY KEY,
            account_id bigint NOT NULL REFERENCES douyin.douyin_creator_accounts(id) ON DELETE RESTRICT,
            client_batch_id varchar(64) NOT NULL, schema_version varchar(64) NOT NULL, script_version varchar(64) NOT NULL,
            part_count integer NOT NULL, status varchar(32) NOT NULL DEFAULT 'receiving',
            observed_creator_fingerprint varchar(64) NOT NULL, installation_id varchar(64) NOT NULL, batch_hash varchar(64),
            item_count integer NOT NULL DEFAULT 0, success_count integer NOT NULL DEFAULT 0, skipped_count integer NOT NULL DEFAULT 0, failure_count integer NOT NULL DEFAULT 0,
            first_received_at timestamptz NOT NULL DEFAULT now(), last_part_received_at timestamptz, finalized_at timestamptz, expires_at timestamptz NOT NULL,
            CONSTRAINT ck_douyin_collection_batch_status CHECK (status IN ('receiving','completed','completed_with_errors','expired','abandoned','failed')),
            CONSTRAINT ck_douyin_collection_batch_part_count CHECK (part_count > 0),
            CONSTRAINT uq_douyin_collection_batch_account_id UNIQUE (account_id, id),
            CONSTRAINT uq_douyin_collection_batch_client_id UNIQUE (account_id, client_batch_id)
        )
    """)
    op.execute("""
        CREATE TABLE douyin.collection_batch_parts (
            id bigserial PRIMARY KEY,
            account_id bigint NOT NULL, batch_id bigint NOT NULL, part_number integer NOT NULL, part_hash varchar(64) NOT NULL,
            record_count integer NOT NULL, uncompressed_bytes bigint NOT NULL, received_at timestamptz NOT NULL DEFAULT now(), status varchar(16) NOT NULL DEFAULT 'received',
            CONSTRAINT uq_douyin_batch_part_account_id UNIQUE (account_id, id),
            CONSTRAINT uq_douyin_batch_part_number UNIQUE (batch_id, part_number),
            CONSTRAINT uq_douyin_batch_part_hash UNIQUE (batch_id, part_hash),
            CONSTRAINT fk_douyin_batch_part_account_batch FOREIGN KEY (account_id, batch_id) REFERENCES douyin.collection_batches(account_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE douyin.video_analysis_snapshots (
            id bigserial PRIMARY KEY,
            account_id bigint NOT NULL, video_id bigint NOT NULL, analysis_type integer NOT NULL, collected_at timestamptz NOT NULL,
            source_snapshot_hash varchar(64) NOT NULL, raw_response_json json NOT NULL, normalized_curve_json json,
            normalization_version varchar(32), original_value_unit varchar(32), curve_quality_status varchar(32) NOT NULL,
            observation_window varchar(16) NOT NULL, first_seen_batch_id bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_douyin_snapshot_account_id UNIQUE (account_id, id),
            CONSTRAINT uq_douyin_analysis_snapshot_content UNIQUE (account_id, video_id, analysis_type, source_snapshot_hash),
            CONSTRAINT fk_douyin_snapshot_account_video FOREIGN KEY (account_id, video_id) REFERENCES douyin.videos(account_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_douyin_snapshot_account_first_batch FOREIGN KEY (account_id, first_seen_batch_id) REFERENCES douyin.collection_batches(account_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE douyin.collection_items (
            id bigserial PRIMARY KEY,
            account_id bigint NOT NULL, batch_id bigint NOT NULL, part_id bigint NOT NULL, video_id_string varchar(64), analysis_type integer,
            item_status varchar(32) NOT NULL, error_category varchar(64), endpoint_name varchar(64), http_status integer, business_status_code integer,
            sanitized_error_message varchar(500), retry_count integer NOT NULL DEFAULT 0, raw_record_hash varchar(64), snapshot_id bigint,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_douyin_collection_item_status CHECK (item_status IN ('pending','success','skipped_non_video','empty_curve','auth_failed','rate_limited','network_failed','http_failed','business_failed','upload_failed')),
            CONSTRAINT uq_douyin_collection_item_raw_record UNIQUE (part_id, raw_record_hash),
            CONSTRAINT fk_douyin_item_account_batch FOREIGN KEY (account_id, batch_id) REFERENCES douyin.collection_batches(account_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_douyin_item_account_part FOREIGN KEY (account_id, part_id) REFERENCES douyin.collection_batch_parts(account_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_douyin_item_account_snapshot FOREIGN KEY (account_id, snapshot_id) REFERENCES douyin.video_analysis_snapshots(account_id, id) ON DELETE RESTRICT
        )
    """)


def downgrade():
    for table in (
        "collection_items", "video_analysis_snapshots", "collection_batch_parts", "collection_batches",
        "videos", "collector_instances", "douyin_upload_tokens", "douyin_creator_accounts",
    ):
        op.execute(f"DROP TABLE IF EXISTS douyin.{table}")
