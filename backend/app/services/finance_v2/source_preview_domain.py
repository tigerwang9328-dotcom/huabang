"""Pure dry-run projection for future source posting rules; never writes vouchers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PreviewRule:
    business_type: str
    version: str
    debit_account: str
    credit_account: str
    source_system: str | None = None
    legal_entity_code: str | None = None
    organization_code: str | None = None
    book_id: int | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    priority: int = 0
    status: str = "published"


@dataclass(frozen=True)
class SourcePreview:
    status: str
    rule_version: str | None
    entries: list[dict]
    creates_draft: bool
    exception_code: str | None = None


def _business_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _matches_scope(event: dict, rule: PreviewRule) -> bool:
    if rule.business_type != event.get("business_type") or rule.status != "published":
        return False
    event_date = _business_date(event.get("business_date"))
    if event_date is None and (rule.effective_from or rule.effective_to):
        return False
    if event_date is not None and rule.effective_from and event_date < rule.effective_from:
        return False
    if event_date is not None and rule.effective_to and event_date > rule.effective_to:
        return False
    for field in ("source_system", "legal_entity_code", "organization_code", "book_id"):
        expected = getattr(rule, field)
        if expected is not None and expected != event.get(field):
            return False
    return True


def _rule_sort_key(rule: PreviewRule) -> tuple[int, int]:
    scope_specificity = sum(
        value is not None
        for value in (rule.source_system, rule.legal_entity_code, rule.organization_code, rule.book_id)
    )
    return scope_specificity, rule.priority


def preview_source_event(event: dict, rules: list[PreviewRule]) -> SourcePreview:
    """Return a non-persistent accounting suggestion or explicit mapping exception."""

    candidates = [candidate for candidate in rules if _matches_scope(event, candidate)]
    if not candidates:
        return SourcePreview("pending_mapping", None, [], False, "missing_rule")
    top_key = max(_rule_sort_key(candidate) for candidate in candidates)
    matching_rules = [candidate for candidate in candidates if _rule_sort_key(candidate) == top_key]
    if len(matching_rules) != 1:
        return SourcePreview("pending_mapping", None, [], False, "ambiguous_rule")
    rule = matching_rules[0]
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
