"""销售月报订单分类标签（2026-06 业务需求版）。"""
from __future__ import annotations

from decimal import Decimal

_EPS = Decimal("0.01")
RULES_VERSION = "销售月报三类标签局部修订-2026-06-28"

STATUS_LABELS = {
    "paid": "已收款",
    "refunded": "已退款",
    "pending_settlement": "待结算",
}


def _d(ctx: dict, key: str) -> Decimal:
    value = ctx.get(key)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _eq(left: Decimal, right: Decimal) -> bool:
    return (left - right).copy_abs() <= _EPS


def _zero(value: Decimal) -> bool:
    return value.copy_abs() <= _EPS


def _after_sale(ctx: dict) -> str:
    return str(ctx.get("after_sale_status") or "-").strip() or "-"


def determine_status(ctx: dict) -> tuple[str | None, str]:
    """按发货时间→订单状态→售后状态→金额生成三类互斥主标签。"""
    if not ctx.get("ship_time"):
        ctx["matched_rule_code"] = "unshipped"
        return None, "发货时间为空，不进入三类已发货订单标签；仅参与发货前退款指标判断"

    order_status = str(ctx.get("order_status") or "").strip()
    after_sale = _after_sale(ctx)
    settlement = (_d(ctx, "classification_settlement_amount")
                  if "classification_settlement_amount" in ctx
                  else _d(ctx, "settlement_amount_total"))
    receivable = _d(ctx, "receivable_amount")

    # 财务特例：已关闭且退款成功时，正向结算为运费结算，仍属于已退款。
    if order_status == "已关闭" and after_sale == "退款成功":
        ctx["matched_rule_code"] = "refunded_rule_1"
        return "refunded", "已退款1：订单已关闭且退款成功（含运费结算特例）"

    # 已收款：已完成全额/部分结算，或已关闭退款成功但部分结算。
    if order_status == "已完成" and _eq(settlement, receivable):
        ctx["matched_rule_code"] = "paid_rule_1"
        return "paid", "已收款1：订单已完成，结算金额等于应收金额"
    if order_status == "已完成" and settlement > 0 and settlement < receivable:
        ctx["matched_rule_code"] = "paid_rule_2"
        return "paid", "已收款2：订单已完成，结算金额大于0且小于应收金额"
    # 已确认的冲突处理：明确的待结算售后组合优先于“已完成+结算为0”通用已退款规则。
    pending_after_sales = ("-", "售后关闭", "售后已拒绝")
    if order_status == "已发货" and after_sale in pending_after_sales and _zero(settlement):
        ctx["matched_rule_code"] = "pending_rule_1"
        return "pending_settlement", "待结算1：订单已发货，售后为-/售后关闭/售后已拒绝，结算金额为0"
    if order_status == "已完成" and after_sale in pending_after_sales and _zero(settlement):
        ctx["matched_rule_code"] = "pending_rule_2"
        return "pending_settlement", "待结算2：订单已完成，售后为-/售后关闭/售后已拒绝，结算金额为0"

    # 已退款2：其他已完成且结算金额为0的订单。
    if order_status == "已完成" and _zero(settlement):
        ctx["matched_rule_code"] = "refunded_rule_2"
        return "refunded", "已退款2：订单已完成，结算金额为0"

    ctx["matched_rule_code"] = "unclassified"
    return None, "未命中本轮规定的三类订单分类标签"
