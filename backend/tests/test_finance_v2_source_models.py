from app.models.finance_v2_sources import (
    FinanceV2MappingException,
    FinanceV2PostingRule,
    FinanceV2PostingRuleVersion,
    FinanceV2PreviewRun,
    FinanceV2SourceDocument,
    FinanceV2SourceDocumentVersion,
    FinanceV2SourceInbox,
)


def test_source_preview_persistence_models_keep_document_identity_versions_rules_exceptions_and_runs_separate():
    assert {"source_system", "source_pk"} <= set(FinanceV2SourceDocument.__table__.columns.keys())
    assert {"source_document_id", "version_no", "source_hash", "payload"} <= set(FinanceV2SourceDocumentVersion.__table__.columns.keys())
    assert {"source_document_version_id", "status", "idempotency_key"} <= set(FinanceV2SourceInbox.__table__.columns.keys())
    assert {"source_system", "rule_code"} <= set(FinanceV2PostingRule.__table__.columns.keys())
    assert {"posting_rule_id", "version_code", "status", "effective_from", "priority"} <= set(FinanceV2PostingRuleVersion.__table__.columns.keys())
    assert {"source_inbox_id", "exception_code", "status"} <= set(FinanceV2MappingException.__table__.columns.keys())
    assert {"source_inbox_id", "posting_rule_version_id", "status", "result_payload"} <= set(FinanceV2PreviewRun.__table__.columns.keys())


def test_source_preview_models_are_current_finance_controls_not_history_facts():
    models = (
        FinanceV2SourceDocument,
        FinanceV2SourceDocumentVersion,
        FinanceV2SourceInbox,
        FinanceV2PostingRule,
        FinanceV2PostingRuleVersion,
        FinanceV2MappingException,
        FinanceV2PreviewRun,
    )

    assert {model.__table__.schema for model in models} == {"fin_current"}
