"""Pure dry-run projection for future source posting rules; never writes vouchers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PreviewRule:
    business_type: str
    version: str
    debit_account: str
    credit_account: str


@dataclass(frozen=True)
class SourcePreview:
    status: str
    rule_version: str | None
    entries: list[dict]
    creates_draft: bool
    exception_code: str | None = None


def preview_source_event(event: dict, rules: list[PreviewRule]) -> SourcePreview:
    """Return a non-persistent accounting suggestion or explicit mapping exception."""

    rule = next((candidate for candidate in rules if candidate.business_type == event.get("business_type")), None)
    if not rule:
        return SourcePreview("pending_mapping", None, [], False, "missing_rule")
    amount = Decimal(event.get("amount", "0"))
    if amount <= 0:
        return SourcePreview("pending_mapping", rule.version, [], False, "invalid_amount")
    return SourcePreview(
        "preview_ready",
        rule.version,
        [
            {"debit_account": rule.debit_account, "credit_account": rule.credit_account, "amount": amount},
        ],
        False,
    )
