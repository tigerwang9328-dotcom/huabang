"""Account-isolated persistence model for the frozen Douyin color analysis v3.1."""

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKeyConstraint,
    Index, Integer, JSON, Numeric, String, Text, Time, UniqueConstraint, text,
)
from sqlalchemy.sql import func

from app.core.database import Base


class DouyinColorModel(Base):
    __abstract__ = True
    __table_args__ = {"schema": "douyin"}


class DouyinCreatorAccount(DouyinColorModel):
    __tablename__ = "douyin_creator_accounts"
    __table_args__ = (
        CheckConstraint("status IN ('preconfigured','inactive','active','disabled')", name="ck_douyin_creator_account_status"),
        UniqueConstraint("account_key", name="uq_douyin_creator_account_key"),
        UniqueConstraint("expected_creator_fingerprint", name="uq_douyin_creator_account_creator_fingerprint"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_key = Column(String(64), nullable=False)
    display_name = Column(String(128), nullable=False)
    expected_creator_fingerprint = Column(String(64), nullable=False)
    expected_account_name = Column(String(128))
    status = Column(String(16), nullable=False, default="preconfigured")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


Index("uq_douyin_creator_one_active_account", DouyinCreatorAccount.status, unique=True, postgresql_where=text("status = 'active'"))


class DouyinUploadToken(DouyinColorModel):
    __tablename__ = "douyin_upload_tokens"
    __table_args__ = (
        CheckConstraint("status IN ('active','revoked','expired')", name="ck_douyin_upload_token_status"),
        UniqueConstraint("token_hash", name="uq_douyin_upload_token_hash"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_upload_token_account", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    token_hash = Column(String(64), nullable=False)
    token_prefix = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="active")
    last_used_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    created_by = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_by = Column(BigInteger)
    revoked_at = Column(DateTime(timezone=True))


class CollectorInstance(DouyinColorModel):
    __tablename__ = "collector_instances"
    __table_args__ = (
        CheckConstraint("current_status IN ('online_active','online_hidden','suspended','auth_required','upload_blocked','offline_expected','offline_unexpected')", name="ck_douyin_collector_status"),
        CheckConstraint("current_page_path IS NULL OR (current_page_path LIKE '/creator-micro/%' AND current_page_path NOT LIKE '%?%' AND current_page_path NOT LIKE '%#%')", name="ck_douyin_collector_page_path"),
        UniqueConstraint("account_id", "id", name="uq_douyin_collector_account_id"),
        UniqueConstraint("account_id", "installation_id", name="uq_douyin_collector_instance"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_collector_account", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    installation_id = Column(String(64), nullable=False)
    script_version = Column(String(64), nullable=False)
    schema_version = Column(Integer, nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True))
    current_status = Column(String(32), nullable=False, default="offline_expected")
    current_page_path = Column(String(512))
    current_page_type = Column(String(64))
    document_visibility = Column(String(16))
    observed_creator_fingerprint = Column(String(64))
    observed_account_name = Column(String(128))
    queued_batch_count = Column(Integer, nullable=False, default=0)
    queued_bytes = Column(BigInteger, nullable=False, default=0)
    last_error_category = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CollectorExpectedSchedule(DouyinColorModel):
    __tablename__ = "collector_expected_schedules"
    __table_args__ = (
        UniqueConstraint("account_id", "weekday_mask", "expected_start_local", name="uq_douyin_expected_schedule"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_expected_schedule_account", ondelete="CASCADE"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    weekday_mask = Column(Integer, nullable=False)
    expected_start_local = Column(Time, nullable=False)
    expected_end_local = Column(Time, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CollectorEvent(DouyinColorModel):
    __tablename__ = "collector_events"
    __table_args__ = (
        ForeignKeyConstraint(["account_id", "collector_instance_id"], ["douyin.collector_instances.account_id", "douyin.collector_instances.id"], name="fk_douyin_collector_event_instance", ondelete="CASCADE"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    collector_instance_id = Column(BigInteger)
    installation_id = Column(String(64), nullable=False)
    event_type = Column(String(64), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    error_category = Column(String(64))
    endpoint_name = Column(String(64))
    http_status = Column(Integer)
    business_status_code = Column(Integer)
    retry_count = Column(Integer)
    sanitized_message = Column(String(500))


class Video(DouyinColorModel):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("account_id", "id", name="uq_douyin_video_account_id"),
        UniqueConstraint("account_id", "video_id_string", name="uq_douyin_video_account_external_id"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_video_account", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    video_id_string = Column(String(64), nullable=False)
    title = Column(Text)
    published_at = Column(DateTime(timezone=True))
    duration_ms = Column(BigInteger)
    cover_path = Column(String(512))
    creator_detail_path = Column(String(512), nullable=False)
    source_type = Column(String(32), nullable=False)
    first_collected_at = Column(DateTime(timezone=True))
    last_collected_at = Column(DateTime(timezone=True))
    collection_status = Column(String(32), nullable=False, default="pending")


class CollectionBatch(DouyinColorModel):
    __tablename__ = "collection_batches"
    __table_args__ = (
        CheckConstraint("status IN ('receiving','completed','completed_with_errors','expired','abandoned','failed')", name="ck_douyin_collection_batch_status"),
        CheckConstraint("part_count > 0", name="ck_douyin_collection_batch_part_count"),
        CheckConstraint("source_date_start IS NULL OR source_date_end IS NULL OR source_date_start <= source_date_end", name="ck_douyin_collection_batch_source_dates"),
        CheckConstraint("item_count >= 0 AND success_count >= 0 AND skipped_count >= 0 AND failure_count >= 0", name="ck_douyin_collection_batch_counts"),
        UniqueConstraint("account_id", "id", name="uq_douyin_collection_batch_account_id"),
        UniqueConstraint("account_id", "client_batch_id", name="uq_douyin_collection_batch_client_id"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_collection_batch_account", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    client_batch_id = Column(String(64), nullable=False)
    schema_version = Column(Integer, nullable=False)
    script_version = Column(String(64), nullable=False)
    source_date_start = Column(Date)
    source_date_end = Column(Date)
    created_at_client = Column(DateTime(timezone=True))
    first_received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_part_received_at = Column(DateTime(timezone=True))
    finalized_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    part_count = Column(Integer, nullable=False)
    batch_hash = Column(String(64))
    status = Column(String(32), nullable=False, default="receiving")
    item_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    observed_creator_fingerprint = Column(String(64), nullable=False)
    installation_id = Column(String(64), nullable=False)


class CollectionBatchPart(DouyinColorModel):
    __tablename__ = "collection_batch_parts"
    __table_args__ = (
        CheckConstraint("part_number >= 1 AND record_count >= 0 AND uncompressed_bytes >= 0", name="ck_douyin_batch_part_bounds"),
        UniqueConstraint("account_id", "id", name="uq_douyin_batch_part_account_id"),
        UniqueConstraint("account_id", "batch_id", "id", name="uq_douyin_batch_part_account_batch_id"),
        UniqueConstraint("batch_id", "part_number", name="uq_douyin_batch_part_number"),
        UniqueConstraint("batch_id", "part_hash", name="uq_douyin_batch_part_hash"),
        ForeignKeyConstraint(["account_id", "batch_id"], ["douyin.collection_batches.account_id", "douyin.collection_batches.id"], name="fk_douyin_batch_part_account_batch", ondelete="CASCADE"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    batch_id = Column(BigInteger, nullable=False)
    part_number = Column(Integer, nullable=False)
    part_hash = Column(String(64), nullable=False)
    record_count = Column(Integer, nullable=False)
    uncompressed_bytes = Column(BigInteger, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(16), nullable=False, default="received")


class VideoAnalysisSnapshot(DouyinColorModel):
    __tablename__ = "video_analysis_snapshots"
    __table_args__ = (
        CheckConstraint("analysis_type IN (1,7)", name="ck_douyin_snapshot_analysis_type"),
        CheckConstraint("observation_window IN ('t2','t7','t30','ad_hoc')", name="ck_douyin_snapshot_observation_window"),
        UniqueConstraint("account_id", "id", name="uq_douyin_snapshot_account_id"),
        UniqueConstraint("account_id", "video_id", "analysis_type", "source_snapshot_hash", name="uq_douyin_analysis_snapshot_content"),
        ForeignKeyConstraint(["account_id", "video_id"], ["douyin.videos.account_id", "douyin.videos.id"], name="fk_douyin_snapshot_account_video", ondelete="RESTRICT"),
        ForeignKeyConstraint(["account_id", "first_seen_batch_id"], ["douyin.collection_batches.account_id", "douyin.collection_batches.id"], name="fk_douyin_snapshot_account_first_batch", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    video_id = Column(BigInteger, nullable=False)
    analysis_type = Column(Integer, nullable=False)
    collected_at = Column(DateTime(timezone=True), nullable=False)
    source_snapshot_hash = Column(String(64), nullable=False)
    raw_response_json = Column(JSON, nullable=False)
    normalized_curve_json = Column(JSON)
    normalization_version = Column(String(32))
    original_value_unit = Column(String(32))
    curve_quality_status = Column(String(32), nullable=False)
    similar_author_normalized_curve_json = Column(JSON)
    valley_list_json = Column(JSON)
    valley_related_items_json = Column(JSON)
    video_age_hours_at_collection = Column(Numeric(12, 3))
    observation_window = Column(String(16), nullable=False)
    curve_audience_count = Column(BigInteger)
    http_status = Column(Integer)
    business_status_code = Column(Integer)
    status_message = Column(String(500))
    first_seen_batch_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollectionItem(DouyinColorModel):
    __tablename__ = "collection_items"
    __table_args__ = (
        CheckConstraint("item_status IN ('pending','success','skipped_non_video','empty_curve','auth_failed','rate_limited','network_failed','http_failed','business_failed','upload_failed')", name="ck_douyin_collection_item_status"),
        UniqueConstraint("part_id", "raw_record_hash", name="uq_douyin_collection_item_raw_record"),
        ForeignKeyConstraint(["account_id", "batch_id", "part_id"], ["douyin.collection_batch_parts.account_id", "douyin.collection_batch_parts.batch_id", "douyin.collection_batch_parts.id"], name="fk_douyin_item_account_batch_part", ondelete="CASCADE"),
        ForeignKeyConstraint(["account_id", "snapshot_id"], ["douyin.video_analysis_snapshots.account_id", "douyin.video_analysis_snapshots.id"], name="fk_douyin_item_account_snapshot", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    batch_id = Column(BigInteger, nullable=False)
    part_id = Column(BigInteger, nullable=False)
    video_id_string = Column(String(64))
    analysis_type = Column(Integer)
    item_status = Column(String(32), nullable=False)
    error_category = Column(String(64))
    endpoint_name = Column(String(64))
    http_status = Column(Integer)
    business_status_code = Column(Integer)
    sanitized_error_message = Column(String(500))
    retry_count = Column(Integer, nullable=False, default=0)
    raw_record_hash = Column(String(64))
    snapshot_id = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VideoCatalogSnapshot(DouyinColorModel):
    __tablename__ = "video_catalog_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "video_id", "source_snapshot_hash", name="uq_douyin_catalog_snapshot_content"),
        ForeignKeyConstraint(["account_id", "video_id"], ["douyin.videos.account_id", "douyin.videos.id"], name="fk_douyin_catalog_snapshot_video", ondelete="CASCADE"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    video_id = Column(BigInteger, nullable=False)
    collected_at = Column(DateTime(timezone=True), nullable=False)
    play_count_at_collection = Column(BigInteger)
    traffic_source_json = Column(JSON)
    raw_item_whitelist_json = Column(JSON, nullable=False)
    source_snapshot_hash = Column(String(64), nullable=False)


class GarmentStyle(DouyinColorModel):
    __tablename__ = "garment_styles"
    __table_args__ = (
        CheckConstraint("status IN ('active','disabled')", name="ck_douyin_style_status"),
        CheckConstraint("garment_position IN ('outer','top','bottom','none')", name="ck_douyin_style_garment_position"),
        UniqueConstraint("account_id", "id", name="uq_douyin_style_account_id"),
        UniqueConstraint("account_id", "style_code", name="uq_douyin_style_code"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_style_account", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    style_code = Column(String(64), nullable=False)
    style_name = Column(String(255), nullable=False)
    main_image = Column(String(512))
    status = Column(String(16), nullable=False, default="active")
    garment_position = Column(String(16), nullable=False, default="none")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class GarmentColor(DouyinColorModel):
    __tablename__ = "garment_colors"
    __table_args__ = (
        UniqueConstraint("account_id", "id", name="uq_douyin_color_account_id"),
        UniqueConstraint("account_id", "style_id", "id", name="uq_douyin_color_account_style_id"),
        UniqueConstraint("account_id", "style_id", "color_code", name="uq_douyin_color_style_code"),
        ForeignKeyConstraint(["account_id", "style_id"], ["douyin.garment_styles.account_id", "douyin.garment_styles.id"], name="fk_douyin_color_account_style", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    style_id = Column(BigInteger, nullable=False)
    color_code = Column(String(64), nullable=False)
    color_name = Column(String(128), nullable=False)
    color_image = Column(String(512))
    status = Column(String(16), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class GarmentSku(DouyinColorModel):
    __tablename__ = "garment_skus"
    __table_args__ = (
        UniqueConstraint("account_id", "sku_code", name="uq_douyin_sku_code"),
        ForeignKeyConstraint(["account_id", "color_id"], ["douyin.garment_colors.account_id", "douyin.garment_colors.id"], name="fk_douyin_sku_account_color", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    color_id = Column(BigInteger, nullable=False)
    sku_code = Column(String(128), nullable=False)
    size_name = Column(String(64))
    status = Column(String(16), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VideoClip(DouyinColorModel):
    __tablename__ = "video_clips"
    __table_args__ = (
        CheckConstraint("start_ms >= 0 AND end_ms > start_ms", name="ck_douyin_clip_bounds"),
        CheckConstraint("input_start_ms >= 0 AND input_end_ms > input_start_ms", name="ck_douyin_clip_input_bounds"),
        CheckConstraint("curve_resolution_ms > 0", name="ck_douyin_clip_resolution"),
        CheckConstraint("version >= 1", name="ck_douyin_clip_version"),
        CheckConstraint("(focus_status = 'clear_primary' AND jsonb_array_length(outfit_parts_json) >= 2) OR (focus_status IN ('multi_focus','unclear') AND jsonb_array_length(outfit_parts_json) = 0)", name="ck_douyin_clip_outfit_composition"),
        CheckConstraint("focus_status IN ('clear_primary','multi_focus','unclear')", name="ck_douyin_clip_focus_status"),
        CheckConstraint("annotation_status IN ('draft','submitted','approved','rejected','deleted')", name="ck_douyin_clip_annotation_status"),
        UniqueConstraint("account_id", "id", name="uq_douyin_clip_account_id"),
        ForeignKeyConstraint(["account_id", "video_id"], ["douyin.videos.account_id", "douyin.videos.id"], name="fk_douyin_clip_account_video", ondelete="CASCADE"),
        ForeignKeyConstraint(["account_id", "style_id", "color_id"], ["douyin.garment_colors.account_id", "douyin.garment_colors.style_id", "douyin.garment_colors.id"], name="fk_douyin_clip_account_style_color", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    video_id = Column(BigInteger, nullable=False)
    style_id = Column(BigInteger)
    color_id = Column(BigInteger)
    start_ms = Column(BigInteger, nullable=False)
    end_ms = Column(BigInteger, nullable=False)
    input_start_ms = Column(BigInteger, nullable=False)
    input_end_ms = Column(BigInteger, nullable=False)
    curve_resolution_ms = Column(Integer, nullable=False)
    focus_status = Column(String(32), nullable=False)
    outfit_parts_json = Column(JSON, nullable=False, default=list)
    focus_note = Column(Text)
    annotation_status = Column(String(16), nullable=False, default="draft")
    overlap_reason = Column(Text)
    overlap_status = Column(String(32), nullable=False, default="not_required")
    overlap_approved_by = Column(BigInteger)
    overlap_approved_at = Column(DateTime(timezone=True))
    submitted_by = Column(BigInteger)
    submitted_at = Column(DateTime(timezone=True))
    approved_by = Column(BigInteger)
    approved_at = Column(DateTime(timezone=True))
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by = Column(BigInteger)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    deleted_at = Column(DateTime(timezone=True))


class MetricSemanticValidation(DouyinColorModel):
    __tablename__ = "metric_semantic_validations"
    __table_args__ = (
        CheckConstraint("semantics_status IN ('unverified','verified_lower_is_better','verified_higher_is_better','rejected')", name="ck_douyin_metric_semantics_status"),
        UniqueConstraint("account_id", "metric_key", name="uq_douyin_metric_semantic"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_metric_semantic_account", ondelete="CASCADE"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    metric_key = Column(String(64), nullable=False)
    semantics_status = Column(String(32), nullable=False, default="unverified")
    evidence_video_ids_json = Column(JSON, nullable=False, default=list)
    verified_by = Column(BigInteger)
    verified_at = Column(DateTime(timezone=True))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VideoColorMetric(DouyinColorModel):
    __tablename__ = "video_color_metrics"
    __table_args__ = (
        CheckConstraint("observation_window IN ('t2','t7','t30','ad_hoc')", name="ck_douyin_metric_observation_window"),
        CheckConstraint("retention_calculation_status IN ('pending','computed','insufficient_data','stale','failed')", name="ck_douyin_metric_retention_status"),
        CheckConstraint("bounce_calculation_status IN ('pending','computed','insufficient_data','stale','failed')", name="ck_douyin_metric_bounce_status"),
        UniqueConstraint("account_id", "video_id", "style_id", "color_id", "observation_window", "metric_version", "metric_input_hash", name="uq_douyin_video_color_metric"),
        ForeignKeyConstraint(["account_id", "video_id"], ["douyin.videos.account_id", "douyin.videos.id"], name="fk_douyin_metric_account_video", ondelete="RESTRICT"),
        ForeignKeyConstraint(["account_id", "style_id", "color_id"], ["douyin.garment_colors.account_id", "douyin.garment_colors.style_id", "douyin.garment_colors.id"], name="fk_douyin_metric_account_style_color", ondelete="RESTRICT"),
        ForeignKeyConstraint(["account_id", "retention_snapshot_id"], ["douyin.video_analysis_snapshots.account_id", "douyin.video_analysis_snapshots.id"], name="fk_douyin_metric_account_retention_snapshot", ondelete="RESTRICT"),
        ForeignKeyConstraint(["account_id", "bounce_snapshot_id"], ["douyin.video_analysis_snapshots.account_id", "douyin.video_analysis_snapshots.id"], name="fk_douyin_metric_account_bounce_snapshot", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    video_id = Column(BigInteger, nullable=False)
    style_id = Column(BigInteger, nullable=False)
    color_id = Column(BigInteger, nullable=False)
    observation_window = Column(String(16), nullable=False)
    retention_snapshot_id = Column(BigInteger, nullable=False)
    bounce_snapshot_id = Column(BigInteger)
    retention_source_hash = Column(String(64), nullable=False)
    bounce_source_hash = Column(String(64))
    annotation_set_hash = Column(String(64), nullable=False)
    metric_input_hash = Column(String(64), nullable=False)
    metric_version = Column(String(32), nullable=False)
    garment_position = Column(String(16), nullable=False, default="none")
    sku_code = Column(String(64))
    average_retention = Column(Numeric(12, 8))
    retention_drop = Column(Numeric(12, 8))
    average_platform_bounce_curve_value = Column(Numeric(12, 8))
    max_platform_bounce_curve_value = Column(Numeric(12, 8))
    clip_count = Column(Integer, nullable=False)
    total_clip_duration_ms = Column(BigInteger, nullable=False)
    average_relative_position = Column(Numeric(12, 8))
    earliest_relative_position = Column(Numeric(12, 8))
    latest_relative_position = Column(Numeric(12, 8))
    average_clip_duration_ms = Column(Numeric(14, 4))
    video_duration_ms = Column(BigInteger, nullable=False)
    dominant_position_segment = Column(String(16))
    retention_calculation_status = Column(String(32), nullable=False, default="pending")
    bounce_calculation_status = Column(String(32), nullable=False, default="pending")
    calculated_at = Column(DateTime(timezone=True))


class CalculationJob(DouyinColorModel):
    __tablename__ = "calculation_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','succeeded','retryable_failed','terminal_failed')", name="ck_douyin_calculation_job_status"),
        CheckConstraint("attempt_count >= 0", name="ck_douyin_calculation_job_attempt_count"),
        UniqueConstraint("deduplication_key", name="uq_douyin_calculation_job_deduplication"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_calculation_job_account", ondelete="CASCADE"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    job_type = Column(String(64), nullable=False)
    target_type = Column(String(64), nullable=False)
    target_id = Column(String(128), nullable=False)
    deduplication_key = Column(String(256), nullable=False)
    requested_by = Column(BigInteger)
    status = Column(String(32), nullable=False, default="queued")
    attempt_count = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    lease_owner = Column(String(128))
    lease_expires_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    sanitized_error_message = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ColorPerformanceSnapshot(DouyinColorModel):
    __tablename__ = "color_performance_snapshots"
    __table_args__ = (
        CheckConstraint("observation_window IN ('t2','t7','t30','ad_hoc')", name="ck_douyin_report_observation_window"),
        CheckConstraint("position_segment IN ('all','front','middle','rear')", name="ck_douyin_report_position_segment"),
        CheckConstraint("report_status IN ('generating','ready','stale','failed')", name="ck_douyin_report_status"),
        CheckConstraint("report_revision >= 1", name="ck_douyin_report_revision"),
        CheckConstraint("retention_video_sample_count >= 0 AND bounce_video_sample_count >= 0 AND eligible_video_sample_count >= 0 AND excluded_multi_focus_clip_count >= 0 AND excluded_unclear_clip_count >= 0 AND front_segment_sample_count >= 0 AND middle_segment_sample_count >= 0 AND rear_segment_sample_count >= 0", name="ck_douyin_report_counts"),
        UniqueConstraint("account_id", "id", name="uq_douyin_report_account_id"),
        ForeignKeyConstraint(["account_id", "style_id", "color_id"], ["douyin.garment_colors.account_id", "douyin.garment_colors.style_id", "douyin.garment_colors.id"], name="fk_douyin_report_account_style_color", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    style_id = Column(BigInteger, nullable=False)
    color_id = Column(BigInteger, nullable=False)
    as_of_date = Column(Date, nullable=False)
    source_data_cutoff_at = Column(DateTime(timezone=True), nullable=False)
    calculation_date = Column(Date, nullable=False)
    observation_window = Column(String(16), nullable=False)
    position_segment = Column(String(16), nullable=False)
    metric_version = Column(String(32), nullable=False)
    report_revision = Column(Integer, nullable=False)
    report_input_hash = Column(String(64), nullable=False)
    is_current = Column(Boolean, nullable=False, default=True)
    report_status = Column(String(32), nullable=False, default="generating")
    retention_video_sample_count = Column(Integer, nullable=False, default=0)
    bounce_video_sample_count = Column(Integer, nullable=False, default=0)
    eligible_video_sample_count = Column(Integer, nullable=False, default=0)
    excluded_multi_focus_clip_count = Column(Integer, nullable=False, default=0)
    excluded_unclear_clip_count = Column(Integer, nullable=False, default=0)
    average_retention = Column(Numeric(12, 8))
    retention_stddev_sample = Column(Numeric(12, 8))
    average_relative_position = Column(Numeric(12, 8))
    average_clip_duration_ms = Column(Numeric(14, 4))
    front_segment_sample_count = Column(Integer, nullable=False, default=0)
    middle_segment_sample_count = Column(Integer, nullable=False, default=0)
    rear_segment_sample_count = Column(Integer, nullable=False, default=0)
    other_colors_equal_weight_retention = Column(Numeric(12, 8))
    other_colors_video_weighted_retention = Column(Numeric(12, 8))
    retention_delta_vs_other_colors = Column(Numeric(12, 8))
    exposure_weighted_retention_reference = Column(Numeric(12, 8))
    average_platform_bounce_curve_value = Column(Numeric(12, 8))
    other_colors_equal_weight_bounce = Column(Numeric(12, 8))
    other_colors_video_weighted_bounce = Column(Numeric(12, 8))
    bounce_delta_vs_other_colors = Column(Numeric(12, 8))
    average_rank_eligible = Column(Boolean, nullable=False, default=False)
    stability_rank_eligible = Column(Boolean, nullable=False, default=False)
    calculated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


Index("uq_color_report_current", ColorPerformanceSnapshot.account_id, ColorPerformanceSnapshot.style_id, ColorPerformanceSnapshot.color_id, ColorPerformanceSnapshot.as_of_date, ColorPerformanceSnapshot.observation_window, ColorPerformanceSnapshot.position_segment, ColorPerformanceSnapshot.metric_version, unique=True, postgresql_where=text("is_current = TRUE"))
Index("uq_color_report_revision", ColorPerformanceSnapshot.account_id, ColorPerformanceSnapshot.style_id, ColorPerformanceSnapshot.color_id, ColorPerformanceSnapshot.as_of_date, ColorPerformanceSnapshot.observation_window, ColorPerformanceSnapshot.position_segment, ColorPerformanceSnapshot.metric_version, ColorPerformanceSnapshot.report_revision, unique=True)

class OutfitCombination(DouyinColorModel):
    """v4.0: one video's qualifying garment combination for outfit ranking."""

    __tablename__ = "outfit_combinations"
    __table_args__ = (
        CheckConstraint("observation_window IN ('t2','t7','t30','ad_hoc')", name="ck_douyin_outfit_observation_window"),
        CheckConstraint("participant_count >= 2", name="ck_douyin_outfit_participant_count"),
        UniqueConstraint("account_id", "id", name="uq_douyin_outfit_account_id"),
        UniqueConstraint("account_id", "video_id", "observation_window", "combination_key", name="uq_douyin_outfit_combination"),
        ForeignKeyConstraint(["account_id", "video_id"], ["douyin.videos.account_id", "douyin.videos.id"], name="fk_douyin_outfit_account_video", ondelete="CASCADE"),
        ForeignKeyConstraint(["account_id", "retention_snapshot_id"], ["douyin.video_analysis_snapshots.account_id", "douyin.video_analysis_snapshots.id"], name="fk_douyin_outfit_retention_snapshot", ondelete="RESTRICT"),
        ForeignKeyConstraint(["account_id", "bounce_snapshot_id"], ["douyin.video_analysis_snapshots.account_id", "douyin.video_analysis_snapshots.id"], name="fk_douyin_outfit_bounce_snapshot", ondelete="RESTRICT"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    video_id = Column(BigInteger, nullable=False)
    observation_window = Column(String(16), nullable=False)
    combination_key = Column(String(512), nullable=False)
    participant_count = Column(Integer, nullable=False)
    annotation_set_hash = Column(String(64), nullable=False)
    retention_snapshot_id = Column(BigInteger, nullable=False)
    bounce_snapshot_id = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OutfitColorMetric(DouyinColorModel):
    """v4.0: aggregated metrics for an outfit combination (>=2 garments)."""

    __tablename__ = "outfit_color_metrics"
    __table_args__ = (
        CheckConstraint("observation_window IN ('t2','t7','t30','ad_hoc')", name="ck_douyin_outfit_metric_observation_window"),
        CheckConstraint("retention_calculation_status IN ('pending','computed','insufficient_data','stale','failed')", name="ck_douyin_outfit_metric_retention_status"),
        CheckConstraint("bounce_calculation_status IN ('pending','computed','insufficient_data','stale','failed')", name="ck_douyin_outfit_metric_bounce_status"),
        UniqueConstraint("account_id", "id", name="uq_douyin_outfit_metric_account_id"),
        UniqueConstraint("account_id", "combination_key", "observation_window", "metric_version", "metric_input_hash", name="uq_douyin_outfit_color_metric"),
        ForeignKeyConstraint(["account_id"], ["douyin.douyin_creator_accounts.id"], name="fk_douyin_outfit_metric_account", ondelete="CASCADE"),
        {"schema": "douyin"},
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    combination_key = Column(String(512), nullable=False)
    observation_window = Column(String(16), nullable=False)
    metric_version = Column(String(32), nullable=False)
    metric_input_hash = Column(String(64), nullable=False)
    average_retention = Column(Numeric(12, 8))
    retention_drop = Column(Numeric(12, 8))
    average_platform_bounce_curve_value = Column(Numeric(12, 8))
    max_platform_bounce_curve_value = Column(Numeric(12, 8))
    participant_count = Column(Integer, nullable=False)
    total_clip_duration_ms = Column(BigInteger, nullable=False)
    video_duration_ms = Column(BigInteger, nullable=False)
    dominant_position_segment = Column(String(16))
    retention_calculation_status = Column(String(32), nullable=False, default="pending")
    bounce_calculation_status = Column(String(32), nullable=False, default="pending")
    calculated_at = Column(DateTime(timezone=True))
