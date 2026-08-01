"""自动凭证规则的纯领域规划。

规则只能形成草稿；审核和过账仍由既有凭证工作流人工完成。
"""
from decimal import Decimal
from typing import Mapping


class AutoVoucherRuleConfigurationError(ValueError):
    """规则不能安全地生成一张平衡草稿凭证。"""


def build_auto_voucher_draft(
    rule: Mapping[str, object], *, amount: Decimal | None, source_key: str,
) -> dict[str, object]:
    """将一个完整双分录规则转换为待审核的平衡草稿，不执行写入。"""
    debit_account_id = rule.get("debit_account_id")
    credit_account_id = rule.get("credit_account_id")
    if not isinstance(debit_account_id, int) or not isinstance(credit_account_id, int):
        raise AutoVoucherRuleConfigurationError("规则必须配置借方和贷方会计科目")
    if debit_account_id == credit_account_id:
        raise AutoVoucherRuleConfigurationError("借方和贷方会计科目不能相同")
    source_key = source_key.strip()
    if not source_key:
        raise AutoVoucherRuleConfigurationError("必须提供来源业务标识，用于防重复生成")
    if len(source_key) > 128:
        raise AutoVoucherRuleConfigurationError("来源业务标识不能超过128个字符")
    effective_amount = amount if amount is not None else rule.get("default_amount")
    try:
        effective_amount = Decimal(str(effective_amount))
    except Exception as exc:
        raise AutoVoucherRuleConfigurationError("规则未配置可用金额") from exc
    if effective_amount <= 0:
        raise AutoVoucherRuleConfigurationError("生成金额必须大于0")
    rule_id = rule.get("id")
    if not isinstance(rule_id, int):
        raise AutoVoucherRuleConfigurationError("规则标识无效")
    summary = str(rule.get("summary") or rule.get("rule_name") or "自动凭证草稿")
    return {
        "status": "draft",
        "source_key": f"auto-rule:{rule_id}:{source_key}",
        "summary": summary,
        "voucher_type": str(rule.get("voucher_type") or "记"),
        "amount": effective_amount,
        "lines": [
            {"account_id": debit_account_id, "summary": summary, "debit_amount": effective_amount, "credit_amount": Decimal("0")},
            {"account_id": credit_account_id, "summary": summary, "debit_amount": Decimal("0"), "credit_amount": effective_amount},
        ],
    }
