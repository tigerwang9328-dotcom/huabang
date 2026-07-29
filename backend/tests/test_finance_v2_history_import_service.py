from dataclasses import dataclass

from app.services.finance_v2.history_import_service import plan_history_import


@dataclass(frozen=True)
class _Record:
    source_pk: str
    source_hash: str


def test_history_import_plan_keeps_matching_sources_idempotent_and_stages_only_new_facts():
    plan = plan_history_import(
        [_Record("same", "same-hash"), _Record("new", "new-hash")],
        {"same": "same-hash"},
    )

    assert [record.source_pk for record in plan.new_records] == ["new"]
    assert plan.idempotent_source_pks == ("same",)
    assert plan.conflicts == ()


def test_history_import_plan_reports_changed_source_hash_without_planning_any_write():
    plan = plan_history_import(
        [_Record("changed", "new-hash")],
        {"changed": "old-hash"},
    )

    assert plan.new_records == ()
    assert plan.conflicts == (("changed", "old-hash", "new-hash"),)
