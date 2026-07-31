"""Task 6: safe CSV/XLSX export with formula injection prevention.

Covers v3.1 §3.4:
- CSV/XLSX export escapes formula injection (= + - @ prefixes)
- UTF-8 encoding
- Metadata: Asia/Shanghai time, account, style, color, window, position, cutoff, version, sample count
"""

import pytest

from app.services.douyin_color_export_service import (
    ExportError,
    escape_csv_cell,
    escape_xlsx_cell,
    build_export_metadata,
    render_csv_row,
)


def test_escape_csv_cell_prepends_quote_for_equal_sign():
    """Cells starting with = must be prefixed with single quote."""

    assert escape_csv_cell("=SUM(A1:A2)") == "'=SUM(A1:A2)"


def test_escape_csv_cell_prepends_quote_for_plus_minus_at():
    """Cells starting with +, -, @ must also be escaped."""

    assert escape_csv_cell("+cmd|/c calc") == "'+cmd|/c calc"
    assert escape_csv_cell("-1+1") == "'-1+1"
    assert escape_csv_cell("@SUM(A1)") == "'@SUM(A1)"


def test_escape_csv_cell_leaves_safe_values_unchanged():
    """Normal text and numbers are not modified."""

    assert escape_csv_cell("hello") == "hello"
    assert escape_csv_cell("0.5") == "0.5"
    assert escape_csv_cell("红色") == "红色"
    assert escape_csv_cell("") == ""


def test_escape_csv_cell_handles_none():
    """None values become empty string."""

    assert escape_csv_cell(None) == ""


def test_escape_xlsx_cell_prepends_quote_for_formula_prefixes():
    """XLSX cells also need formula injection prevention."""

    assert escape_xlsx_cell("=cmd|/c calc") == "'=cmd|/c calc"
    assert escape_xlsx_cell("+1") == "'+1"
    assert escape_xlsx_cell("-1") == "'-1"
    assert escape_xlsx_cell("@risk") == "'@risk"


def test_escape_xlsx_cell_leaves_safe_values_unchanged():
    assert escape_xlsx_cell("正常文本") == "正常文本"
    assert escape_xlsx_cell("0.123") == "0.123"


def test_render_csv_row_escapes_all_cells_and_quotes_commas():
    """CSV row rendering must escape formula injection and quote cells with commas."""

    row = render_csv_row(["=bad", "hello,world", "正常"])
    assert "'=bad" in row
    assert '"hello,world"' in row
    assert "正常" in row


def test_build_export_metadata_includes_required_fields():
    """Export metadata must include all v3.1 §3.4 required fields."""

    metadata = build_export_metadata(
        account_name="测试账号",
        style_code="WZ001",
        style_name="测试款",
        observation_window="t7",
        position_segment="all",
        source_data_cutoff="2026-07-31 00:00:00 (Asia/Shanghai)",
        metric_version="v1.0",
        sample_count=5,
    )
    assert "测试账号" in metadata
    assert "WZ001" in metadata
    assert "t7" in metadata
    assert "all" in metadata
    assert "Asia/Shanghai" in metadata
    assert "v1.0" in metadata
    assert "5" in metadata
    assert "历史关联" in metadata or "关联性" in metadata


def test_build_export_metadata_includes_correlation_disclaimer():
    """Metadata must include the 'correlation not causation' disclaimer."""

    metadata = build_export_metadata(
        account_name="x", style_code="x", style_name="x",
        observation_window="t7", position_segment="all",
        source_data_cutoff="x", metric_version="v1.0", sample_count=3,
    )
    assert "因果" in metadata or "causation" in metadata.lower() or "关联" in metadata
