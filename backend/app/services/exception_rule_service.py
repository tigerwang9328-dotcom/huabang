"""Versioned, evidence-backed business exception persistence and querying."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.store_whitelist import ALLOWED_INVENTORY_CODES
from app.services.rule_engine import RuleEngine


RULE_SOURCES: dict[str, dict[str, str]] = {
    "return": {"status": "pending_data", "source": "baison_return", "reason": "可靠退货明细待接入"},
    "amendment": {"status": "pending_data", "source": "baison_ticket_change", "reason": "改单前后值待接入"},
    "discount": {"status": "ready", "source": "dws.dws_store_daily", "reason": "按已同步销售折扣判断"},
    "member": {"status": "ready", "source": "dim.dim_member", "reason": "会员主档已接入"},
    "vip_balance": {"status": "ready", "source": "dim.dim_member.CZ_DQJE", "reason": "按当前主档余额判断"},
    "recharge": {"status": "ready", "source": "dwd.dwd_store_recharge_daily", "reason": "门店日充值已接入，会员级明细待分层阶段使用"},
    "transfer": {"status": "ready", "source": "dwd.dwd_baison_transfer_inbound", "reason": "调拨入库单已接入"},
    "stocktake": {"status": "pending_data", "source": "baison_stocktake", "reason": "盘点单据待接入"},
    "inventory": {"status": "ready", "source": "dws.dws_inventory_daily", "reason": "外穿衣物统一库存已接入"},
    "responsibility": {"status": "pending_data", "source": "assignment", "reason": "导购、店长和平台归属尚无可靠来源"},
}


RULE_SOURCE_BY_CODE = {
    "R001": ("dws.dws_store_daily", "/app/store"),
    "R002": ("dws.dws_store_daily", "/app/store"),
    "R003": ("dws.dws_store_daily", "/app/dashboard"),
    "R004": ("baison_return", "/app/store"),
    "R005": ("dws.dws_store_daily", "/app/store"),
    "R006": ("dws.dws_inventory_daily", "/app/inventory"),
    "R007": ("dws.dws_inventory_daily", "/app/inventory"),
    "R008": ("dws.dws_inventory_daily", "/app/inventory"),
    "R009": ("dwd.v_apparel_inventory_snapshot", "/app/product/size-wall"),
    "R010": ("dws.dws_inventory_daily", "/app/inventory"),
    "R011": ("dm.dm_boss_daily_report", "/app/finance"),
    "R012": ("dm.dm_finance_profit_daily", "/app/finance"),
    "R013": ("app.app_action_task", "/app/task"),
    "R014": ("app.app_action_task", "/app/task"),
    "R015": ("dm.dm_boss_daily_report", "/app/report"),
    "VIP_NEGATIVE_BALANCE": ("dim.dim_member", "/app/member"),
}


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    raise TypeError(f"unsupported evidence value: {type(value)!r}")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def build_evidence_hash(evidence: Any) -> str:
    return hashlib.sha256(_canonical_json(evidence).encode("utf-8")).hexdigest()


def build_exception_unique_key(
    *, business_date: date, rule_code: str, subject_type: str, subject_id: str, evidence_hash: str
) -> str:
    raw = "|".join((str(business_date), rule_code.upper(), subject_type, subject_id, evidence_hash))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_rule_version(rule_code: str, thresholds: dict[str, Any], definition_marker: str) -> str:
    digest = build_evidence_hash({
        "rule_code": rule_code.upper(),
        "thresholds": thresholds,
        "definition": definition_marker,
    })
    return f"v-{digest[:12]}"


def rule_source_statuses() -> dict[str, dict[str, str]]:
    return {key: dict(value) for key, value in RULE_SOURCES.items()}


def _subject(finding: dict[str, Any]) -> tuple[str, str]:
    store = str(finding.get("store_code") or "").upper()
    if finding.get("member_no"):
        return "member", str(finding["member_no"])
    if finding.get("sku_code"):
        return "sku", f"{store}:{finding['sku_code']}" if store else str(finding["sku_code"])
    if finding.get("product_code"):
        return "product", f"{store}:{finding['product_code']}" if store else str(finding["product_code"])
    if finding.get("order_no"):
        return "transaction", str(finding["order_no"])
    if store:
        return "store", store
    return "company", "ALL"


def normalize_rule_finding(
    *, business_date: date, finding: dict[str, Any], thresholds: dict[str, Any] | None = None
) -> dict[str, Any]:
    rule_code = str(finding.get("rule_id") or finding.get("rule_code") or "UNKNOWN").upper()
    thresholds = thresholds or {}
    subject_type, subject_id = _subject(finding)
    source_name, route = RULE_SOURCE_BY_CODE.get(rule_code, (str(finding.get("source_name") or "rule_engine"), "/app/warning"))
    evidence = {
        "facts": finding.get("evidence") or {},
        "thresholds": thresholds,
        "suggestion": finding.get("suggestion") or "",
        "rule_name": finding.get("rule_name") or rule_code,
    }
    evidence_hash = build_evidence_hash(evidence)
    rule_version = build_rule_version(rule_code, thresholds, str(finding.get("definition_marker") or rule_code))
    store_code = str(finding.get("store_code") or "").upper() or None
    drilldown = {
        "route": route,
        "params": {
            key: value for key, value in {
                "store_code": store_code,
                "product_code": finding.get("product_code"),
                "sku_code": finding.get("sku_code"),
                "member_no": finding.get("member_no"),
                "order_no": finding.get("order_no"),
                "date": str(business_date),
            }.items() if value is not None
        },
    }
    return {
        "audit_date": business_date,
        "exception_type": str(finding.get("exception_type") or f"rule_{rule_code.lower()}"),
        "rule_code": rule_code,
        "rule_name": str(finding.get("rule_name") or rule_code),
        "rule_version": rule_version,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "evidence_hash": evidence_hash,
        "unique_key": build_exception_unique_key(
            business_date=business_date,
            rule_code=rule_code,
            subject_type=subject_type,
            subject_id=subject_id,
            evidence_hash=evidence_hash,
        ),
        "severity": str(finding.get("severity") or "warning"),
        "store_code": store_code,
        "product_code": finding.get("product_code"),
        "sku_code": finding.get("sku_code"),
        "order_no": finding.get("order_no"),
        "description": str(finding.get("title") or finding.get("description") or "触发业务异常"),
        "data_snapshot": evidence,
        "thresholds": thresholds,
        "metric_status": str(finding.get("metric_status") or "ready"),
        "source_name": source_name,
        "source_updated_at": finding.get("source_updated_at"),
        "drilldown": drilldown,
        "responsibility_status": "ready" if finding.get("responsibility_confirmed") else "pending_data",
        "evidence_records": finding.get("evidence_records") or [{
            "source_table": source_name,
            "record_key": str(finding.get("order_no") or subject_id),
            "source_record_id": str(finding.get("source_record_id") or subject_id),
            "document_no": finding.get("order_no"),
            "source_fields": finding.get("evidence") or {},
            "source_updated_at": finding.get("source_updated_at"),
        }],
    }


async def _load_thresholds(db: AsyncSession, rule_codes: list[str]) -> dict[str, dict[str, Any]]:
    if not rule_codes:
        return {}
    rows = (await db.execute(text("""
        SELECT rule_id, thresholds FROM app.app_business_rule_config
        WHERE rule_id=ANY(:rule_codes)
    """), {"rule_codes": rule_codes})).mappings().all()
    return {str(row["rule_id"]).upper(): row["thresholds"] or {} for row in rows}


async def _load_source_timestamps(db: AsyncSession, business_date: date) -> dict[str, Any]:
    row = (await db.execute(text("""
        SELECT
          (SELECT MAX(etl_at) FROM dws.dws_store_daily WHERE stat_date=:business_date) sales_updated_at,
          (SELECT MAX(etl_at) FROM dws.dws_inventory_daily WHERE stat_date=:business_date) inventory_updated_at,
          (SELECT MAX(balance_updated_at) FROM dim.dim_member
           WHERE UPPER(register_store)=ANY(:codes) AND COALESCE(status,'active')='active') member_updated_at,
          (SELECT MAX(updated_at) FROM dwd.dwd_store_recharge_daily WHERE biz_date=:business_date) recharge_updated_at,
          (SELECT MAX(synced_at) FROM dwd.dwd_baison_transfer_inbound WHERE record_date<=:business_date) transfer_updated_at,
          (SELECT MAX(updated_at) FROM app.app_action_task WHERE is_deleted=false) task_updated_at,
          (SELECT MAX(generated_at) FROM dm.dm_boss_daily_report WHERE report_date=:business_date) report_updated_at
    """), {
        "business_date": business_date,
        "codes": sorted(ALLOWED_INVENTORY_CODES),
    })).mappings().one()
    return {
        "dws.dws_store_daily": row["sales_updated_at"],
        "dws.dws_inventory_daily": row["inventory_updated_at"],
        "dwd.v_apparel_inventory_snapshot": row["inventory_updated_at"],
        "dim.dim_member": row["member_updated_at"],
        "dim.dim_member.CZ_DQJE": row["member_updated_at"],
        "dwd.dwd_store_recharge_daily": row["recharge_updated_at"],
        "dwd.dwd_baison_transfer_inbound": row["transfer_updated_at"],
        "app.app_action_task": row["task_updated_at"],
        "dm.dm_boss_daily_report": row["report_updated_at"],
    }


async def persist_rule_findings(
    db: AsyncSession, business_date: date, findings: list[dict[str, Any]]
) -> int:
    triggered = [item for item in findings if item.get("triggered", True)]
    thresholds_by_rule = await _load_thresholds(
        db, sorted({str(item.get("rule_id") or item.get("rule_code") or "UNKNOWN").upper() for item in triggered})
    )
    source_timestamps = await _load_source_timestamps(db, business_date) if triggered else {}
    persisted = 0
    for finding in triggered:
        rule_code = str(finding.get("rule_id") or finding.get("rule_code") or "UNKNOWN").upper()
        source_name = RULE_SOURCE_BY_CODE.get(rule_code, (str(finding.get("source_name") or "rule_engine"), "/app/warning"))[0]
        if not finding.get("source_updated_at") and source_timestamps.get(source_name):
            finding = {**finding, "source_updated_at": source_timestamps[source_name]}
        normalized = normalize_rule_finding(
            business_date=business_date,
            finding=finding,
            thresholds=thresholds_by_rule.get(rule_code, finding.get("thresholds") or {}),
        )
        await db.execute(text("""
            INSERT INTO dm.dm_exception_rule_version(
                rule_code, version, rule_name, thresholds, definition_hash, source_status
            ) VALUES (
                :rule_code, :rule_version, :rule_name, CAST(:thresholds AS jsonb),
                :definition_hash, :metric_status
            ) ON CONFLICT(rule_code, version) DO NOTHING
        """), {
            **normalized,
            "thresholds": _canonical_json(normalized["thresholds"]),
            "definition_hash": normalized["rule_version"].removeprefix("v-"),
        })
        exception_params = {
            **normalized,
            "data_snapshot": _canonical_json(normalized["data_snapshot"]),
            "thresholds": _canonical_json(normalized["thresholds"]),
            "drilldown": _canonical_json(normalized["drilldown"]),
        }
        legacy_id = (await db.execute(text("""
            SELECT id FROM dm.dm_exception_audit
            WHERE audit_date=:audit_date AND exception_type=:exception_type
              AND store_code IS NOT DISTINCT FROM :store_code
              AND description=:description AND rule_version='legacy'
            ORDER BY id DESC LIMIT 1
        """), exception_params)).scalar()
        if legacy_id:
            row = (await db.execute(text("""
                UPDATE dm.dm_exception_audit SET
                    rule_code=:rule_code, rule_version=:rule_version,
                    subject_type=:subject_type, subject_id=:subject_id,
                    evidence_hash=:evidence_hash, unique_key=:unique_key,
                    severity=:severity, product_code=:product_code, sku_code=:sku_code,
                    order_no=:order_no, data_snapshot=CAST(:data_snapshot AS jsonb),
                    thresholds=CAST(:thresholds AS jsonb), metric_status=:metric_status,
                    source_name=:source_name, source_updated_at=:source_updated_at,
                    drilldown=CAST(:drilldown AS jsonb), responsibility_status=:responsibility_status,
                    generated_at=now()
                WHERE id=:legacy_id RETURNING id
            """), {**exception_params, "legacy_id": legacy_id})).mappings().one()
        else:
            row = (await db.execute(text("""
                INSERT INTO dm.dm_exception_audit(
                    audit_date, exception_type, rule_code, rule_version, subject_type, subject_id,
                    evidence_hash, unique_key, severity, store_code, product_code, sku_code, order_no,
                    description, data_snapshot, thresholds, metric_status, source_name,
                    source_updated_at, drilldown, responsibility_status, is_reviewed,
                    is_converted_to_task, generated_at
                ) VALUES (
                    :audit_date, :exception_type, :rule_code, :rule_version, :subject_type, :subject_id,
                    :evidence_hash, :unique_key, :severity, :store_code, :product_code, :sku_code, :order_no,
                    :description, CAST(:data_snapshot AS jsonb), CAST(:thresholds AS jsonb), :metric_status,
                    :source_name, :source_updated_at, CAST(:drilldown AS jsonb), :responsibility_status,
                    false, false, now()
                ) ON CONFLICT(unique_key) DO UPDATE SET
                    severity=EXCLUDED.severity,
                    description=EXCLUDED.description,
                    source_updated_at=COALESCE(EXCLUDED.source_updated_at, dm.dm_exception_audit.source_updated_at),
                    generated_at=now()
                RETURNING id
            """), exception_params)).mappings().one()
        exception_id = int(row["id"])
        for record in normalized["evidence_records"]:
            record_hash = build_evidence_hash(record.get("source_fields") or {})
            await db.execute(text("""
                INSERT INTO dm.dm_exception_evidence(
                    exception_id, source_table, record_key, source_record_id, document_no,
                    before_value, after_value, source_fields, evidence_hash, source_updated_at
                ) VALUES (
                    :exception_id, :source_table, :record_key, :source_record_id, :document_no,
                    CAST(:before_value AS jsonb), CAST(:after_value AS jsonb),
                    CAST(:source_fields AS jsonb), :evidence_hash, :source_updated_at
                ) ON CONFLICT(exception_id, source_table, record_key, evidence_hash) DO NOTHING
            """), {
                "exception_id": exception_id,
                "source_table": record["source_table"],
                "record_key": record["record_key"],
                "source_record_id": record.get("source_record_id"),
                "document_no": record.get("document_no"),
                "before_value": _canonical_json(record.get("before_value")) if record.get("before_value") is not None else None,
                "after_value": _canonical_json(record.get("after_value")) if record.get("after_value") is not None else None,
                "source_fields": _canonical_json(record.get("source_fields") or {}),
                "evidence_hash": record_hash,
                "source_updated_at": record.get("source_updated_at"),
            })
        persisted += 1
    return persisted


async def _vip_balance_findings(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (await db.execute(text("""
        SELECT member_no, UPPER(register_store) store_code, current_balance, balance_updated_at
        FROM dim.dim_member
        WHERE UPPER(register_store)=ANY(:codes)
          AND COALESCE(status,'active')='active' AND current_balance<0
    """), {"codes": sorted(ALLOWED_INVENTORY_CODES)})).mappings().all()
    return [{
        "rule_code": "VIP_NEGATIVE_BALANCE",
        "rule_name": "VIP负余额异常",
        "exception_type": "vip_negative_balance",
        "severity": "critical",
        "member_no": row["member_no"],
        "store_code": row["store_code"],
        "title": f"会员{row['member_no']}存在负余额，请复核会员主档和交易流水",
        "evidence": {"current_balance": row["current_balance"]},
        "source_updated_at": row["balance_updated_at"],
        "source_record_id": row["member_no"],
        "suggestion": "核对充值、消费和退款流水，不与正余额抵消",
    } for row in rows]


async def rebuild_exception_rules(db: AsyncSession, business_date: date) -> dict[str, Any]:
    engine = RuleEngine()
    result = await engine.run_all(str(business_date), db)
    findings = [item for item in result["results"] if item.get("triggered")]
    findings.extend(await _vip_balance_findings(db))
    persisted = await persist_rule_findings(db, business_date, findings)
    return {
        "business_date": str(business_date),
        "finding_count": len(findings),
        "persisted_count": persisted,
        "source_statuses": rule_source_statuses(),
    }
