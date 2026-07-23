"""销售月报店铺级汇总（销售月度报表开发业务需求文档版）。"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

ZERO = Decimal("0")


def _q(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def calculate_actual_sales_cost(
    shipping_by_product: dict[str, dict], cost_map: dict[str, Decimal]
) -> tuple[Decimal, dict]:
    """实际销售成本 = Σ(发货订单按商品编码汇总的实发数量 × 成本价)。"""
    total = ZERO
    matched = 0
    missing: list[str] = []
    net_quantity_total = ZERO
    for product_code, quantities in shipping_by_product.items():
        net_qty = _q(quantities.get("net_shipped_quantity"))
        net_quantity_total += net_qty
        if product_code not in cost_map:
            if len(missing) < 10:
                missing.append(product_code)
            continue
        matched += 1
        total += net_qty * _q(cost_map[product_code])
    return total, {
        "product_code_count": len(shipping_by_product),
        "cost_matched_count": matched,
        "cost_missing_count": len(shipping_by_product) - matched,
        "cost_missing_samples": missing,
        "net_shipped_quantity_total": net_quantity_total,
        "actual_sales_cost": total,
        "formula": "Σ(商品编码实发数量 × 商品成本价)",
    }


def aggregate_shop_report(
    *,
    orders: Iterable[dict],
    actual_product_cost: Decimal = ZERO,
    platform_service_fee: Decimal = ZERO,
    talent_commission: Decimal = ZERO,
    freight_insurance: Decimal = ZERO,
    platform_other_fee: Decimal = ZERO,
    ad_cost: Decimal = ZERO,
    compensation_amount: Decimal = ZERO,
    small_payment_amount: Decimal = ZERO,
    customer_service_fee: Decimal = ZERO,
    management_fee: Decimal = ZERO,
    tax_fee: Decimal = ZERO,
    order_claim: Decimal = ZERO,
    deposit_recharge: Decimal = ZERO,
    rebate_amount: Decimal = ZERO,
    other_deduction: Decimal = ZERO,
    salary_fee: Decimal = ZERO,
    rent_utility_fee: Decimal = ZERO,
    other_monthly_expense: Decimal = ZERO,
    package_unit_cost: Decimal = Decimal("0.5"),
    goods_loss_unit_cost: Decimal = Decimal("1"),
    return_loss_enabled: bool = True,
) -> dict:
    """按三类主标签汇总销售月报；未发货退款独立计入发货前退款。"""
    rows = list(orders)
    shipped_mains: set[str] = set()
    refund_mains: set[str] = set()
    actual_sales_mains: set[str] = set()

    shipped_amount = ZERO
    after_ship_refund_amount = ZERO
    before_ship_refund_amount = ZERO
    after_settlement_refund_amount = ZERO
    actual_sales_amount = ZERO
    paid_sales_amount = ZERO
    freight_amount = ZERO

    for order in rows:
        main_no = order.get("main_order_no") or order.get("sub_order_no") or ""
        status = order.get("final_status")
        has_ship = order.get("ship_time") is not None
        payment = _q(order.get("settlement_income"))
        refund = _q(order.get("refund_amount"))
        receivable = _q(order.get("receivable_amount"))
        product_amount = _q(order.get("product_amount")) if order.get("product_amount") is not None else receivable

        if has_ship:
            if main_no:
                shipped_mains.add(main_no)
            shipped_amount += product_amount
            freight_amount += _q(order.get("matched_freight"))

        if payment > ZERO:
            paid_sales_amount += payment

        if status == "refunded":
            if main_no:
                refund_mains.add(main_no)
            refund_settlement_difference = (
                product_amount - _q(order.get("classification_settlement_amount"))
            )
            after_ship_refund_amount += refund_settlement_difference

        if status in ("paid", "pending_settlement") and main_no:
            actual_sales_mains.add(main_no)

        if status == "paid":
            after_settlement_refund_amount += _q(order.get("fund_refund_amount"))

        if not has_ship and order.get("order_status") == "已关闭":
            before_ship_refund_amount += receivable

    shipped_order_count = len(shipped_mains)
    refund_order_count = len(refund_mains)
    actual_sales_order_count = len(actual_sales_mains)
    actual_sales_order_completed = len(actual_sales_mains)
    actual_sales_amount = shipped_amount - after_ship_refund_amount
    avg_order_amount = (
        actual_sales_amount / Decimal(actual_sales_order_count)
        if actual_sales_order_count else ZERO
    )
    return_loss = Decimal(refund_order_count) if return_loss_enabled else ZERO
    package_fee = Decimal(shipped_order_count) * _q(package_unit_cost)
    goods_loss = Decimal(shipped_order_count) * _q(goods_loss_unit_cost)

    platform_service_fee_amount = _q(platform_service_fee).copy_abs()
    talent_commission_amount = _q(talent_commission).copy_abs()
    total_fee = (
        _q(actual_product_cost) + platform_service_fee_amount + talent_commission_amount
        + return_loss + freight_amount + package_fee + _q(freight_insurance)
        + _q(compensation_amount) + _q(small_payment_amount) + _q(platform_other_fee)
        + _q(customer_service_fee) + _q(ad_cost) + _q(management_fee) + _q(tax_fee)
    )
    gross_profit = actual_sales_amount - total_fee + _q(order_claim) - goods_loss
    net_profit = gross_profit + _q(rebate_amount) - _q(deposit_recharge) - _q(other_deduction)
    net_profit_rate = net_profit / actual_sales_amount if actual_sales_amount > ZERO else ZERO

    refund_numerator = (
        before_ship_refund_amount + after_ship_refund_amount + after_settlement_refund_amount
    )
    if paid_sales_amount > ZERO:
        total_refund_rate = refund_numerator / paid_sales_amount
        before_ship_refund_rate = before_ship_refund_amount / paid_sales_amount
        after_ship_refund_rate = after_ship_refund_amount / paid_sales_amount
        after_settlement_refund_rate = after_settlement_refund_amount / paid_sales_amount
    else:
        total_refund_rate = before_ship_refund_rate = ZERO
        after_ship_refund_rate = after_settlement_refund_rate = ZERO

    return {
        "shipped_order_count": shipped_order_count,
        "shipped_amount": shipped_amount,
        "refund_order_count": refund_order_count,
        "after_ship_refund_amount": after_ship_refund_amount,
        "before_ship_refund_amount": before_ship_refund_amount,
        "after_settlement_refund_amount": after_settlement_refund_amount,
        "actual_sales_amount": actual_sales_amount,
        "actual_sales_order_count": actual_sales_order_count,
        "actual_sales_order_completed": actual_sales_order_completed,
        "paid_sales_amount": paid_sales_amount,
        "avg_order_amount": avg_order_amount,
        "actual_product_cost": _q(actual_product_cost),
        "platform_service_fee": platform_service_fee_amount,
        "talent_commission": talent_commission_amount,
        "return_loss": return_loss,
        "freight_amount": freight_amount,
        "package_fee": package_fee,
        "freight_insurance": _q(freight_insurance),
        "compensation_amount": _q(compensation_amount),
        "small_payment_amount": _q(small_payment_amount),
        "platform_other_fee": _q(platform_other_fee),
        "customer_service_fee": _q(customer_service_fee),
        "ad_cost": _q(ad_cost),
        "management_fee": _q(management_fee),
        "salary_fee": _q(salary_fee),
        "rent_utility_fee": _q(rent_utility_fee),
        "other_monthly_expense": _q(other_monthly_expense),
        "tax_fee": _q(tax_fee),
        "total_fee": total_fee,
        "order_claim": _q(order_claim),
        "goods_loss": goods_loss,
        "gross_profit": gross_profit,
        "deposit_recharge": _q(deposit_recharge),
        "rebate_amount": _q(rebate_amount),
        "other_deduction": _q(other_deduction),
        "net_profit": net_profit,
        "net_profit_rate": net_profit_rate,
        "total_refund_rate": total_refund_rate,
        "before_ship_refund_rate": before_ship_refund_rate,
        "after_ship_refund_rate": after_ship_refund_rate,
        "after_settlement_refund_rate": after_settlement_refund_rate,
        "_diag_order_count": len(rows),
    }


MAX_MONEY_ABS = Decimal("10000000")
_ID_SANITY_BOUND = Decimal("100000000000000")
_CRITICAL_MONEY_FIELDS = ["freight_insurance", "total_fee", "gross_profit", "net_profit"]
_ALL_MONEY_FIELDS = [
    "shipped_amount", "after_ship_refund_amount", "before_ship_refund_amount",
    "after_settlement_refund_amount", "actual_sales_amount", "paid_sales_amount",
    "avg_order_amount", "actual_product_cost", "platform_service_fee", "talent_commission",
    "return_loss", "freight_amount", "package_fee", "freight_insurance",
    "compensation_amount", "small_payment_amount", "platform_other_fee",
    "customer_service_fee", "ad_cost", "management_fee", "tax_fee", "total_fee",
    "order_claim", "goods_loss", "gross_profit", "deposit_recharge", "rebate_amount",
    "other_deduction", "net_profit",
]


def validate_shop_report_values(report: dict, store_name: str | None = None) -> list[dict]:
    anomalies: list[dict] = []
    for field in _ALL_MONEY_FIELDS:
        if field not in report or report.get(field) is None:
            continue
        try:
            value = _q(report[field])
        except Exception:
            anomalies.append({"store_name": store_name, "field": field,
                              "value": str(report.get(field)), "threshold": "-"})
            continue
        threshold = MAX_MONEY_ABS if field in _CRITICAL_MONEY_FIELDS else _ID_SANITY_BOUND
        if value.copy_abs() > threshold:
            anomalies.append({"store_name": store_name, "field": field,
                              "value": str(value), "threshold": str(threshold)})
    return anomalies
