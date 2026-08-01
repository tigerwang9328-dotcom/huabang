"""Task 10: 自动凭证规则 CRUD 路由测试(finance_center_mumaren_auto_voucher_rules)。"""
import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_crud import (
    AutoVoucherRuleInput,
    AutoVoucherRuleUpdate,
    create_auto_voucher_rule,
    delete_auto_voucher_rule,
    list_auto_voucher_rules,
    update_auto_voucher_rule,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenAutoVoucherRule


def _rule(*, rid=1, book_id=1, name="销售收款规则", is_active=True):
    return FinanceCenterMumarenAutoVoucherRule(
        id=rid, book_id=book_id, rule_name=name,
        trigger_event="sale_settled", account_id=10,
        direction="debit", amount_formula="order.total_amount",
        is_active=is_active, created_by=5,
    )


@pytest.mark.asyncio
async def test_create_auto_voucher_rule_persists_and_writes_audit_log():
    db = _MockDb()
    user = _FakeUser(user_id=7)
    res = await create_auto_voucher_rule(
        body=AutoVoucherRuleInput(
            book_id=1, rule_name="销售收款规则", trigger_event="sale_settled",
            account_id=10, direction="debit", amount_formula="order.total_amount",
        ),
        current_user=user, db=db,
    )
    assert res.data["rule_name"] == "销售收款规则"
    assert res.data["is_active"] is True
    logs = db.audit_logs("create_auto_voucher_rule")
    assert len(logs) == 1
    assert logs[0].book_id == 1
    assert logs[0].operator_id == 7


@pytest.mark.asyncio
async def test_list_auto_voucher_rules_returns_rows_bounded_by_limit():
    rows = [_rule(rid=1), _rule(rid=2, name="采购付款规则")]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_auto_voucher_rules(book_id=1, limit=100, _=_FakeUser(), db=db)
    assert res.success
    assert len(res.data) == 2


@pytest.mark.asyncio
async def test_update_auto_voucher_rule_rejects_cross_book_and_writes_audit_log():
    rule = _rule(rid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenAutoVoucherRule: {1: rule}})
    with pytest.raises(HTTPException) as exc:
        await update_auto_voucher_rule(
            rule_id=1, body=AutoVoucherRuleUpdate(book_id=2, rule_name="新名"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400
    assert db.audit_logs() == []

    rule2 = _rule(rid=1, book_id=1)
    db2 = _MockDb(get_map={FinanceCenterMumarenAutoVoucherRule: {1: rule2}})
    updated = await update_auto_voucher_rule(
        rule_id=1, body=AutoVoucherRuleUpdate(book_id=1, rule_name="新名", is_active=False),
        current_user=_FakeUser(user_id=8), db=db2,
    )
    assert updated.data["rule_name"] == "新名"
    assert updated.data["is_active"] is False
    assert len(db2.audit_logs("update_auto_voucher_rule")) == 1


@pytest.mark.asyncio
async def test_update_auto_voucher_rule_returns_404_when_missing():
    db = _MockDb(get_map={FinanceCenterMumarenAutoVoucherRule: {}})
    with pytest.raises(HTTPException) as exc:
        await update_auto_voucher_rule(
            rule_id=999, body=AutoVoucherRuleUpdate(book_id=1, rule_name="x"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_auto_voucher_rule_writes_audit_log_and_rejects_cross_book():
    rule = _rule(rid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenAutoVoucherRule: {1: rule}})
    res = await delete_auto_voucher_rule(rule_id=1, book_id=1, current_user=_FakeUser(user_id=9), db=db)
    assert res.success
    assert len(db.deleted) == 1
    assert len(db.audit_logs("delete_auto_voucher_rule")) == 1

    rule2 = _rule(rid=2, book_id=1)
    db2 = _MockDb(get_map={FinanceCenterMumarenAutoVoucherRule: {2: rule2}})
    with pytest.raises(HTTPException) as exc:
        await delete_auto_voucher_rule(rule_id=2, book_id=99, current_user=_FakeUser(), db=db2)
    assert exc.value.status_code == 400
