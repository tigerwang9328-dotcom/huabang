"""v4.0 report query service: outfit and single-garment rankings, plus export.

Synchronous query functions that aggregate from ``outfit_color_metrics`` and
``video_color_metrics`` tables. Designed to be called either directly with a
sync SQLAlchemy ``Session`` or via ``AsyncSession.run_sync`` from async routes.

Sample thresholds (v4.0 §ranking):
- ``>=3`` distinct videos per combination_key → enters average_retention ranking
- ``>=5`` distinct videos per combination_key → stdev (sample standard deviation, n-1) shown

Formula-injection escaping for CSV/XLSX export is delegated to
``douyin_color_export_service``.
"""

from __future__ import annotations

import io
import statistics
from typing import Any

from sqlalchemy import func as sa_func, select

from app.models.douyin_color_analytics import (
    OutfitColorMetric,
    VideoClip,
    VideoColorMetric,
)
from app.services.douyin_color_export_service import (
    build_export_metadata,
    escape_xlsx_cell,
    render_csv_row,
)


_DISCLAIMER = "本报告为历史关联性分析，不是因果结论"
_METRIC_VERSION = "v4.0"
_RANKING_SAMPLE_THRESHOLD = 3
_STDEV_SAMPLE_THRESHOLD = 5

# Ranking row column order for export.
_EXPORT_COLUMNS = (
    "combination_key",
    "average_retention",
    "stdev",
    "sample_count",
    "participant_count",
    "position_segment",
)


def _to_float(value: Any) -> float | None:
    """Coerce a Numeric/Decimal/None value to float for aggregation."""
    if value is None:
        return None
    return float(value)


def _aggregate_group(group: list, position_segment: str) -> dict | None:
    """Aggregate one combination_key group into a ranking row.

    Returns ``None`` when the group is below the ``_RANKING_SAMPLE_THRESHOLD``
    and should not enter the ranking.
    """
    sample_count = len(group)
    if sample_count < _RANKING_SAMPLE_THRESHOLD:
        return None
    retentions = [_to_float(m.average_retention) for m in group if m.average_retention is not None]
    avg_retention = sum(retentions) / len(retentions) if retentions else None
    stdev = None
    if sample_count >= _STDEV_SAMPLE_THRESHOLD and len(retentions) >= 2:
        stdev = statistics.stdev(retentions)
    segment = position_segment
    if segment == "all":
        segment = getattr(group[0], "dominant_position_segment", None) or "all"
    return {
        "average_retention": avg_retention,
        "stdev": stdev,
        "sample_count": sample_count,
        "position_segment": segment,
    }


def _count_excluded_clips(session, account_id: int) -> tuple[int, int]:
    """Return (multi_focus_count, unclear_count) for the account."""
    multi_focus = session.execute(
        select(sa_func.count()).select_from(VideoClip).where(
            VideoClip.account_id == account_id,
            VideoClip.focus_status == "multi_focus",
        )
    ).scalar() or 0
    unclear = session.execute(
        select(sa_func.count()).select_from(VideoClip).where(
            VideoClip.account_id == account_id,
            VideoClip.focus_status == "unclear",
        )
    ).scalar() or 0
    return multi_focus, unclear


def _source_data_cutoff(metrics: list) -> Any:
    """Return max(calculated_at) across metric rows, or None."""
    timestamps = [m.calculated_at for m in metrics if getattr(m, "calculated_at", None) is not None]
    return max(timestamps) if timestamps else None


def query_outfit_rankings(
    *,
    session,
    account_id: int,
    observation_window: str,
    position_segment: str = "all",
    as_of_date=None,
) -> dict:
    """Query whole-outfit rankings from ``outfit_color_metrics``.

    Aggregation dimension: ``combination_key``.
    Each row in ``outfit_color_metrics`` represents one video's outfit metric;
    the sample count for a combination_key equals the number of rows.
    """
    query = select(OutfitColorMetric).where(
        OutfitColorMetric.account_id == account_id,
        OutfitColorMetric.observation_window == observation_window,
    )
    if position_segment != "all":
        query = query.where(OutfitColorMetric.dominant_position_segment == position_segment)

    metrics = session.execute(query).scalars().all()

    groups: dict[str, list] = {}
    for m in metrics:
        groups.setdefault(m.combination_key, []).append(m)

    ranking_rows: list[dict] = []
    for combination_key, group in sorted(groups.items()):
        row = _aggregate_group(group, position_segment)
        if row is None:
            continue
        participant_count = max((getattr(m, "participant_count", 0) or 0) for m in group)
        ranking_rows.append({
            "combination_key": combination_key,
            "average_retention": row["average_retention"],
            "stdev": row["stdev"],
            "sample_count": row["sample_count"],
            "participant_count": participant_count,
            "position_segment": row["position_segment"],
        })

    ranking_rows.sort(key=lambda r: r["average_retention"] or 0.0, reverse=True)

    excluded_multi_focus, excluded_unclear = _count_excluded_clips(session, account_id)

    return {
        "ranking_rows": ranking_rows,
        "excluded_multi_focus_count": excluded_multi_focus,
        "excluded_unclear_count": excluded_unclear,
        "sample_count": len(metrics),
        "observation_window": observation_window,
        "position_segment": position_segment,
        "metric_version": _METRIC_VERSION,
        "source_data_cutoff_at": _source_data_cutoff(metrics),
        "disclaimer": _DISCLAIMER,
    }


def query_single_garment_rankings(
    *,
    session,
    account_id: int,
    ranking_bucket: str,
    observation_window: str,
    position_segment: str = "all",
    as_of_date=None,
) -> dict:
    """Query single-garment split rankings from ``video_color_metrics``.

    ``ranking_bucket``: ``"top"`` (outer + top) or ``"bottom"``.
    Aggregation dimension: ``style_id`` + ``sku_code``.
    """
    if ranking_bucket == "top":
        positions = ("outer", "top")
    elif ranking_bucket == "bottom":
        positions = ("bottom",)
    else:
        raise ValueError(f"invalid_ranking_bucket: {ranking_bucket}")

    query = select(VideoColorMetric).where(
        VideoColorMetric.account_id == account_id,
        VideoColorMetric.observation_window == observation_window,
        VideoColorMetric.garment_position.in_(positions),
    )
    if position_segment != "all":
        query = query.where(VideoColorMetric.dominant_position_segment == position_segment)

    metrics = session.execute(query).scalars().all()

    groups: dict[tuple, list] = {}
    for m in metrics:
        key = (m.style_id, m.sku_code)
        groups.setdefault(key, []).append(m)

    ranking_rows: list[dict] = []
    for (style_id, sku_code), group in sorted(groups.items(), key=lambda item: (item[0][0] or 0, item[0][1] or "")):
        row = _aggregate_group(group, position_segment)
        if row is None:
            continue
        combination_key = f"{style_id}:{sku_code or ''}"
        ranking_rows.append({
            "combination_key": combination_key,
            "average_retention": row["average_retention"],
            "stdev": row["stdev"],
            "sample_count": row["sample_count"],
            "participant_count": 1,
            "position_segment": row["position_segment"],
        })

    ranking_rows.sort(key=lambda r: r["average_retention"] or 0.0, reverse=True)

    excluded_multi_focus, excluded_unclear = _count_excluded_clips(session, account_id)

    return {
        "ranking_rows": ranking_rows,
        "excluded_multi_focus_count": excluded_multi_focus,
        "excluded_unclear_count": excluded_unclear,
        "sample_count": len(metrics),
        "observation_window": observation_window,
        "position_segment": position_segment,
        "metric_version": _METRIC_VERSION,
        "source_data_cutoff_at": _source_data_cutoff(metrics),
        "disclaimer": _DISCLAIMER,
    }


def export_rankings(*, rankings: dict, format: str, tab: str) -> dict:
    """Export rankings as CSV or XLSX with formula-injection prevention.

    ``format``: ``"csv"`` or ``"xlsx"``.
    ``tab``: ``"outfit"``, ``"top"``, or ``"bottom"``.
    Returns ``{content, filename, metadata}`` where ``content`` is a UTF-8 string.
    """
    rows = rankings.get("ranking_rows", [])
    metadata = build_export_metadata(
        account_name=str(rankings.get("account_id", "")),
        style_code=tab,
        style_name=tab,
        observation_window=str(rankings.get("observation_window", "")),
        position_segment=str(rankings.get("position_segment", "")),
        source_data_cutoff=str(rankings.get("source_data_cutoff_at", "")),
        metric_version=str(rankings.get("metric_version", "")),
        sample_count=int(rankings.get("sample_count", 0) or 0),
    )

    if format == "csv":
        output = io.StringIO()
        output.write(metadata + "\n")
        output.write(render_csv_row(_EXPORT_COLUMNS) + "\n")
        for row in rows:
            output.write(render_csv_row([row.get(col) for col in _EXPORT_COLUMNS]) + "\n")
        content = output.getvalue()
    elif format == "xlsx":
        output = io.StringIO()
        output.write(metadata + "\n")
        output.write(",".join(escape_xlsx_cell(col) for col in _EXPORT_COLUMNS) + "\n")
        for row in rows:
            output.write(",".join(
                escape_xlsx_cell("" if row.get(col) is None else str(row.get(col)))
                for col in _EXPORT_COLUMNS
            ) + "\n")
        content = output.getvalue()
    else:
        raise ValueError(f"unsupported_format: {format}")

    filename = f"douyin_color_{tab}_rankings.{format}"
    return {
        "content": content,
        "filename": filename,
        "metadata": metadata,
    }
