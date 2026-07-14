"""Read-only aggregation for LifeData advertising optimization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.life_data import LifeDataCapture, LifeDataCollectorState


_CANONICAL_ALIASES: dict[str, frozenset[str]] = {
    "plays": frozenset({"plays", "item_play_cnt", "item_total_play_cnt", "play_count"}),
    "spend_fen": frozenset({"spend_fen", "total_ad_cost", "current_ad_cost"}),
    "ad_orders": frozenset({"ad_orders", "order_cnt", "ad_order_cnt", "ad_pay_order_cnt", "total_ad_order_cnt", "current_ad_order_cnt"}),
    "ad_pay_gmv_fen": frozenset({"ad_pay_gmv_fen", "ad_pay_gmv", "total_ad_pay_gmv", "current_ad_pay_gmv"}),
    "pay_gmv_fen": frozenset({"pay_gmv_fen", "pay_gmv"}),
    "verified_gmv_fen": frozenset({"verified_gmv_fen", "verify_gmv", "verified_gmv"}),
    "verified_count": frozenset({"verify_cert_cnt", "verified_count"}),
    "refund_gmv_fen": frozenset({"refund_gmv_fen", "refund_gmv"}),
    "audience_age": frozenset({"audience_age", "age_name", "age_range", "age"}),
    "audience_gender": frozenset({"audience_gender", "gender", "gender_name", "sex"}),
    "region": frozenset({"city", "city_resident", "province_resident", "province", "region"}),
    "hour": frozenset({"hour", "hour_str", "stat_hour"}),
    "video_id": frozenset({"item_id", "video_id", "aweme_id"}),
    "campaign_id": frozenset({"campaign_id"}),
    "plan_id": frozenset({"plan_id"}),
    "creative_id": frozenset({"creative_id"}),
    "store_id": frozenset({"store_id"}),
    "stat_date": frozenset({"date_str", "stat_date"}),
}
_ALIAS_TO_CANONICAL = {
    alias.casefold(): canonical
    for canonical, aliases in _CANONICAL_ALIASES.items()
    for alias in aliases
}
_NUMERIC_FIELDS = frozenset({
    "plays", "spend_fen", "ad_orders", "ad_pay_gmv_fen", "pay_gmv_fen",
    "verified_gmv_fen", "verified_count", "refund_gmv_fen",
})
_REQUIRED_FIELDS = ["spend_fen", "verified_gmv_fen", "stat_date"]
_REQUIRED_ANALYSIS_FIELDS = ["attribution_quality"]
_GUIDANCE_PAGES = {
    "plays": "流量 → 视频分析",
    "spend_fen": "投放 → 广告分析",
    "ad_orders": "投放 → 广告分析",
    "ad_pay_gmv_fen": "投放 → 广告分析",
    "pay_gmv_fen": "经营 → 经营概览",
    "verified_gmv_fen": "经营 → 经营概览",
    "verified_count": "经营 → 经营概览",
    "refund_gmv_fen": "经营 → 经营概览",
    "audience_age": "人群分析",
    "audience_gender": "人群分析",
    "region": "地域分析",
    "hour": "时间趋势",
    "stat_date": "经营 → 经营概览",
}


def _valid_canonical_value(field: str, value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if field in _NUMERIC_FIELDS:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return False
        return number == number and number not in {float("inf"), float("-inf")}
    if field == "stat_date":
        return isinstance(value, str) and bool(value.strip())
    return isinstance(value, (str, int, float)) and str(value).strip() != ""


@dataclass
class _FieldOccurrence:
    value: Any
    path: str
    period: str | None
    response_period: bool


@dataclass
class _CaptureAnalysis:
    capture: Any
    request_period: str | None
    response_periods: set[str] = field(default_factory=set)
    effective_period: str | None = None
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    occurrences: dict[str, list[_FieldOccurrence]] = field(default_factory=dict)
    rows: list[Mapping[str, Any]] = field(default_factory=list)
    exact_link: bool = False


def _date_value(value: Any) -> str | None:
    return value if isinstance(value, str) and len(value) == 10 else None


def _local_period(value: Any, inherited: str | None) -> str | None:
    if not isinstance(value, Mapping):
        return inherited
    return _date_value(value.get("stat_date")) or _date_value(value.get("date_str")) or inherited


def _iter_json_entries(value: Any):
    if isinstance(value, Mapping):
        return iter(value.items()), False
    if isinstance(value, list):
        return enumerate(value), True
    return iter(()), False


def _scan_response(
    value: Any,
    *,
    request_period: str | None = None,
    max_depth: int = 40,
    max_nodes: int = 100_000,
    max_paths: int = 8,
) -> _CaptureAnalysis:
    analysis = _CaptureAnalysis(capture=None, request_period=request_period)
    if not isinstance(value, (Mapping, list)):
        return analysis
    root_period = _local_period(value, None)
    root_row_id = id(value) if isinstance(value, Mapping) else None
    stack = [(_iter_json_entries(value)[0], "$", 0, root_period, isinstance(value, list), root_row_id)]
    row_fields: dict[int, set[str]] = {}
    if isinstance(value, Mapping):
        analysis.rows.append(value)
        row_fields[id(value)] = set()
    visited = 0
    while stack and visited < max_nodes:
        iterator, path, depth, inherited_period, is_array, row_id = stack[-1]
        try:
            raw_key, child = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        visited += 1
        key = str(raw_key)
        child_path = f"{path}[{key}]" if is_array else f"{path}.{key}"
        canonical = None if is_array else _ALIAS_TO_CANONICAL.get(key.casefold())
        if canonical and _valid_canonical_value(canonical, child):
            if row_id is not None:
                row_fields[row_id].add(canonical)
            period = (
                _date_value(child)
                if canonical == "stat_date"
                else inherited_period or request_period
            )
            entry = analysis.fields.setdefault(canonical, {"paths": [], "count": 0})
            entry["count"] += 1
            if len(entry["paths"]) < max_paths:
                entry["paths"].append(child_path)
            analysis.occurrences.setdefault(canonical, []).append(
                _FieldOccurrence(
                    child,
                    child_path,
                    period,
                    canonical == "stat_date" or inherited_period is not None,
                )
            )
        if depth < max_depth and isinstance(child, (Mapping, list)):
            child_period = _local_period(child, inherited_period)
            if isinstance(child, Mapping):
                analysis.rows.append(child)
                row_fields[id(child)] = set()
            child_iterator, child_is_array = _iter_json_entries(child)
            child_row_id = id(child) if isinstance(child, Mapping) else None
            stack.append((child_iterator, child_path, depth + 1, child_period, child_is_array, child_row_id))
    for fields in row_fields.values():
        if (
            {"spend_fen", "verified_gmv_fen", "stat_date", "video_id"}.issubset(fields)
            and fields.intersection({"creative_id", "plan_id", "campaign_id"})
        ):
            analysis.exact_link = True
            break
    return analysis


def _scan_canonical_fields(
    value: Any,
    *,
    max_depth: int = 40,
    max_nodes: int = 100_000,
    max_paths: int = 8,
) -> dict[str, dict[str, Any]]:
    return _scan_response(
        value, max_depth=max_depth, max_nodes=max_nodes, max_paths=max_paths
    ).fields


def _walk(value: Any) -> Iterable[Mapping[str, Any]]:
    return iter(_scan_response(value).rows)


def _number(value: Any) -> int | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        number = float(value)
        return int(round(number)) if isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _capture_value(capture: Any, key: str, default: Any = None) -> Any:
    if isinstance(capture, Mapping):
        return capture.get(key, default)
    return getattr(capture, key, default)


def _period_end(capture: Any) -> str | None:
    request = _capture_value(capture, "request_payload", {})
    for row in _walk(request):
        value = row.get("end_date")
        if isinstance(value, str) and len(value) == 10:
            return value
    return None


def _latest_period_captures(captures: list[Any]) -> tuple[list[Any], str | None]:
    latest_end = max((_period_end(row) for row in captures if _period_end(row)), default=None)
    if latest_end is None:
        return captures, None
    anchors = [
        _capture_value(row, "captured_at")
        for row in captures
        if _period_end(row) == latest_end and isinstance(_capture_value(row, "captured_at"), datetime)
    ]
    anchor = max(anchors, default=None)
    selected = []
    for row in captures:
        end = _period_end(row)
        captured_at = _capture_value(row, "captured_at")
        if end == latest_end:
            selected.append(row)
        elif end is None and anchor and isinstance(captured_at, datetime):
            if abs((captured_at - anchor).total_seconds()) <= 300:
                selected.append(row)
    return selected, latest_end


def _analyze_capture(capture: Any) -> _CaptureAnalysis:
    request_period = _period_end(capture)
    analysis = _scan_response(
        _capture_value(capture, "response_payload", {}), request_period=request_period
    )
    analysis.capture = capture
    analysis.response_periods = {
        str(occurrence.value)
        for occurrence in analysis.occurrences.get("stat_date", [])
        if _date_value(occurrence.value)
    }
    if len(analysis.response_periods) == 1:
        analysis.effective_period = next(iter(analysis.response_periods))
    elif not analysis.response_periods:
        analysis.effective_period = request_period
    return analysis


def _latest_period_analyses(
    analyses: list[_CaptureAnalysis],
) -> tuple[list[_CaptureAnalysis], str | None]:
    def selection_period(analysis: _CaptureAnalysis) -> str | None:
        return max(analysis.response_periods) if analysis.response_periods else analysis.effective_period

    latest_period = max(
        (period for analysis in analyses if (period := selection_period(analysis))),
        default=None,
    )
    if latest_period is None:
        return analyses, None
    selected = [analysis for analysis in analyses if selection_period(analysis) == latest_period]
    anchors = [
        _capture_value(analysis.capture, "captured_at")
        for analysis in selected
        if isinstance(_capture_value(analysis.capture, "captured_at"), datetime)
    ]
    anchor = max(anchors, default=None)
    if anchor:
        selected_ids = {id(analysis) for analysis in selected}
        for analysis in analyses:
            captured_at = _capture_value(analysis.capture, "captured_at")
            if (
                id(analysis) not in selected_ids
                and isinstance(captured_at, datetime)
                and abs((captured_at - anchor).total_seconds()) <= 300
            ):
                if analysis.effective_period is None and not analysis.response_periods:
                    analysis.effective_period = latest_period
                selected.append(analysis)
    return selected, latest_period


def _field_sources(analyses: Iterable[_CaptureAnalysis]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, set[tuple[Any, ...]]] = {}
    for analysis in analyses:
        capture = analysis.capture
        for field_name in _CANONICAL_ALIASES:
            for occurrence in analysis.occurrences.get(field_name, []):
                source = {
                    "page_path": str(_capture_value(capture, "page_path", "")),
                    "endpoint": str(_capture_value(capture, "endpoint", "")),
                    "stat_end": occurrence.period,
                }
                marker = (source["page_path"], source["endpoint"], source["stat_end"])
                if marker in seen.setdefault(field_name, set()):
                    continue
                seen[field_name].add(marker)
                result.setdefault(field_name, []).append(source)
    return result


def _select_summary_metric(
    analyses: Iterable[_CaptureAnalysis], field_name: str
) -> tuple[int | None, str | None]:
    candidates: list[tuple[int, int, str | None]] = []
    for analysis in analyses:
        target_period = (
            max(analysis.response_periods)
            if analysis.response_periods
            else analysis.effective_period
        )
        for occurrence in analysis.occurrences.get(field_name, []):
            value = _number(occurrence.value)
            if value is None:
                continue
            if not occurrence.response_period:
                priority = 0
            elif occurrence.period == target_period:
                priority = 1
            else:
                priority = 2
            candidates.append((priority, value, occurrence.period or target_period))
    if not candidates:
        return None, None
    best_priority = min(candidate[0] for candidate in candidates)
    _, value, period = max(
        (candidate for candidate in candidates if candidate[0] == best_priority),
        key=lambda candidate: candidate[1],
    )
    return value, period


def _period_consistent(
    spend_metric: tuple[int | None, str | None],
    verified_metric: tuple[int | None, str | None],
) -> bool:
    spend_value, spend_period = spend_metric
    verified_value, verified_period = verified_metric
    if spend_value is None or verified_value is None:
        return True
    return bool(spend_period and verified_period and spend_period == verified_period)


def _attribution_quality(
    analyses: Iterable[_CaptureAnalysis],
    available_fields: set[str],
    period_consistent: bool,
) -> str:
    if not {"spend_fen", "verified_gmv_fen", "stat_date"}.issubset(available_fields):
        return "missing"
    if not period_consistent:
        return "missing"
    if any(analysis.exact_link for analysis in analyses):
        return "exact"
    return "period_estimate"


def _collection_guidance(missing: Iterable[str]) -> list[dict[str, str]]:
    return [
        {"field": field, "page": _GUIDANCE_PAGES[field], "action": "open_and_refresh"}
        for field in missing
        if field in _GUIDANCE_PAGES
    ]


def _ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator, 2)


def _demographics(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for row in rows:
        man = _number(row.get("man_ad_cost_1d"))
        woman = _number(row.get("woman_ad_cost_1d"))
        if man is None and woman is None:
            continue
        age = str(row.get("age_name") or row.get("age_range") or row.get("age") or "未标注")
        item = (age, man or 0, woman or 0)
        if item in seen:
            continue
        seen.add(item)
        result.append({"age": age, "male_cost_fen": man or 0, "female_cost_fen": woman or 0})
    return result


def _materials(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        cost = _number(row.get("current_ad_cost"))
        if cost is None:
            continue
        item_id = str(row.get("item_id") or row.get("video_id") or row.get("aweme_id") or "")
        title = str(row.get("item_title") or row.get("video_title") or row.get("title") or "未命名素材")
        key = item_id or f"{title}:{cost}"
        candidate = {
            "item_id": item_id, "title": title, "ad_cost_fen": cost,
            "ad_pay_gmv_fen": _number(row.get("current_ad_pay_gmv")) or 0,
            "play_count": _number(row.get("item_total_play_cnt") or row.get("item_play_cnt") or row.get("play_count")) or 0,
        }
        if key not in result or candidate["ad_cost_fen"] > result[key]["ad_cost_fen"]:
            result[key] = candidate
    return sorted(result.values(), key=lambda item: item["ad_cost_fen"], reverse=True)[:50]


def _regions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row.get("city_resident") or row.get("province_resident") or row.get("province")
        cost = _number(row.get("sub_ad_cost"))
        if not name or cost is None:
            continue
        candidate = {"name": str(name), "ad_cost_fen": cost, "cost_rate": float(row.get("sub_ad_cost_rate") or 0)}
        key = str(name)
        if key not in result or candidate["ad_cost_fen"] > result[key]["ad_cost_fen"]:
            result[key] = candidate
    return sorted(result.values(), key=lambda item: item["ad_cost_fen"], reverse=True)[:30]


def _trends(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        date = row.get("date_str") or row.get("date") or row.get("stat_date")
        cost = _number(row.get("total_ad_cost"))
        if not date or cost is None:
            continue
        candidate = {"date": str(date), "ad_cost_fen": cost, "ad_pay_gmv_fen": _number(row.get("total_ad_pay_gmv")) or 0}
        key = str(date)
        if key not in result or candidate["ad_cost_fen"] > result[key]["ad_cost_fen"]:
            result[key] = candidate
    return [result[key] for key in sorted(result)]


def _recommend(summary: Mapping[str, Any]) -> dict[str, Any]:
    roi = summary.get("verify_roi")
    evidence = [
        f"近7日消耗 ¥{summary['ad_cost_fen'] / 100:.2f}" if summary.get("ad_cost_fen") is not None else "缺少投放消耗",
        f"实际核销 ¥{summary['verify_gmv_fen'] / 100:.2f}" if summary.get("verify_gmv_fen") is not None else "缺少实际核销",
        f"退款 ¥{summary['refund_gmv_fen'] / 100:.2f}" if summary.get("refund_gmv_fen") is not None else "缺少退款",
    ]
    if roi is None:
        action, title = "collect_more_data", "先补齐消耗与核销数据"
        budget = None
        stop_loss = "未形成完整口径前不建议新增预算"
    elif roi >= 1.5:
        action, title = "increase_budget", "对高核销素材小步加投"
        budget = {"min_yuan": 100, "max_yuan": 300}
        stop_loss = "连续24小时核销ROI低于1.2时停止加投"
    elif roi >= 1.0:
        action, title = "maintain_and_observe", "维持预算并观察核销滞后"
        budget = {"min_yuan": 50, "max_yuan": 150}
        stop_loss = "连续24小时核销ROI低于0.9时降低预算"
    else:
        action, title = "reduce_and_observe", "降低无效消耗，只保留小额验证"
        budget = {"min_yuan": 30, "max_yuan": 80}
        stop_loss = "新增消耗100元仍无新增核销时停止"
    return {
        "action": action,
        "title": title,
        "budget": budget,
        "review_window_hours": 24,
        "stop_loss": stop_loss,
        "evidence": evidence,
        "confidence": "medium" if roi is not None else "low",
        "requires_human_confirm": True,
        "executed": False,
    }


def build_investment_overview(
    captures: Iterable[Any],
    snapshots: Iterable[Any],
    collector_state: Any,
) -> dict[str, Any]:
    all_captures = list(captures)
    all_analyses = [_analyze_capture(capture) for capture in all_captures]
    analyses, stat_end = _latest_period_analyses(all_analyses)
    captures = [analysis.capture for analysis in analyses]
    ad_rows = [
        row
        for analysis in analyses
        if "ad/analysis" in str(_capture_value(analysis.capture, "page_path", ""))
        for row in analysis.rows
    ]
    spend_metric = _select_summary_metric(analyses, "spend_fen")
    verified_metric = _select_summary_metric(analyses, "verified_gmv_fen")
    ad_cost = spend_metric[0]
    ad_pay = _select_summary_metric(analyses, "ad_pay_gmv_fen")[0]
    pay = _select_summary_metric(analyses, "pay_gmv_fen")[0]
    verify = verified_metric[0]
    refund = _select_summary_metric(analyses, "refund_gmv_fen")[0]
    verify_count = _select_summary_metric(analyses, "verified_count")[0]
    period_consistent = _period_consistent(spend_metric, verified_metric)
    summary = {
        "ad_cost_fen": ad_cost,
        "ad_pay_gmv_fen": ad_pay,
        "pay_gmv_fen": pay,
        "verify_gmv_fen": verify,
        "refund_gmv_fen": refund,
        "verify_cert_count": verify_count,
        "ad_pay_roi": _ratio(ad_pay, ad_cost) if period_consistent else None,
        "verify_roi": _ratio(verify, ad_cost) if period_consistent else None,
        "cost_per_verify_fen": round(ad_cost / verify_count) if ad_cost is not None and verify_count else None,
        "refund_rate": _ratio(refund, pay),
    }
    field_sources = _field_sources(analyses)
    available_fields = {field for field in _CANONICAL_ALIASES if field in field_sources}
    attribution_quality = _attribution_quality(analyses, available_fields, period_consistent)
    missing = [field for field in _REQUIRED_FIELDS if field not in available_fields]
    available_analysis_fields = [] if attribution_quality == "missing" else ["attribution_quality"]
    missing_analysis_fields = [
        field for field in _REQUIRED_ANALYSIS_FIELDS if field not in available_analysis_fields
    ]
    latest = max(
        (_capture_value(row, "captured_at") for row in captures if _capture_value(row, "captured_at")),
        default=None,
    )
    state_status = _capture_value(collector_state, "status", "offline") if collector_state else "offline"
    last_full_success_at = _capture_value(collector_state, "last_full_success_at") if collector_state else None
    return {
        "period": {"label": "近7日", "stat_end": stat_end, "latest_capture_at": latest.isoformat() if isinstance(latest, datetime) else latest},
        "collector": {
            "status": state_status,
            "template_count": _capture_value(collector_state, "template_count", 0) if collector_state else 0,
            "last_full_success_at": (
                last_full_success_at.isoformat()
                if isinstance(last_full_success_at, datetime)
                else last_full_success_at
            ),
            "groups": _capture_value(collector_state, "group_health", {}) if collector_state else {},
        },
        "summary": summary,
        "materials": _materials(ad_rows),
        "demographics": _demographics(ad_rows),
        "regions": _regions(ad_rows),
        "trends": _trends(ad_rows),
        "ai_recommendation": _recommend(summary),
        "data_quality": {
            "required_fields": _REQUIRED_FIELDS.copy(),
            "required_analysis_fields": _REQUIRED_ANALYSIS_FIELDS.copy(),
            "available_fields": [field for field in _CANONICAL_ALIASES if field in available_fields],
            "missing": missing,
            "available_analysis_fields": available_analysis_fields,
            "missing_analysis_fields": missing_analysis_fields,
            "field_sources": field_sources,
            "collection_guidance": _collection_guidance(missing),
            "attribution_quality": attribution_quality,
            "period_consistent": period_consistent,
            "is_estimated_verify_attribution": attribution_quality != "exact",
        },
    }


async def get_investment_overview(db: AsyncSession, account_id: str) -> dict[str, Any]:
    captures = (
        await db.execute(
            select(LifeDataCapture)
            .where(LifeDataCapture.account_id == account_id)
            .order_by(LifeDataCapture.captured_at.desc())
            .limit(300)
        )
    ).scalars().all()
    state = (
        await db.execute(
            select(LifeDataCollectorState).where(LifeDataCollectorState.account_id == account_id)
        )
    ).scalar_one_or_none()
    return build_investment_overview(captures, [], state)
