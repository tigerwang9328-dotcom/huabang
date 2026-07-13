"""Read-only aggregation for LifeData advertising optimization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.life_data import LifeDataCapture, LifeDataCollectorState


def _walk(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _number(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return None


def _max_metric(payloads: Iterable[Any], names: set[str]) -> int | None:
    values: list[int] = []
    for payload in payloads:
        for row in _walk(payload):
            for name in names:
                value = _number(row.get(name))
                if value is not None:
                    values.append(value)
    return max(values) if values else None


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


def _ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator, 2)


def _demographics(payloads: Iterable[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for payload in payloads:
        for row in _walk(payload):
            man = _number(row.get("man_ad_cost_1d"))
            woman = _number(row.get("woman_ad_cost_1d"))
            if man is None and woman is None:
                continue
            age = str(
                row.get("age_name")
                or row.get("age_range")
                or row.get("age")
                or "未标注"
            )
            item = (age, man or 0, woman or 0)
            if item in seen:
                continue
            seen.add(item)
            result.append({"age": age, "male_cost_fen": man or 0, "female_cost_fen": woman or 0})
    return result


def _materials(payloads: Iterable[Any]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in _walk(payload):
            cost = _number(row.get("current_ad_cost"))
            if cost is None:
                continue
            item_id = str(row.get("item_id") or row.get("video_id") or row.get("aweme_id") or "")
            title = str(row.get("item_title") or row.get("video_title") or row.get("title") or "未命名素材")
            key = item_id or f"{title}:{cost}"
            candidate = {
                "item_id": item_id,
                "title": title,
                "ad_cost_fen": cost,
                "ad_pay_gmv_fen": _number(row.get("current_ad_pay_gmv")) or 0,
                "play_count": _number(row.get("item_total_play_cnt") or row.get("item_play_cnt") or row.get("play_count")) or 0,
            }
            if key not in result or candidate["ad_cost_fen"] > result[key]["ad_cost_fen"]:
                result[key] = candidate
    return sorted(result.values(), key=lambda item: item["ad_cost_fen"], reverse=True)[:50]


def _regions(payloads: Iterable[Any]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in _walk(payload):
            name = row.get("city_resident") or row.get("province_resident") or row.get("province")
            cost = _number(row.get("sub_ad_cost"))
            if not name or cost is None:
                continue
            candidate = {
                "name": str(name),
                "ad_cost_fen": cost,
                "cost_rate": float(row.get("sub_ad_cost_rate") or 0),
            }
            key = str(name)
            if key not in result or candidate["ad_cost_fen"] > result[key]["ad_cost_fen"]:
                result[key] = candidate
    return sorted(result.values(), key=lambda item: item["ad_cost_fen"], reverse=True)[:30]


def _trends(payloads: Iterable[Any]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in _walk(payload):
            date = row.get("date_str") or row.get("date") or row.get("stat_date")
            cost = _number(row.get("total_ad_cost"))
            if not date or cost is None:
                continue
            candidate = {
                "date": str(date),
                "ad_cost_fen": cost,
                "ad_pay_gmv_fen": _number(row.get("total_ad_pay_gmv")) or 0,
            }
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
    captures, stat_end = _latest_period_captures(list(captures))
    ad_payloads = [
        _capture_value(row, "response_payload", {})
        for row in captures
        if "ad/analysis" in str(_capture_value(row, "page_path", ""))
    ]
    business_payloads = [
        _capture_value(row, "response_payload", {})
        for row in captures
        if str(_capture_value(row, "page_path", "")) in {"/dito/pc/business/page", "/trade/overview", "/flow/my/overview"}
    ]
    ad_cost = _max_metric(ad_payloads, {"total_ad_cost"})
    ad_pay = _max_metric(ad_payloads, {"total_ad_pay_gmv"})
    pay = _max_metric(business_payloads, {"pay_gmv"})
    verify = _max_metric(business_payloads, {"verify_gmv"})
    refund = _max_metric(business_payloads, {"refund_gmv"})
    verify_count = _max_metric(business_payloads, {"verify_cert_cnt"})
    summary = {
        "ad_cost_fen": ad_cost,
        "ad_pay_gmv_fen": ad_pay,
        "pay_gmv_fen": pay,
        "verify_gmv_fen": verify,
        "refund_gmv_fen": refund,
        "verify_cert_count": verify_count,
        "ad_pay_roi": _ratio(ad_pay, ad_cost),
        "verify_roi": _ratio(verify, ad_cost),
        "cost_per_verify_fen": round(ad_cost / verify_count) if ad_cost is not None and verify_count else None,
        "refund_rate": _ratio(refund, pay),
    }
    missing = []
    if ad_cost is None:
        missing.append("advertising_cost")
    if verify is None:
        missing.append("verified_gmv")
    latest = max(
        (_capture_value(row, "captured_at") for row in captures if _capture_value(row, "captured_at")),
        default=None,
    )
    state_status = _capture_value(collector_state, "status", "offline") if collector_state else "offline"
    return {
        "period": {"label": "近7日", "stat_end": stat_end, "latest_capture_at": latest.isoformat() if isinstance(latest, datetime) else latest},
        "collector": {"status": state_status},
        "summary": summary,
        "materials": _materials(ad_payloads),
        "demographics": _demographics(ad_payloads),
        "regions": _regions(ad_payloads),
        "trends": _trends(ad_payloads),
        "ai_recommendation": _recommend(summary),
        "data_quality": {"missing": missing, "is_estimated_verify_attribution": True},
    }


async def get_investment_overview(db: AsyncSession, account_id: str) -> dict[str, Any]:
    captures = (
        await db.execute(
            select(LifeDataCapture)
            .where(
                LifeDataCapture.account_id == account_id,
                LifeDataCapture.page_path.in_([
                    "/dito/pc/ad/analysis",
                    "/dito/pc/business/page",
                    "/trade/overview",
                    "/flow/my/overview",
                ]),
            )
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
