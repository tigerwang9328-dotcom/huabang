"""Deterministic, read-only readiness checks for versioned Finance V2 reports.

This module deliberately does not create a statutory report.  It projects a
single versioned mapping over the current ledger and makes every missing
template, mapping, coverage, or accounting-equation condition explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Protocol


class LedgerBalance(Protocol):
    account_version_id: int
    closing_debit: Decimal
    closing_credit: Decimal


@dataclass(frozen=True)
class ReportTemplate:
    report_code: str
    version_code: str
    status: str
    line_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReportMapping:
    line_code: str
    account_version_id: int
    multiplier: Decimal


@dataclass(frozen=True)
class ReportReadiness:
    status: str
    reason_code: str | None
    formal_export_allowed: bool
    template_version: str | None
    rows: dict[str, Decimal]
    unmapped_account_version_ids: tuple[int, ...]


def _blocked(
    *,
    status: str,
    reason_code: str,
    template: ReportTemplate | None,
    rows: dict[str, Decimal],
    unmapped_account_version_ids: Iterable[int] = (),
) -> ReportReadiness:
    return ReportReadiness(
        status=status,
        reason_code=reason_code,
        formal_export_allowed=False,
        template_version=template.version_code if template else None,
        rows=rows,
        unmapped_account_version_ids=tuple(sorted(set(unmapped_account_version_ids))),
    )


def build_report_readiness(
    *,
    report_code: str,
    template: ReportTemplate | None,
    mappings: Iterable[ReportMapping],
    balances: Iterable[LedgerBalance],
    formal_report_blocked: bool,
    has_approved_coverage_gap: bool,
) -> ReportReadiness:
    """Project current-ledger balances and tell callers whether export is safe.

    `multiplier` is part of the approved report-mapping version.  It prevents
    code from guessing whether a credit-normal account should render positive
    on a particular statement line.
    """

    if template is None or template.status != "published" or template.report_code != report_code:
        return _blocked(
            status="pending_mapping",
            reason_code="missing_published_template",
            template=template,
            rows={},
        )

    required_lines = {
        "balance_sheet": {"assets", "liabilities_equity"},
        "profit_statement": {"revenue", "expense"},
    }.get(report_code, set())
    mapping_rows = list(mappings)
    template_lines = set(template.line_codes)
    if len(template_lines) != len(template.line_codes) or not required_lines.issubset(template_lines):
        return _blocked(
            status="pending_mapping",
            reason_code="incomplete_report_definition",
            template=template,
            rows={},
        )
    mappings_by_account: dict[int, list[ReportMapping]] = {}
    mapped_line_codes: set[str] = set()
    for mapping in mapping_rows:
        if mapping.line_code not in template_lines:
            continue
        mappings_by_account.setdefault(mapping.account_version_id, []).append(mapping)
        mapped_line_codes.add(mapping.line_code)

    balances = list(balances)
    unmapped = [row.account_version_id for row in balances if row.account_version_id not in mappings_by_account]
    if unmapped or mapped_line_codes != template_lines:
        return _blocked(
            status="pending_mapping",
            reason_code="incomplete_account_mapping",
            template=template,
            rows={},
            unmapped_account_version_ids=unmapped,
        )

    rows = {line_code: Decimal("0") for line_code in template.line_codes}
    for balance in balances:
        amount = Decimal(balance.closing_debit) - Decimal(balance.closing_credit)
        for mapping in mappings_by_account[balance.account_version_id]:
            rows[mapping.line_code] += amount * Decimal(mapping.multiplier)

    if report_code == "profit_statement":
        rows["net_profit"] = rows.get("revenue", Decimal("0")) - rows.get("expense", Decimal("0"))

    if report_code == "balance_sheet":
        assets = rows.get("assets", Decimal("0"))
        liabilities_equity = rows.get("liabilities_equity", Decimal("0"))
        if assets != liabilities_equity:
            return _blocked(
                status="pending_data",
                reason_code="accounting_equation_mismatch",
                template=template,
                rows=rows,
            )

    if has_approved_coverage_gap:
        return _blocked(
            status="pending_gap",
            reason_code="approved_coverage_gap",
            template=template,
            rows=rows,
        )
    if formal_report_blocked:
        return _blocked(
            status="blocked",
            reason_code="book_formal_report_blocked",
            template=template,
            rows=rows,
        )
    return ReportReadiness(
        status="ready",
        reason_code=None,
        formal_export_allowed=True,
        template_version=template.version_code,
        rows=rows,
        unmapped_account_version_ids=(),
    )
