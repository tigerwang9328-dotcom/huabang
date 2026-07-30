import asyncio
from pathlib import Path


def test_account_scoped_models_use_only_douyin_schema_and_explicit_account_ids():
    from app.models.douyin_color_analytics import (
        CollectionBatch,
        CollectionItem,
        CollectorInstance,
        DouyinCreatorAccount,
        DouyinUploadToken,
        Video,
        VideoAnalysisSnapshot,
    )

    tables = [
        DouyinCreatorAccount,
        DouyinUploadToken,
        CollectorInstance,
        CollectionBatch,
        CollectionItem,
        Video,
        VideoAnalysisSnapshot,
    ]
    for model in tables:
        assert model.__table__.schema == "douyin"
    for model in tables[1:]:
        assert "account_id" in model.__table__.c


def test_account_model_enforces_one_active_account_and_never_persists_raw_creator_id():
    from app.models.douyin_color_analytics import DouyinCreatorAccount

    columns = DouyinCreatorAccount.__table__.c
    assert "expected_creator_fingerprint" in columns
    assert "expected_creator_id" not in columns
    index_sql = " ".join(
        str(index.dialect_options["postgresql"].get("where"))
        for index in DouyinCreatorAccount.__table__.indexes
    )
    assert "status = 'active'" in index_sql


def test_account_scoped_foreign_keys_carry_account_id_in_their_constraint():
    from app.models.douyin_color_analytics import CollectionItem, VideoAnalysisSnapshot

    collection_item_fk_columns = {
        tuple(foreign_key_constraint.column_keys)
        for foreign_key_constraint in CollectionItem.__table__.foreign_key_constraints
    }
    snapshot_fk_columns = {
        tuple(foreign_key_constraint.column_keys)
        for foreign_key_constraint in VideoAnalysisSnapshot.__table__.foreign_key_constraints
    }
    assert ("account_id", "batch_id", "part_id") in collection_item_fk_columns
    assert ("account_id", "video_id") in snapshot_fk_columns


def test_collection_boundary_constraints_reject_an_invalid_page_path_or_part_count():
    from app.models.douyin_color_analytics import CollectionBatch, CollectorInstance

    instance_checks = {str(constraint.sqltext) for constraint in CollectorInstance.__table__.constraints if hasattr(constraint, "sqltext")}
    batch_checks = {str(constraint.sqltext) for constraint in CollectionBatch.__table__.constraints if hasattr(constraint, "sqltext")}
    assert any("current_page_path" in check and "?" in check and "#" in check for check in instance_checks)
    assert "part_count > 0" in batch_checks


class _Session:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flush_count += 1


class _User:
    id = 88
    username = "internal-user"


def test_uniform_audit_writer_flushes_within_request_transaction_and_redacts_secrets():
    from app.services.operation_audit_service import write_operation_audit

    session = _Session()
    log = asyncio.run(
        write_operation_audit(
            session,
            actor=_User(),
            module="douyin_color",
            action="account.bootstrap",
            target_type="creator_account",
            target_id="primary",
            after_data={"status": "preconfigured", "token": "must-not-persist"},
        )
    )

    assert session.added == [log]
    assert session.flush_count == 1
    assert log.user_id == 88
    assert log.after_data == {"status": "preconfigured", "token": "[REDACTED]"}


def test_audit_writer_redacts_signed_urls_even_when_the_field_name_looks_safe():
    from app.services.operation_audit_service import redact_audit_payload

    assert redact_audit_payload({"detail_path": "https://example.test/detail?msToken=nope"}) == {
        "detail_path": "[REDACTED]"
    }


def test_existing_system_and_auth_audit_helpers_delegate_to_the_uniform_writer():
    backend_root = Path(__file__).resolve().parents[1]
    system_source = (backend_root / "app" / "api" / "v1" / "system.py").read_text(encoding="utf-8")
    auth_source = (backend_root / "app" / "api" / "v1" / "auth.py").read_text(encoding="utf-8")

    assert "from app.services.operation_audit_service import write_operation_audit" in system_source
    assert "return await write_operation_audit(" in system_source
    assert "from app.services.operation_audit_service import write_operation_audit" in auth_source
    assert "return await write_operation_audit(" in auth_source


def test_dedicated_migrator_assets_do_not_grant_finance_access_or_create_a_second_alembic_head():
    backend_root = Path(__file__).resolve().parents[1]
    repository_root = backend_root.parent
    runner = (repository_root / "deploy" / "run_douyin_color_migrations.sh").read_text(encoding="utf-8")
    bootstrap = (repository_root / "deploy" / "bootstrap_douyin_color_migrator.sql").read_text(encoding="utf-8")

    assert "alembic.ini" in runner
    assert "alembic_douyin" not in runner
    assert "huabang_douyin_migrator" in bootstrap
    assert "CREATE SCHEMA IF NOT EXISTS douyin AUTHORIZATION huabang_douyin_migrator" in bootstrap
    assert "fin_current" not in bootstrap
    assert "fin_history" not in bootstrap
    assert "GRANT .* ON ALL TABLES IN SCHEMA fin" not in bootstrap


def test_rbac_bootstrap_uses_the_frozen_v31_platform_permission_codes():
    backend_root = Path(__file__).resolve().parents[1]
    source = (backend_root / "scripts" / "bootstrap_douyin_color_permissions.py").read_text(encoding="utf-8")

    assert "select(SysRole).where(SysRole.status == 1)" in source
    for permission_code in (
        "douyin.collector.write",
        "douyin.annotation.edit",
        "douyin.annotation.approve",
        "douyin.report.view",
        "douyin.report.export",
        "douyin.admin",
        "douyin.audit.read",
    ):
        assert permission_code in source
    assert "douyin_color:" not in source
