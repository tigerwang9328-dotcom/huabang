"""Create the frozen v3.1 Douyin color analytics schema.

Revision ID: 2d7c4a9e8b10
Revises: 1fdf4577d7d8
"""

from alembic import op


_UPGRADE_DDL = r"""

CREATE TABLE douyin.douyin_creator_accounts (
	id BIGSERIAL NOT NULL,
	account_key VARCHAR(64) NOT NULL,
	display_name VARCHAR(128) NOT NULL,
	expected_creator_fingerprint VARCHAR(64) NOT NULL,
	expected_account_name VARCHAR(128),
	status VARCHAR(16) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_creator_account_status CHECK (status IN ('preconfigured','inactive','active','disabled')),
	CONSTRAINT uq_douyin_creator_account_key UNIQUE (account_key),
	CONSTRAINT uq_douyin_creator_account_creator_fingerprint UNIQUE (expected_creator_fingerprint)
)


;

CREATE TABLE douyin.calculation_jobs (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	job_type VARCHAR(64) NOT NULL,
	target_type VARCHAR(64) NOT NULL,
	target_id VARCHAR(128) NOT NULL,
	deduplication_key VARCHAR(256) NOT NULL,
	requested_by BIGINT,
	status VARCHAR(32) NOT NULL,
	attempt_count INTEGER NOT NULL,
	available_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	lease_owner VARCHAR(128),
	lease_expires_at TIMESTAMP WITH TIME ZONE,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	sanitized_error_message VARCHAR(500),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_calculation_job_status CHECK (status IN ('queued','running','succeeded','retryable_failed','terminal_failed')),
	CONSTRAINT ck_douyin_calculation_job_attempt_count CHECK (attempt_count >= 0),
	CONSTRAINT uq_douyin_calculation_job_deduplication UNIQUE (deduplication_key),
	CONSTRAINT fk_douyin_calculation_job_account FOREIGN KEY(account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE CASCADE
)


;

CREATE TABLE douyin.collection_batches (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	client_batch_id VARCHAR(64) NOT NULL,
	schema_version INTEGER NOT NULL,
	script_version VARCHAR(64) NOT NULL,
	source_date_start DATE,
	source_date_end DATE,
	created_at_client TIMESTAMP WITH TIME ZONE,
	first_received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	last_part_received_at TIMESTAMP WITH TIME ZONE,
	finalized_at TIMESTAMP WITH TIME ZONE,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	part_count INTEGER NOT NULL,
	batch_hash VARCHAR(64),
	status VARCHAR(32) NOT NULL,
	item_count INTEGER NOT NULL,
	success_count INTEGER NOT NULL,
	skipped_count INTEGER NOT NULL,
	failure_count INTEGER NOT NULL,
	observed_creator_fingerprint VARCHAR(64) NOT NULL,
	installation_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_collection_batch_status CHECK (status IN ('receiving','completed','completed_with_errors','expired','abandoned','failed')),
	CONSTRAINT ck_douyin_collection_batch_part_count CHECK (part_count > 0),
	CONSTRAINT ck_douyin_collection_batch_source_dates CHECK (source_date_start IS NULL OR source_date_end IS NULL OR source_date_start <= source_date_end),
	CONSTRAINT ck_douyin_collection_batch_counts CHECK (item_count >= 0 AND success_count >= 0 AND skipped_count >= 0 AND failure_count >= 0),
	CONSTRAINT uq_douyin_collection_batch_account_id UNIQUE (account_id, id),
	CONSTRAINT uq_douyin_collection_batch_client_id UNIQUE (account_id, client_batch_id),
	CONSTRAINT fk_douyin_collection_batch_account FOREIGN KEY(account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.collector_expected_schedules (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	timezone VARCHAR(64) NOT NULL,
	weekday_mask INTEGER NOT NULL,
	expected_start_local TIME WITHOUT TIME ZONE NOT NULL,
	expected_end_local TIME WITHOUT TIME ZONE NOT NULL,
	enabled BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_douyin_expected_schedule UNIQUE (account_id, weekday_mask, expected_start_local),
	CONSTRAINT fk_douyin_expected_schedule_account FOREIGN KEY(account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE CASCADE
)


;

CREATE TABLE douyin.collector_instances (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	installation_id VARCHAR(64) NOT NULL,
	script_version VARCHAR(64) NOT NULL,
	schema_version INTEGER NOT NULL,
	last_heartbeat_at TIMESTAMP WITH TIME ZONE,
	last_success_at TIMESTAMP WITH TIME ZONE,
	current_status VARCHAR(32) NOT NULL,
	current_page_path VARCHAR(512),
	current_page_type VARCHAR(64),
	document_visibility VARCHAR(16),
	observed_creator_fingerprint VARCHAR(64),
	observed_account_name VARCHAR(128),
	queued_batch_count INTEGER NOT NULL,
	queued_bytes BIGINT NOT NULL,
	last_error_category VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_collector_status CHECK (current_status IN ('online_active','online_hidden','suspended','auth_required','upload_blocked','offline_expected','offline_unexpected')),
	CONSTRAINT ck_douyin_collector_page_path CHECK (current_page_path IS NULL OR (current_page_path LIKE '/creator-micro/%%' AND current_page_path NOT LIKE '%%?%%' AND current_page_path NOT LIKE '%%#%%')),
	CONSTRAINT uq_douyin_collector_account_id UNIQUE (account_id, id),
	CONSTRAINT uq_douyin_collector_instance UNIQUE (account_id, installation_id),
	CONSTRAINT fk_douyin_collector_account FOREIGN KEY(account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.douyin_upload_tokens (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	token_prefix VARCHAR(16) NOT NULL,
	status VARCHAR(16) NOT NULL,
	last_used_at TIMESTAMP WITH TIME ZONE,
	expires_at TIMESTAMP WITH TIME ZONE,
	created_by BIGINT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	revoked_by BIGINT,
	revoked_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_upload_token_status CHECK (status IN ('active','revoked','expired')),
	CONSTRAINT uq_douyin_upload_token_hash UNIQUE (token_hash),
	CONSTRAINT fk_douyin_upload_token_account FOREIGN KEY(account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.garment_styles (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	style_code VARCHAR(64) NOT NULL,
	style_name VARCHAR(255) NOT NULL,
	main_image VARCHAR(512),
	status VARCHAR(16) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_douyin_style_account_id UNIQUE (account_id, id),
	CONSTRAINT uq_douyin_style_code UNIQUE (account_id, style_code),
	CONSTRAINT fk_douyin_style_account FOREIGN KEY(account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.metric_semantic_validations (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	metric_key VARCHAR(64) NOT NULL,
	semantics_status VARCHAR(32) NOT NULL,
	evidence_video_ids_json JSON NOT NULL,
	verified_by BIGINT,
	verified_at TIMESTAMP WITH TIME ZONE,
	notes TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_metric_semantics_status CHECK (semantics_status IN ('unverified','verified_lower_is_better','verified_higher_is_better','rejected')),
	CONSTRAINT uq_douyin_metric_semantic UNIQUE (account_id, metric_key),
	CONSTRAINT fk_douyin_metric_semantic_account FOREIGN KEY(account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE CASCADE
)


;

CREATE TABLE douyin.videos (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	video_id_string VARCHAR(64) NOT NULL,
	title TEXT,
	published_at TIMESTAMP WITH TIME ZONE,
	duration_ms BIGINT,
	cover_path VARCHAR(512),
	creator_detail_path VARCHAR(512) NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	first_collected_at TIMESTAMP WITH TIME ZONE,
	last_collected_at TIMESTAMP WITH TIME ZONE,
	collection_status VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_douyin_video_account_id UNIQUE (account_id, id),
	CONSTRAINT uq_douyin_video_account_external_id UNIQUE (account_id, video_id_string),
	CONSTRAINT fk_douyin_video_account FOREIGN KEY(account_id) REFERENCES douyin.douyin_creator_accounts (id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.collection_batch_parts (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	batch_id BIGINT NOT NULL,
	part_number INTEGER NOT NULL,
	part_hash VARCHAR(64) NOT NULL,
	record_count INTEGER NOT NULL,
	uncompressed_bytes BIGINT NOT NULL,
	received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	status VARCHAR(16) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_batch_part_bounds CHECK (part_number >= 1 AND record_count >= 0 AND uncompressed_bytes >= 0),
	CONSTRAINT uq_douyin_batch_part_account_id UNIQUE (account_id, id),
	CONSTRAINT uq_douyin_batch_part_account_batch_id UNIQUE (account_id, batch_id, id),
	CONSTRAINT uq_douyin_batch_part_number UNIQUE (batch_id, part_number),
	CONSTRAINT uq_douyin_batch_part_hash UNIQUE (batch_id, part_hash),
	CONSTRAINT fk_douyin_batch_part_account_batch FOREIGN KEY(account_id, batch_id) REFERENCES douyin.collection_batches (account_id, id) ON DELETE CASCADE
)


;

CREATE TABLE douyin.collector_events (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	collector_instance_id BIGINT,
	installation_id VARCHAR(64) NOT NULL,
	event_type VARCHAR(64) NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
	error_category VARCHAR(64),
	endpoint_name VARCHAR(64),
	http_status INTEGER,
	business_status_code INTEGER,
	retry_count INTEGER,
	sanitized_message VARCHAR(500),
	PRIMARY KEY (id),
	CONSTRAINT fk_douyin_collector_event_instance FOREIGN KEY(account_id, collector_instance_id) REFERENCES douyin.collector_instances (account_id, id) ON DELETE CASCADE
)


;

CREATE TABLE douyin.garment_colors (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	style_id BIGINT NOT NULL,
	color_code VARCHAR(64) NOT NULL,
	color_name VARCHAR(128) NOT NULL,
	color_image VARCHAR(512),
	status VARCHAR(16) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_douyin_color_account_id UNIQUE (account_id, id),
	CONSTRAINT uq_douyin_color_account_style_id UNIQUE (account_id, style_id, id),
	CONSTRAINT uq_douyin_color_style_code UNIQUE (account_id, style_id, color_code),
	CONSTRAINT fk_douyin_color_account_style FOREIGN KEY(account_id, style_id) REFERENCES douyin.garment_styles (account_id, id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.video_analysis_snapshots (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	video_id BIGINT NOT NULL,
	analysis_type INTEGER NOT NULL,
	collected_at TIMESTAMP WITH TIME ZONE NOT NULL,
	source_snapshot_hash VARCHAR(64) NOT NULL,
	raw_response_json JSON NOT NULL,
	normalized_curve_json JSON,
	normalization_version VARCHAR(32),
	original_value_unit VARCHAR(32),
	curve_quality_status VARCHAR(32) NOT NULL,
	similar_author_normalized_curve_json JSON,
	valley_list_json JSON,
	valley_related_items_json JSON,
	video_age_hours_at_collection NUMERIC(12, 3),
	observation_window VARCHAR(16) NOT NULL,
	curve_audience_count BIGINT,
	http_status INTEGER,
	business_status_code INTEGER,
	status_message VARCHAR(500),
	first_seen_batch_id BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_snapshot_analysis_type CHECK (analysis_type IN (1,7)),
	CONSTRAINT ck_douyin_snapshot_observation_window CHECK (observation_window IN ('t2','t7','t30','ad_hoc')),
	CONSTRAINT uq_douyin_snapshot_account_id UNIQUE (account_id, id),
	CONSTRAINT uq_douyin_analysis_snapshot_content UNIQUE (account_id, video_id, analysis_type, source_snapshot_hash),
	CONSTRAINT fk_douyin_snapshot_account_video FOREIGN KEY(account_id, video_id) REFERENCES douyin.videos (account_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_douyin_snapshot_account_first_batch FOREIGN KEY(account_id, first_seen_batch_id) REFERENCES douyin.collection_batches (account_id, id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.video_catalog_snapshots (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	video_id BIGINT NOT NULL,
	collected_at TIMESTAMP WITH TIME ZONE NOT NULL,
	play_count_at_collection BIGINT,
	traffic_source_json JSON,
	raw_item_whitelist_json JSON NOT NULL,
	source_snapshot_hash VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_douyin_catalog_snapshot_content UNIQUE (account_id, video_id, source_snapshot_hash),
	CONSTRAINT fk_douyin_catalog_snapshot_video FOREIGN KEY(account_id, video_id) REFERENCES douyin.videos (account_id, id) ON DELETE CASCADE
)


;

CREATE TABLE douyin.collection_items (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	batch_id BIGINT NOT NULL,
	part_id BIGINT NOT NULL,
	video_id_string VARCHAR(64),
	analysis_type INTEGER,
	item_status VARCHAR(32) NOT NULL,
	error_category VARCHAR(64),
	endpoint_name VARCHAR(64),
	http_status INTEGER,
	business_status_code INTEGER,
	sanitized_error_message VARCHAR(500),
	retry_count INTEGER NOT NULL,
	raw_record_hash VARCHAR(64),
	snapshot_id BIGINT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_collection_item_status CHECK (item_status IN ('pending','success','skipped_non_video','empty_curve','auth_failed','rate_limited','network_failed','http_failed','business_failed','upload_failed')),
	CONSTRAINT uq_douyin_collection_item_raw_record UNIQUE (part_id, raw_record_hash),
	CONSTRAINT fk_douyin_item_account_batch_part FOREIGN KEY(account_id, batch_id, part_id) REFERENCES douyin.collection_batch_parts (account_id, batch_id, id) ON DELETE CASCADE,
	CONSTRAINT fk_douyin_item_account_snapshot FOREIGN KEY(account_id, snapshot_id) REFERENCES douyin.video_analysis_snapshots (account_id, id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.color_performance_snapshots (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	style_id BIGINT NOT NULL,
	color_id BIGINT NOT NULL,
	as_of_date DATE NOT NULL,
	source_data_cutoff_at TIMESTAMP WITH TIME ZONE NOT NULL,
	calculation_date DATE NOT NULL,
	observation_window VARCHAR(16) NOT NULL,
	position_segment VARCHAR(16) NOT NULL,
	metric_version VARCHAR(32) NOT NULL,
	report_revision INTEGER NOT NULL,
	report_input_hash VARCHAR(64) NOT NULL,
	is_current BOOLEAN NOT NULL,
	report_status VARCHAR(32) NOT NULL,
	retention_video_sample_count INTEGER NOT NULL,
	bounce_video_sample_count INTEGER NOT NULL,
	eligible_video_sample_count INTEGER NOT NULL,
	excluded_multi_focus_clip_count INTEGER NOT NULL,
	excluded_unclear_clip_count INTEGER NOT NULL,
	average_retention NUMERIC(12, 8),
	retention_stddev_sample NUMERIC(12, 8),
	average_relative_position NUMERIC(12, 8),
	average_clip_duration_ms NUMERIC(14, 4),
	front_segment_sample_count INTEGER NOT NULL,
	middle_segment_sample_count INTEGER NOT NULL,
	rear_segment_sample_count INTEGER NOT NULL,
	other_colors_equal_weight_retention NUMERIC(12, 8),
	other_colors_video_weighted_retention NUMERIC(12, 8),
	retention_delta_vs_other_colors NUMERIC(12, 8),
	exposure_weighted_retention_reference NUMERIC(12, 8),
	average_platform_bounce_curve_value NUMERIC(12, 8),
	other_colors_equal_weight_bounce NUMERIC(12, 8),
	other_colors_video_weighted_bounce NUMERIC(12, 8),
	bounce_delta_vs_other_colors NUMERIC(12, 8),
	average_rank_eligible BOOLEAN NOT NULL,
	stability_rank_eligible BOOLEAN NOT NULL,
	calculated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_report_observation_window CHECK (observation_window IN ('t2','t7','t30','ad_hoc')),
	CONSTRAINT ck_douyin_report_position_segment CHECK (position_segment IN ('all','front','middle','rear')),
	CONSTRAINT ck_douyin_report_status CHECK (report_status IN ('generating','ready','stale','failed')),
	CONSTRAINT ck_douyin_report_revision CHECK (report_revision >= 1),
	CONSTRAINT ck_douyin_report_counts CHECK (retention_video_sample_count >= 0 AND bounce_video_sample_count >= 0 AND eligible_video_sample_count >= 0 AND excluded_multi_focus_clip_count >= 0 AND excluded_unclear_clip_count >= 0 AND front_segment_sample_count >= 0 AND middle_segment_sample_count >= 0 AND rear_segment_sample_count >= 0),
	CONSTRAINT uq_douyin_report_account_id UNIQUE (account_id, id),
	CONSTRAINT fk_douyin_report_account_style_color FOREIGN KEY(account_id, style_id, color_id) REFERENCES douyin.garment_colors (account_id, style_id, id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.garment_skus (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	color_id BIGINT NOT NULL,
	sku_code VARCHAR(128) NOT NULL,
	size_name VARCHAR(64),
	status VARCHAR(16) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_douyin_sku_code UNIQUE (account_id, sku_code),
	CONSTRAINT fk_douyin_sku_account_color FOREIGN KEY(account_id, color_id) REFERENCES douyin.garment_colors (account_id, id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.video_clips (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	video_id BIGINT NOT NULL,
	style_id BIGINT,
	color_id BIGINT,
	start_ms BIGINT NOT NULL,
	end_ms BIGINT NOT NULL,
	input_start_ms BIGINT NOT NULL,
	input_end_ms BIGINT NOT NULL,
	curve_resolution_ms INTEGER NOT NULL,
	focus_status VARCHAR(32) NOT NULL,
	focus_note TEXT,
	annotation_status VARCHAR(16) NOT NULL,
	overlap_reason TEXT,
	overlap_status VARCHAR(32) NOT NULL,
	overlap_approved_by BIGINT,
	overlap_approved_at TIMESTAMP WITH TIME ZONE,
	submitted_by BIGINT,
	submitted_at TIMESTAMP WITH TIME ZONE,
	approved_by BIGINT,
	approved_at TIMESTAMP WITH TIME ZONE,
	created_by BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_by BIGINT,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_clip_bounds CHECK (start_ms >= 0 AND end_ms > start_ms),
	CONSTRAINT ck_douyin_clip_input_bounds CHECK (input_start_ms >= 0 AND input_end_ms > input_start_ms),
	CONSTRAINT ck_douyin_clip_resolution CHECK (curve_resolution_ms > 0),
	CONSTRAINT ck_douyin_clip_version CHECK (version >= 1),
	CONSTRAINT ck_douyin_clip_focus_assignment CHECK ((focus_status = 'clear_primary' AND style_id IS NOT NULL AND color_id IS NOT NULL) OR (focus_status IN ('multi_focus','unclear') AND style_id IS NULL AND color_id IS NULL)),
	CONSTRAINT ck_douyin_clip_focus_status CHECK (focus_status IN ('clear_primary','multi_focus','unclear')),
	CONSTRAINT ck_douyin_clip_annotation_status CHECK (annotation_status IN ('draft','submitted','approved','rejected','deleted')),
	CONSTRAINT uq_douyin_clip_account_id UNIQUE (account_id, id),
	CONSTRAINT fk_douyin_clip_account_video FOREIGN KEY(account_id, video_id) REFERENCES douyin.videos (account_id, id) ON DELETE CASCADE,
	CONSTRAINT fk_douyin_clip_account_style_color FOREIGN KEY(account_id, style_id, color_id) REFERENCES douyin.garment_colors (account_id, style_id, id) ON DELETE RESTRICT
)


;

CREATE TABLE douyin.video_color_metrics (
	id BIGSERIAL NOT NULL,
	account_id BIGINT NOT NULL,
	video_id BIGINT NOT NULL,
	style_id BIGINT NOT NULL,
	color_id BIGINT NOT NULL,
	observation_window VARCHAR(16) NOT NULL,
	retention_snapshot_id BIGINT NOT NULL,
	bounce_snapshot_id BIGINT,
	retention_source_hash VARCHAR(64) NOT NULL,
	bounce_source_hash VARCHAR(64),
	annotation_set_hash VARCHAR(64) NOT NULL,
	metric_input_hash VARCHAR(64) NOT NULL,
	metric_version VARCHAR(32) NOT NULL,
	average_retention NUMERIC(12, 8),
	retention_drop NUMERIC(12, 8),
	average_platform_bounce_curve_value NUMERIC(12, 8),
	max_platform_bounce_curve_value NUMERIC(12, 8),
	clip_count INTEGER NOT NULL,
	total_clip_duration_ms BIGINT NOT NULL,
	average_relative_position NUMERIC(12, 8),
	earliest_relative_position NUMERIC(12, 8),
	latest_relative_position NUMERIC(12, 8),
	average_clip_duration_ms NUMERIC(14, 4),
	video_duration_ms BIGINT NOT NULL,
	dominant_position_segment VARCHAR(16),
	retention_calculation_status VARCHAR(32) NOT NULL,
	bounce_calculation_status VARCHAR(32) NOT NULL,
	calculated_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_douyin_metric_observation_window CHECK (observation_window IN ('t2','t7','t30','ad_hoc')),
	CONSTRAINT ck_douyin_metric_retention_status CHECK (retention_calculation_status IN ('pending','computed','insufficient_data','stale','failed')),
	CONSTRAINT ck_douyin_metric_bounce_status CHECK (bounce_calculation_status IN ('pending','computed','insufficient_data','stale','failed')),
	CONSTRAINT uq_douyin_video_color_metric UNIQUE (account_id, video_id, style_id, color_id, observation_window, metric_version, metric_input_hash),
	CONSTRAINT fk_douyin_metric_account_video FOREIGN KEY(account_id, video_id) REFERENCES douyin.videos (account_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_douyin_metric_account_style_color FOREIGN KEY(account_id, style_id, color_id) REFERENCES douyin.garment_colors (account_id, style_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_douyin_metric_account_retention_snapshot FOREIGN KEY(account_id, retention_snapshot_id) REFERENCES douyin.video_analysis_snapshots (account_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_douyin_metric_account_bounce_snapshot FOREIGN KEY(account_id, bounce_snapshot_id) REFERENCES douyin.video_analysis_snapshots (account_id, id) ON DELETE RESTRICT
)


;
CREATE UNIQUE INDEX uq_color_report_current ON douyin.color_performance_snapshots (account_id, style_id, color_id, as_of_date, observation_window, position_segment, metric_version) WHERE is_current = TRUE
;
CREATE UNIQUE INDEX uq_color_report_revision ON douyin.color_performance_snapshots (account_id, style_id, color_id, as_of_date, observation_window, position_segment, metric_version, report_revision)
;
CREATE UNIQUE INDEX uq_douyin_creator_one_active_account ON douyin.douyin_creator_accounts (status) WHERE status = 'active'
"""





revision = "2d7c4a9e8b10"
down_revision = "1fdf4577d7d8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL ROLE huabang_douyin_migrator")
    try:

        for statement in _UPGRADE_DDL.split("\n;\n"):
            if statement.strip():
                op.execute(statement)
    finally:
        op.execute("RESET ROLE")


def downgrade():
    op.execute("SET LOCAL ROLE huabang_douyin_migrator")
    try:
        op.execute("DROP TABLE IF EXISTS douyin.color_performance_snapshots" )
        op.execute("DROP TABLE IF EXISTS douyin.calculation_jobs" )
        op.execute("DROP TABLE IF EXISTS douyin.video_color_metrics" )
        op.execute("DROP TABLE IF EXISTS douyin.metric_semantic_validations" )
        op.execute("DROP TABLE IF EXISTS douyin.video_clips" )
        op.execute("DROP TABLE IF EXISTS douyin.garment_skus" )
        op.execute("DROP TABLE IF EXISTS douyin.garment_colors" )
        op.execute("DROP TABLE IF EXISTS douyin.garment_styles" )
        op.execute("DROP TABLE IF EXISTS douyin.video_catalog_snapshots" )
        op.execute("DROP TABLE IF EXISTS douyin.collection_items" )
        op.execute("DROP TABLE IF EXISTS douyin.video_analysis_snapshots" )
        op.execute("DROP TABLE IF EXISTS douyin.collection_batch_parts" )
        op.execute("DROP TABLE IF EXISTS douyin.collection_batches" )
        op.execute("DROP TABLE IF EXISTS douyin.videos" )
        op.execute("DROP TABLE IF EXISTS douyin.collector_events" )
        op.execute("DROP TABLE IF EXISTS douyin.collector_expected_schedules" )
        op.execute("DROP TABLE IF EXISTS douyin.collector_instances" )
        op.execute("DROP TABLE IF EXISTS douyin.douyin_upload_tokens" )
        op.execute("DROP TABLE IF EXISTS douyin.douyin_creator_accounts" )
    finally:
        op.execute("RESET ROLE")
