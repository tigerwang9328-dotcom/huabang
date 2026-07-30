from pathlib import Path


def test_v31_model_exposes_every_frozen_table_in_the_single_douyin_schema():
    from app.models.douyin_color_analytics import (
        CalculationJob,
        CollectionBatch,
        CollectionBatchPart,
        CollectionItem,
        CollectorEvent,
        CollectorExpectedSchedule,
        CollectorInstance,
        ColorPerformanceSnapshot,
        DouyinCreatorAccount,
        DouyinUploadToken,
        GarmentColor,
        GarmentSku,
        GarmentStyle,
        MetricSemanticValidation,
        Video,
        VideoAnalysisSnapshot,
        VideoCatalogSnapshot,
        VideoClip,
        VideoColorMetric,
    )

    models = [
        DouyinCreatorAccount, DouyinUploadToken, CollectorInstance, CollectorExpectedSchedule, CollectorEvent,
        CollectionBatch, CollectionBatchPart, CollectionItem, Video, VideoCatalogSnapshot, VideoAnalysisSnapshot,
        GarmentStyle, GarmentColor, GarmentSku, VideoClip, MetricSemanticValidation, VideoColorMetric,
        CalculationJob, ColorPerformanceSnapshot,
    ]
    assert {model.__tablename__ for model in models} == {
        "douyin_creator_accounts", "douyin_upload_tokens", "collector_instances", "collector_expected_schedules",
        "collector_events", "collection_batches", "collection_batch_parts", "collection_items", "videos",
        "video_catalog_snapshots", "video_analysis_snapshots", "garment_styles", "garment_colors", "garment_skus",
        "video_clips", "metric_semantic_validations", "video_color_metrics", "calculation_jobs",
        "color_performance_snapshots",
    }
    assert all(model.__table__.schema == "douyin" for model in models)
    assert all("account_id" in model.__table__.c for model in models[1:])


def test_v31_model_uses_composite_account_foreign_keys_and_focus_constraints():
    from app.models.douyin_color_analytics import (
        CollectionBatchPart,
        CollectionItem,
        ColorPerformanceSnapshot,
        GarmentColor,
        VideoClip,
        VideoColorMetric,
    )

    color_fks = {tuple(foreign_key_constraint.column_keys) for foreign_key_constraint in GarmentColor.__table__.foreign_key_constraints}
    clip_fks = {tuple(foreign_key_constraint.column_keys) for foreign_key_constraint in VideoClip.__table__.foreign_key_constraints}
    metric_fks = {tuple(foreign_key_constraint.column_keys) for foreign_key_constraint in VideoColorMetric.__table__.foreign_key_constraints}
    report_fks = {tuple(foreign_key_constraint.column_keys) for foreign_key_constraint in ColorPerformanceSnapshot.__table__.foreign_key_constraints}
    item_fks = {tuple(foreign_key_constraint.column_keys) for foreign_key_constraint in CollectionItem.__table__.foreign_key_constraints}
    clip_checks = {str(constraint.sqltext) for constraint in VideoClip.__table__.constraints if hasattr(constraint, "sqltext")}

    assert ("account_id", "style_id") in color_fks
    assert ("account_id", "style_id", "id") in {
        tuple(constraint.columns.keys()) for constraint in GarmentColor.__table__.constraints if constraint.name == "uq_douyin_color_account_style_id"
    }
    assert ("account_id", "style_id", "color_id") in clip_fks
    assert ("account_id", "style_id", "color_id") in metric_fks
    assert ("account_id", "style_id", "color_id") in report_fks
    assert ("account_id", "batch_id", "id") in {
        tuple(constraint.columns.keys()) for constraint in CollectionBatchPart.__table__.constraints if constraint.name == "uq_douyin_batch_part_account_batch_id"
    }
    assert ("account_id", "batch_id", "part_id") in item_fks
    assert ("account_id", "retention_snapshot_id") in metric_fks
    assert any("clear_primary" in check and "multi_focus" in check and "unclear" in check for check in clip_checks)


def test_v31_report_indexes_are_current_and_revision_unique_without_nullable_scope_keys():
    from app.models.douyin_color_analytics import ColorPerformanceSnapshot

    indexes = {index.name: index for index in ColorPerformanceSnapshot.__table__.indexes}
    assert {"uq_color_report_current", "uq_color_report_revision"} <= set(indexes)
    assert "is_current = TRUE" in str(indexes["uq_color_report_current"].dialect_options["postgresql"].get("where"))
    assert [column.name for column in indexes["uq_color_report_revision"].columns] == [
        "account_id", "style_id", "color_id", "as_of_date", "observation_window", "position_segment",
        "metric_version", "report_revision",
    ]


def test_v31_uses_the_existing_global_alembic_chain_and_has_no_second_migration_chain():
    backend_root = Path(__file__).resolve().parents[1]
    version_files = list((backend_root / "alembic" / "versions").glob("*douyin_color_analytics.py"))
    env = (backend_root / "alembic" / "env.py").read_text(encoding="utf-8")

    assert len(version_files) == 1
    assert not (backend_root / "alembic_douyin").exists()
    assert not (backend_root / "alembic_douyin.ini").exists()
    assert "ALEMBIC_DATABASE_URL" in env


def test_v31_request_schemas_exclude_client_account_identity_and_freeze_status_values():
    from app.schemas.douyin_color_analytics import (
        BatchPartEnvelope,
        CollectionBatchStatus,
        CalculationStatus,
        FocusStatus,
        MetricSemanticsStatus,
        ObservationWindow,
        ReportStatus,
    )

    assert set(FocusStatus) == {FocusStatus.clear_primary, FocusStatus.multi_focus, FocusStatus.unclear}
    assert set(ObservationWindow) == {ObservationWindow.t2, ObservationWindow.t7, ObservationWindow.t30, ObservationWindow.ad_hoc}
    assert CollectionBatchStatus.completed_with_errors.value == "completed_with_errors"
    assert set(MetricSemanticsStatus) == {
        MetricSemanticsStatus.unverified,
        MetricSemanticsStatus.verified_lower_is_better,
        MetricSemanticsStatus.verified_higher_is_better,
        MetricSemanticsStatus.rejected,
    }
    assert set(CalculationStatus) == {
        CalculationStatus.pending,
        CalculationStatus.computed,
        CalculationStatus.insufficient_data,
        CalculationStatus.stale,
        CalculationStatus.failed,
    }
    assert set(ReportStatus) == {
        ReportStatus.generating,
        ReportStatus.ready,
        ReportStatus.stale,
        ReportStatus.failed,
    }
    assert "account_id" not in BatchPartEnvelope.model_fields
    assert "account_key" not in BatchPartEnvelope.model_fields


def test_v31_database_constraints_cover_all_frozen_state_sets_and_static_bounds():
    from app.models.douyin_color_analytics import (
        CalculationJob,
        CollectionBatch,
        CollectionBatchPart,
        ColorPerformanceSnapshot,
        MetricSemanticValidation,
        VideoAnalysisSnapshot,
        VideoClip,
        VideoColorMetric,
    )

    def checks(model):
        return {constraint.name: str(constraint.sqltext) for constraint in model.__table__.constraints if hasattr(constraint, "sqltext")}

    assert "analysis_type IN (1,7)" in checks(VideoAnalysisSnapshot)["ck_douyin_snapshot_analysis_type"]
    assert "observation_window IN ('t2','t7','t30','ad_hoc')" in checks(VideoAnalysisSnapshot)["ck_douyin_snapshot_observation_window"]
    assert "source_date_start <= source_date_end" in checks(CollectionBatch)["ck_douyin_collection_batch_source_dates"]
    assert "part_number >= 1" in checks(CollectionBatchPart)["ck_douyin_batch_part_bounds"]
    assert "curve_resolution_ms > 0" in checks(VideoClip)["ck_douyin_clip_resolution"]
    assert "verified_lower_is_better" in checks(MetricSemanticValidation)["ck_douyin_metric_semantics_status"]
    assert "computed" in checks(VideoColorMetric)["ck_douyin_metric_retention_status"]
    assert "observation_window IN ('t2','t7','t30','ad_hoc')" in checks(VideoColorMetric)["ck_douyin_metric_observation_window"]
    assert "report_status IN ('generating','ready','stale','failed')" in checks(ColorPerformanceSnapshot)["ck_douyin_report_status"]
    assert "report_revision >= 1" in checks(ColorPerformanceSnapshot)["ck_douyin_report_revision"]
    assert "attempt_count >= 0" in checks(CalculationJob)["ck_douyin_calculation_job_attempt_count"]
