"""Persistent, account-isolated foundation for Douyin color analytics.

This module deliberately has its own SQLAlchemy metadata and PostgreSQL schema.
The global application Alembic chain therefore remains untouched, including the
Finance schemas that have a separate privilege boundary.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Text,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class DouyinColorBase(DeclarativeBase):
    metadata = MetaData(schema="douyin")


class DouyinColorModel(DouyinColorBase):
    __abstract__ = True
    __table_args__ = {"schema": "douyin"}


class DouyinCreatorAccount(DouyinColorModel):
    __tablename__ = "douyin_creator_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('preconfigured', 'inactive', 'active', 'disabled')",
            name="ck_douyin_creator_account_status",
        ),
        UniqueConstraint("account_key", name="uq_douyin_creator_account_key"),
        UniqueConstraint(
            "expected_creator_fingerprint",
            name="uq_douyin_creator_account_creator_fingerprint",
        ),
        {"schema": "douyin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_key = Column(String(64), nullable=False)
    display_name = Column(String(128), nullable=False)
    # The raw creator id is never persisted. Request handling compares a
    # transient observed id after fingerprinting it.
    expected_creator_fingerprint = Column(String(64), nullable=False)
    expected_account_name = Column(String(128))
    status = Column(String(16), nullable=False, default="preconfigured")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


Index(
    "uq_douyin_creator_one_active_account",
    DouyinCreatorAccount.status,
    unique=True,
    postgresql_where=text("status = 'active'"),
)


class DouyinUploadToken(DouyinColorModel):
    __tablename__ = "douyin_upload_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_douyin_upload_token_hash"),
        ForeignKeyConstraint(
            ["account_id"],
            ["douyin.douyin_creator_accounts.id"],
            name="fk_douyin_upload_token_account",
            ondelete="RESTRICT",
        ),
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
        CheckConstraint(
            "current_page_path IS NULL OR (current_page_path LIKE '/creator-micro/%' AND current_page_path NOT LIKE '%?%' AND current_page_path NOT LIKE '%#%')",
            name="ck_douyin_collector_page_path",
        ),
        UniqueConstraint("account_id", "installation_id", name="uq_douyin_collector_instance"),
        ForeignKeyConstraint(
            ["account_id"],
            ["douyin.douyin_creator_accounts.id"],
            name="fk_douyin_collector_instance_account",
            ondelete="RESTRICT",
        ),
        {"schema": "douyin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    installation_id = Column(String(64), nullable=False)
    script_version = Column(String(64), nullable=False)
    schema_version = Column(String(64), nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True))
    current_status = Column(String(32), nullable=False, default="offline_expected")
    current_page_path = Column(String(512))
    current_page_type = Column(String(64))
    document_visibility = Column(String(16))
    queued_batch_count = Column(Integer, nullable=False, default=0)
    queued_bytes = Column(BigInteger, nullable=False, default=0)
    last_error_category = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Video(DouyinColorModel):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("account_id", "id", name="uq_douyin_video_account_id"),
        UniqueConstraint("account_id", "video_id_string", name="uq_douyin_video_account_external_id"),
        ForeignKeyConstraint(
            ["account_id"],
            ["douyin.douyin_creator_accounts.id"],
            name="fk_douyin_video_account",
            ondelete="RESTRICT",
        ),
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
        CheckConstraint(
            "status IN ('receiving', 'completed', 'completed_with_errors', 'expired', 'abandoned', 'failed')",
            name="ck_douyin_collection_batch_status",
        ),
        CheckConstraint("part_count > 0", name="ck_douyin_collection_batch_part_count"),
        UniqueConstraint("account_id", "id", name="uq_douyin_collection_batch_account_id"),
        UniqueConstraint("account_id", "client_batch_id", name="uq_douyin_collection_batch_client_id"),
        ForeignKeyConstraint(
            ["account_id"],
            ["douyin.douyin_creator_accounts.id"],
            name="fk_douyin_collection_batch_account",
            ondelete="RESTRICT",
        ),
        {"schema": "douyin"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False)
    client_batch_id = Column(String(64), nullable=False)
    schema_version = Column(String(64), nullable=False)
    script_version = Column(String(64), nullable=False)
    part_count = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="receiving")
    observed_creator_fingerprint = Column(String(64), nullable=False)
    installation_id = Column(String(64), nullable=False)
    batch_hash = Column(String(64))
    item_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    first_received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_part_received_at = Column(DateTime(timezone=True))
    finalized_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)


class CollectionBatchPart(DouyinColorModel):
    __tablename__ = "collection_batch_parts"
    __table_args__ = (
        UniqueConstraint("account_id", "id", name="uq_douyin_batch_part_account_id"),
        UniqueConstraint("batch_id", "part_number", name="uq_douyin_batch_part_number"),
        UniqueConstraint("batch_id", "part_hash", name="uq_douyin_batch_part_hash"),
        ForeignKeyConstraint(
            ["account_id", "batch_id"],
            ["douyin.collection_batches.account_id", "douyin.collection_batches.id"],
            name="fk_douyin_batch_part_account_batch",
            ondelete="CASCADE",
        ),
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
        UniqueConstraint("account_id", "id", name="uq_douyin_snapshot_account_id"),
        UniqueConstraint(
            "account_id", "video_id", "analysis_type", "source_snapshot_hash",
            name="uq_douyin_analysis_snapshot_content",
        ),
        ForeignKeyConstraint(
            ["account_id", "video_id"],
            ["douyin.videos.account_id", "douyin.videos.id"],
            name="fk_douyin_snapshot_account_video",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "first_seen_batch_id"],
            ["douyin.collection_batches.account_id", "douyin.collection_batches.id"],
            name="fk_douyin_snapshot_account_first_batch",
            ondelete="RESTRICT",
        ),
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
    observation_window = Column(String(16), nullable=False)
    first_seen_batch_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CollectionItem(DouyinColorModel):
    __tablename__ = "collection_items"
    __table_args__ = (
        CheckConstraint(
            "item_status IN ('pending', 'success', 'skipped_non_video', 'empty_curve', 'auth_failed', 'rate_limited', 'network_failed', 'http_failed', 'business_failed', 'upload_failed')",
            name="ck_douyin_collection_item_status",
        ),
        UniqueConstraint("part_id", "raw_record_hash", name="uq_douyin_collection_item_raw_record"),
        ForeignKeyConstraint(
            ["account_id", "batch_id"],
            ["douyin.collection_batches.account_id", "douyin.collection_batches.id"],
            name="fk_douyin_item_account_batch",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["account_id", "part_id"],
            ["douyin.collection_batch_parts.account_id", "douyin.collection_batch_parts.id"],
            name="fk_douyin_item_account_part",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["account_id", "snapshot_id"],
            ["douyin.video_analysis_snapshots.account_id", "douyin.video_analysis_snapshots.id"],
            name="fk_douyin_item_account_snapshot",
            ondelete="RESTRICT",
        ),
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
