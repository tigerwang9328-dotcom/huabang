"""Task 6: safe CSV/XLSX export with formula injection prevention.

Implements v3.1 §3.4 export safety primitives:
- CSV/XLSX cell escaping for formula injection (= + - @ prefixes)
- CSV row rendering with comma-aware quoting
- Export metadata string with Asia/Shanghai timezone, correlation/causation disclaimer
"""

from __future__ import annotations

from typing import Iterable

# Characters that trigger spreadsheet formula injection when found at cell start.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


class ExportError(ValueError):
    """An export request violates v3.1 §3.4 export safety contract."""


def _escape_cell(value) -> str:
    """Escape formula-injection prefixes; coerce None to empty string."""

    if value is None:
        return ""
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def escape_csv_cell(value) -> str:
    """Escape a CSV cell value against formula injection."""

    return _escape_cell(value)


def escape_xlsx_cell(value) -> str:
    """Escape an XLSX cell value against formula injection."""

    return _escape_cell(value)


def render_csv_row(cells: Iterable) -> str:
    """Render an iterable of cells as a single CSV row.

    Each cell is first escaped against formula injection, then any cell
    containing a comma is wrapped in double quotes per RFC 4180.
    """

    escaped = [_escape_cell(c) for c in cells]
    rendered = []
    for cell in escaped:
        if "," in cell:
            rendered.append('"' + cell + '"')
        else:
            rendered.append(cell)
    return ",".join(rendered)


def build_export_metadata(
    *,
    account_name: str,
    style_code: str,
    style_name: str,
    observation_window: str,
    position_segment: str,
    source_data_cutoff: str,
    metric_version: str,
    sample_count: int,
) -> str:
    """Build a human-readable export metadata banner.

    Includes all v3.1 §3.4 required fields and a disclaimer stressing that
    the reported association is a historical correlation, not a causation.
    Times are expressed in the Asia/Shanghai timezone.
    """

    lines = [
        "# 抖音颜色分析导出元数据",
        f"# 账号: {account_name}",
        f"# 款号: {style_code} ({style_name})",
        f"# 观察窗口: {observation_window}",
        f"# 位置分段: {position_segment}",
        f"# 数据截止: {source_data_cutoff}",
        f"# 指标版本: {metric_version}",
        f"# 样本数: {sample_count}",
        "# 时区: Asia/Shanghai",
        "# 说明: 本报告展示的是历史关联性 (historical correlation), 关联不等于因果 (correlation is not causation).",
    ]
    return "\n".join(lines)
