from dataclasses import dataclass
from decimal import Decimal

from app.services.finance_v2.report_readiness import (
    ReportMapping,
    ReportTemplate,
    build_report_readiness,
)


@dataclass(frozen=True)
class Balance:
    account_version_id: int
    closing_debit: Decimal
    closing_credit: Decimal


def _template(report_code: str, *, status: str = "published") -> ReportTemplate:
    return ReportTemplate(
        report_code=report_code,
        version_code="v1",
        status=status,
        line_codes=("assets", "liabilities_equity") if report_code == "balance_sheet" else ("revenue", "expense"),
    )


def test_formal_report_is_blocked_without_published_template_and_complete_mapping():
    result = build_report_readiness(
        report_code="balance_sheet",
        template=None,
        mappings=[],
        balances=[Balance(1, Decimal("100"), Decimal("0"))],
        formal_report_blocked=False,
        has_approved_coverage_gap=False,
    )

    assert result.status == "pending_mapping"
    assert result.formal_export_allowed is False
    assert result.reason_code == "missing_published_template"


def test_balance_sheet_readiness_rejects_an_unbalanced_mapping_output():
    result = build_report_readiness(
        report_code="balance_sheet",
        template=_template("balance_sheet"),
        mappings=[ReportMapping("assets", 1, Decimal("1")), ReportMapping("liabilities_equity", 2, Decimal("-1"))],
        balances=[Balance(1, Decimal("100"), Decimal("0")), Balance(2, Decimal("0"), Decimal("90"))],
        formal_report_blocked=False,
        has_approved_coverage_gap=False,
    )

    assert result.status == "pending_data"
    assert result.formal_export_allowed is False
    assert result.reason_code == "accounting_equation_mismatch"


def test_balance_sheet_readiness_rejects_a_template_without_the_required_equation_lines():
    result = build_report_readiness(
        report_code="balance_sheet",
        template=ReportTemplate("balance_sheet", "v1", "published", ("assets",)),
        mappings=[ReportMapping("assets", 1, Decimal("1"))],
        balances=[Balance(1, Decimal("100"), Decimal("0"))],
        formal_report_blocked=False,
        has_approved_coverage_gap=False,
    )

    assert result.status == "pending_mapping"
    assert result.reason_code == "incomplete_report_definition"


def test_balance_sheet_readiness_requires_no_coverage_gap_and_balanced_lines():
    result = build_report_readiness(
        report_code="balance_sheet",
        template=_template("balance_sheet"),
        mappings=[ReportMapping("assets", 1, Decimal("1")), ReportMapping("liabilities_equity", 2, Decimal("-1"))],
        balances=[Balance(1, Decimal("100"), Decimal("0")), Balance(2, Decimal("0"), Decimal("100"))],
        formal_report_blocked=False,
        has_approved_coverage_gap=True,
    )

    assert result.status == "pending_gap"
    assert result.formal_export_allowed is False
    assert result.reason_code == "approved_coverage_gap"


def test_profit_statement_readiness_returns_versioned_rows_without_allowing_export_while_book_is_blocked():
    result = build_report_readiness(
        report_code="profit_statement",
        template=_template("profit_statement"),
        mappings=[ReportMapping("revenue", 1, Decimal("-1")), ReportMapping("expense", 2, Decimal("1"))],
        balances=[Balance(1, Decimal("0"), Decimal("300")), Balance(2, Decimal("120"), Decimal("0"))],
        formal_report_blocked=True,
        has_approved_coverage_gap=False,
    )

    assert result.status == "blocked"
    assert result.formal_export_allowed is False
    assert result.rows == {"revenue": Decimal("300"), "expense": Decimal("120"), "net_profit": Decimal("180")}
