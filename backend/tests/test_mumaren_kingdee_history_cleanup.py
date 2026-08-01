import os

import pytest


os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")


@pytest.mark.asyncio
async def test_execute_rejects_noncanonical_history_identity_before_any_database_access():
    """A CLI caller must never be able to redirect cleanup at another batch."""
    from app.services.mumaren_finance_center.kingdee_history_cleanup import (
        KingdeeHistoryCleanupError,
        KingdeeHistoryCleanupRequest,
        cleanup_misarchived_kingdee_history,
    )

    class Db:
        async def execute(self, _statement):
            raise AssertionError("noncanonical cleanup must not query the database")

    with pytest.raises(KingdeeHistoryCleanupError, match="固定"):
        await cleanup_misarchived_kingdee_history(
            Db(),
            KingdeeHistoryCleanupRequest("another-batch", "f" * 64, "three-books", "b" * 64),
            execute=True,
        )


@pytest.mark.asyncio
async def test_execute_requires_actual_replacement_database_counts_not_batch_expectations():
    """A forged import-batch expectation must not unlock destructive cleanup."""
    from app.models.mumaren_finance_center import FinanceCenterMumarenKingdeeImportBatch
    from app.services.mumaren_finance_center.kingdee_history_cleanup import (
        MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
        KingdeeHistoryCleanupError,
        KingdeeHistoryCleanupRequest,
        cleanup_misarchived_kingdee_history,
    )

    import_batch = FinanceCenterMumarenKingdeeImportBatch(
        id=12,
        batch_key="three-books",
        manifest_checksum="b" * 64,
        validation_status="imported",
        expected_book_count=3,
        expected_voucher_count=339,
        expected_line_count=4596,
        expected_balance_snapshot_count=6868,
    )

    class ScalarResult:
        def __init__(self, value): self.value = value
        def scalar_one_or_none(self): return self.value
        def scalar_one(self): return self.value

    class Db:
        def __init__(self): self.statements = []
        async def execute(self, statement):
            query = str(statement)
            self.statements.append(query)
            if "kingdee_import_batches" in query:
                return ScalarResult(import_batch)
            if "finance_center_mumaren_" in query:
                return ScalarResult(0)
            raise AssertionError(query)

    db = Db()
    with pytest.raises(KingdeeHistoryCleanupError, match="实际迁移数据"):
        await cleanup_misarchived_kingdee_history(
            db,
            KingdeeHistoryCleanupRequest(
                MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
                MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
                "three-books",
                "b" * 64,
            ),
            execute=True,
        )
    assert not any("DELETE" in query.upper() for query in db.statements)


def test_cleanup_uses_fixed_history_identity_and_allows_replacement_identity():
    from app.services.mumaren_finance_center.kingdee_history_cleanup import (
        MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
        KingdeeHistoryCleanupRequest,
    )

    request = KingdeeHistoryCleanupRequest(
        source_batch_key=MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        source_checksum=MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
        kingdee_batch_key="three-books-2026-08",
        kingdee_manifest_checksum="b" * 64,
    )

    assert request.source_batch_key == MISARCHIVED_HISTORY_SOURCE_BATCH_KEY
    assert request.source_checksum == MISARCHIVED_HISTORY_SOURCE_CHECKSUM
    assert request.kingdee_manifest_checksum == "b" * 64


@pytest.mark.asyncio
async def test_dry_run_needs_only_the_exact_history_batch_identity():
    from app.models.mumaren_finance_center import FinanceCenterMumarenHistoryImportBatch
    from app.services.mumaren_finance_center.kingdee_history_cleanup import (
        MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
        KingdeeHistoryCleanupRequest,
        cleanup_misarchived_kingdee_history,
    )

    history_batch = FinanceCenterMumarenHistoryImportBatch(
        id=11, source_system="kingdee", source_batch_key=MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        source_checksum=MISARCHIVED_HISTORY_SOURCE_CHECKSUM, record_count=1,
    )

    class Result:
        def scalar_one_or_none(self): return history_batch
        def scalar_one(self): return 1

    class Db:
        async def execute(self, statement):
            query = str(statement)
            if query == "SET TRANSACTION READ ONLY" or "history_import_batches" in query or "count" in query.lower():
                return Result()
            raise AssertionError(query)

    result = await cleanup_misarchived_kingdee_history(
        Db(), KingdeeHistoryCleanupRequest(MISARCHIVED_HISTORY_SOURCE_BATCH_KEY, MISARCHIVED_HISTORY_SOURCE_CHECKSUM, None, None), execute=False,
    )

    assert result.status == "dry_run"


@pytest.mark.asyncio
async def test_dry_run_sets_readonly_transaction_and_never_deletes():
    from app.models.mumaren_finance_center import (
        FinanceCenterMumarenHistoryImportBatch,
        FinanceCenterMumarenKingdeeImportBatch,
    )
    from app.services.mumaren_finance_center.kingdee_history_cleanup import (
        MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
        KingdeeHistoryCleanupRequest,
        cleanup_misarchived_kingdee_history,
    )

    history_batch = FinanceCenterMumarenHistoryImportBatch(
        id=11, source_system="kingdee", source_batch_key=MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        source_checksum=MISARCHIVED_HISTORY_SOURCE_CHECKSUM, record_count=2,
    )
    import_batch = FinanceCenterMumarenKingdeeImportBatch(
        id=12, batch_key="three-books", manifest_checksum="b" * 64,
        validation_status="imported", expected_book_count=3, expected_voucher_count=4,
        expected_line_count=8, expected_balance_snapshot_count=3,
    )

    class ScalarResult:
        def __init__(self, value): self.value = value
        def scalar_one_or_none(self): return self.value

    class CountResult:
        def scalar_one(self): return 2

    class Db:
        def __init__(self): self.statements = []
        async def execute(self, statement):
            self.statements.append(str(statement))
            query = str(statement)
            if query == "SET TRANSACTION READ ONLY":
                return ScalarResult(None)
            if "kingdee_import_batches" in query:
                return ScalarResult(import_batch)
            if "history_import_batches" in query:
                return ScalarResult(history_batch)
            if "count" in query.lower():
                return CountResult()
            raise AssertionError(query)

    db = Db()
    result = await cleanup_misarchived_kingdee_history(
        db,
        KingdeeHistoryCleanupRequest(MISARCHIVED_HISTORY_SOURCE_BATCH_KEY, MISARCHIVED_HISTORY_SOURCE_CHECKSUM, "three-books", "b" * 64),
        execute=False,
    )

    assert result.status == "dry_run"
    assert result.candidate_voucher_count == 2
    assert any("SET TRANSACTION READ ONLY" in query for query in db.statements)
    assert not any("DELETE" in query.upper() for query in db.statements)


@pytest.mark.asyncio
async def test_execute_is_blocked_unless_exact_three_book_batch_is_validated_or_imported():
    from app.models.mumaren_finance_center import FinanceCenterMumarenKingdeeImportBatch
    from app.services.mumaren_finance_center.kingdee_history_cleanup import (
        MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
        KingdeeHistoryCleanupError,
        KingdeeHistoryCleanupRequest,
        cleanup_misarchived_kingdee_history,
    )

    invalid_import_batch = FinanceCenterMumarenKingdeeImportBatch(
        id=12, batch_key="three-books", manifest_checksum="b" * 64,
        validation_status="planned", expected_book_count=3, expected_voucher_count=4,
        expected_line_count=8, expected_balance_snapshot_count=3,
    )

    class Result:
        def scalar_one_or_none(self): return invalid_import_batch

    class Db:
        def __init__(self): self.statements = []
        async def execute(self, statement):
            self.statements.append(str(statement)); return Result()

    db = Db()
    with pytest.raises(KingdeeHistoryCleanupError, match="三账套"):
        await cleanup_misarchived_kingdee_history(
            db,
            KingdeeHistoryCleanupRequest(MISARCHIVED_HISTORY_SOURCE_BATCH_KEY, MISARCHIVED_HISTORY_SOURCE_CHECKSUM, "three-books", "b" * 64),
            execute=True,
        )
    assert not any("DELETE" in query.upper() for query in db.statements)


@pytest.mark.asyncio
async def test_execute_deletes_only_the_matched_history_vouchers_then_its_batch():
    from app.models.mumaren_finance_center import (
        FinanceCenterMumarenHistoryImportBatch,
        FinanceCenterMumarenKingdeeImportBatch,
    )
    from app.services.mumaren_finance_center.kingdee_history_cleanup import (
        MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        MISARCHIVED_HISTORY_SOURCE_CHECKSUM,
        EXPECTED_REPLACEMENT_BOOK_COUNT,
        EXPECTED_REPLACEMENT_VOUCHER_COUNT,
        EXPECTED_REPLACEMENT_LINE_COUNT,
        EXPECTED_REPLACEMENT_SNAPSHOT_COUNT,
        EXPECTED_MISARCHIVED_VOUCHER_COUNT,
        KingdeeHistoryCleanupRequest,
        cleanup_misarchived_kingdee_history,
    )

    history_batch = FinanceCenterMumarenHistoryImportBatch(
        id=11, source_system="kingdee", source_batch_key=MISARCHIVED_HISTORY_SOURCE_BATCH_KEY,
        source_checksum=MISARCHIVED_HISTORY_SOURCE_CHECKSUM, record_count=EXPECTED_MISARCHIVED_VOUCHER_COUNT,
    )
    import_batch = FinanceCenterMumarenKingdeeImportBatch(
        id=12, batch_key="three-books", manifest_checksum="b" * 64,
        validation_status="imported", expected_book_count=3, expected_voucher_count=339,
        expected_line_count=4596, expected_balance_snapshot_count=6868,
    )

    class ScalarResult:
        def __init__(self, value): self.value = value
        def scalar_one_or_none(self): return self.value
        def scalar_one(self): return self.value

    class Db:
        def __init__(self): self.statements = []
        async def execute(self, statement):
            query = str(statement)
            self.statements.append(query)
            if "kingdee_import_batches" in query: return ScalarResult(import_batch)
            if "finance_center_mumaren_books" in query: return ScalarResult(EXPECTED_REPLACEMENT_BOOK_COUNT)
            if "finance_center_mumaren_vouchers" in query: return ScalarResult(EXPECTED_REPLACEMENT_VOUCHER_COUNT)
            if "finance_center_mumaren_voucher_lines" in query: return ScalarResult(EXPECTED_REPLACEMENT_LINE_COUNT)
            if "finance_center_mumaren_balance_snapshots" in query: return ScalarResult(EXPECTED_REPLACEMENT_SNAPSHOT_COUNT)
            if "history_import_batches" in query and not query.lstrip().upper().startswith("DELETE"): return ScalarResult(history_batch)
            if "count" in query.lower(): return ScalarResult(EXPECTED_MISARCHIVED_VOUCHER_COUNT)
            if query.lstrip().upper().startswith("DELETE"): return ScalarResult(None)
            raise AssertionError(query)

    db = Db()
    result = await cleanup_misarchived_kingdee_history(
        db, KingdeeHistoryCleanupRequest(MISARCHIVED_HISTORY_SOURCE_BATCH_KEY, MISARCHIVED_HISTORY_SOURCE_CHECKSUM, "three-books", "b" * 64), execute=True,
    )

    deletes = [query for query in db.statements if query.lstrip().upper().startswith("DELETE")]
    assert result.status == "deleted"
    assert result.deleted_voucher_count == EXPECTED_MISARCHIVED_VOUCHER_COUNT
    assert len(deletes) == 2
    assert "finance_center_mumaren_history_vouchers" in deletes[0]
    assert "import_batch_id" in deletes[0]
    assert "finance_center_mumaren_history_import_batches" in deletes[1]
    assert "source_checksum" in deletes[1]


def test_cleanup_script_defaults_to_dry_run_and_never_mentions_legacy_or_source_tables():
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_misarchived_kingdee_history.py"
    source = script.read_text(encoding="utf-8")

    assert 'parser.add_argument("--execute", action="store_true"' in source
    assert 'parser.add_argument("--source-batch-key"' not in source
    assert 'parser.add_argument("--source-checksum"' not in source
    assert "MISARCHIVED_HISTORY_SOURCE_BATCH_KEY" in source
    assert "SET TRANSACTION READ ONLY" in source or "cleanup_misarchived_kingdee_history" in source
    assert "kingdee_finance" not in source
    assert "fin_history" not in source


def test_cleanup_service_uses_exact_history_batch_predicates_and_readonly_preview():
    from pathlib import Path

    service = Path(__file__).resolve().parents[1] / "app" / "services" / "mumaren_finance_center" / "kingdee_history_cleanup.py"
    source = service.read_text(encoding="utf-8")

    assert 'text("SET TRANSACTION READ ONLY")' in source
    assert 'source_system == "kingdee"' in source
    assert "source_batch_key == request.source_batch_key" in source
    assert "source_checksum == request.source_checksum" in source
    assert "manifest_checksum == request.kingdee_manifest_checksum" in source
    assert "EXPECTED_REPLACEMENT_VOUCHER_COUNT" in source
    assert "MISARCHIVED_HISTORY_SOURCE_BATCH_KEY" in source
    assert "kingdee_finance" not in source
    assert "fin_history" not in source
