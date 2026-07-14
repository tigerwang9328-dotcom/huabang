from datetime import date
from pathlib import Path

from app.services.exception_rule_service import (
    build_evidence_hash,
    build_exception_unique_key,
    build_rule_version,
    normalize_rule_finding,
    rule_source_statuses,
)


REPO = Path(__file__).resolve().parents[2]


def test_evidence_hash_is_stable_for_equivalent_json():
    left = {"threshold": 0.15, "actual": 0.22, "documents": ["T1", "T2"]}
    right = {"documents": ["T1", "T2"], "actual": 0.22, "threshold": 0.15}

    assert build_evidence_hash(left) == build_evidence_hash(right)


def test_exception_unique_key_includes_subject_and_evidence():
    first = build_exception_unique_key(
        business_date=date(2026, 7, 13),
        rule_code="R004",
        subject_type="store",
        subject_id="285204",
        evidence_hash="abc",
    )
    duplicate = build_exception_unique_key(
        business_date=date(2026, 7, 13),
        rule_code="R004",
        subject_type="store",
        subject_id="285204",
        evidence_hash="abc",
    )
    changed = build_exception_unique_key(
        business_date=date(2026, 7, 13),
        rule_code="R004",
        subject_type="store",
        subject_id="285204",
        evidence_hash="def",
    )

    assert first == duplicate
    assert first != changed
    assert len(first) == 64


def test_rule_version_changes_when_thresholds_change():
    first = build_rule_version("R004", {"max_rate": 0.15}, "return-rate-v1")
    same = build_rule_version("R004", {"max_rate": 0.15}, "return-rate-v1")
    changed = build_rule_version("R004", {"max_rate": 0.2}, "return-rate-v1")

    assert first == same
    assert first != changed


def test_normalized_finding_keeps_evidence_source_and_pending_responsibility():
    finding = normalize_rule_finding(
        business_date=date(2026, 7, 13),
        finding={
            "rule_id": "R006",
            "rule_name": "负库存预警",
            "severity": "critical",
            "store_code": "gz002",
            "product_code": "SKU-PARENT",
            "title": "存在负库存",
            "evidence": {"negative_sku_count": 1},
            "suggestion": "复核出入库",
        },
        thresholds={"minimum": 0},
    )

    assert finding["rule_code"] == "R006"
    assert finding["subject_type"] == "product"
    assert finding["subject_id"] == "GZ002:SKU-PARENT"
    assert finding["source_name"] == "dws.dws_inventory_daily"
    assert finding["responsibility_status"] == "pending_data"
    assert finding["drilldown"]["route"] == "/app/inventory"
    assert finding["unique_key"]
    assert finding["evidence_hash"]


def test_rule_registry_covers_phase_two_sources_without_inventing_missing_data():
    statuses = rule_source_statuses()

    assert set(statuses) >= {
        "return",
        "amendment",
        "discount",
        "member",
        "vip_balance",
        "recharge",
        "transfer",
        "stocktake",
        "inventory",
        "responsibility",
    }
    assert statuses["amendment"]["status"] == "pending_data"
    assert statuses["stocktake"]["status"] == "pending_data"
    assert statuses["responsibility"]["status"] == "pending_data"


def test_migration_and_command_center_use_versioned_evidence_model():
    migration = (
        REPO / "backend" / "alembic" / "versions" / "0b8c9d0e1f2a_business_exception_evidence.py"
    ).read_text(encoding="utf-8")
    command_center = (
        REPO / "backend" / "app" / "services" / "command_center_service.py"
    ).read_text(encoding="utf-8")

    assert "dm_exception_evidence" in migration
    assert "dm_exception_rule_version" in migration
    assert "unique_key" in migration
    assert "evidence_hash" in migration
    assert "persist_rule_findings" in command_center
    assert "DELETE FROM dm.dm_exception_audit" not in command_center
    service = (
        REPO / "backend" / "app" / "services" / "exception_rule_service.py"
    ).read_text(encoding="utf-8")
    assert "rule_version='legacy'" in service


def test_audit_api_exposes_list_detail_status_and_rebuild_routes():
    source = (REPO / "backend" / "app" / "api" / "v1" / "audit.py").read_text(encoding="utf-8")

    assert '@router.get("/exceptions",' in source
    assert '@router.get("/exceptions/{exception_id}",' in source
    assert '@router.get("/rules/status",' in source
    assert '@router.post("/rebuild",' in source
