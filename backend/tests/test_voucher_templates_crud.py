"""Task 9: 凭证模板 CRUD 路由测试(finance_center_mumaren_voucher_templates)。"""
import pytest
from fastapi import HTTPException

from mumaren_crud_helpers import _FakeUser, _MockDb, _MockResult

from app.api.v1.mumaren_finance_center_crud import (
    VoucherTemplateInput,
    VoucherTemplateUpdate,
    create_voucher_template,
    delete_voucher_template,
    list_voucher_templates,
    update_voucher_template,
)
from app.models.mumaren_finance_center_domains import FinanceCenterMumarenVoucherTemplate


def _template(*, tid=1, book_id=1, name="差旅费模板"):
    return FinanceCenterMumarenVoucherTemplate(
        id=tid, book_id=book_id, template_name=name,
        voucher_type="记", summary="差旅费摘要",
        lines_json={"lines": []}, created_by=5,
    )


@pytest.mark.asyncio
async def test_create_voucher_template_persists_and_writes_audit_log():
    db = _MockDb()
    user = _FakeUser(user_id=7)
    res = await create_voucher_template(
        body=VoucherTemplateInput(
            book_id=1, template_name="差旅费模板", voucher_type="记",
            summary="差旅费摘要", lines_json={"lines": []},
        ),
        current_user=user, db=db,
    )
    assert res.data["template_name"] == "差旅费模板"
    assert res.data["voucher_type"] == "记"
    logs = db.audit_logs("create_voucher_template")
    assert len(logs) == 1
    assert logs[0].book_id == 1
    assert logs[0].operator_id == 7


@pytest.mark.asyncio
async def test_list_voucher_templates_returns_rows_bounded_by_limit():
    rows = [_template(tid=1), _template(tid=2, name="招待费模板")]
    db = _MockDb(execute_results=[_MockResult(scalars=rows)])
    res = await list_voucher_templates(book_id=1, limit=100, _=_FakeUser(), db=db)
    assert res.success
    assert len(res.data) == 2
    assert res.data[0]["template_name"] == "差旅费模板"


@pytest.mark.asyncio
async def test_update_voucher_template_rejects_cross_book_and_writes_audit_log():
    tpl = _template(tid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenVoucherTemplate: {1: tpl}})
    with pytest.raises(HTTPException) as exc:
        await update_voucher_template(
            template_id=1, body=VoucherTemplateUpdate(book_id=2, template_name="新名"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 400
    assert db.audit_logs() == []

    tpl2 = _template(tid=1, book_id=1)
    db2 = _MockDb(get_map={FinanceCenterMumarenVoucherTemplate: {1: tpl2}})
    updated = await update_voucher_template(
        template_id=1, body=VoucherTemplateUpdate(book_id=1, template_name="新名"),
        current_user=_FakeUser(user_id=8), db=db2,
    )
    assert updated.data["template_name"] == "新名"
    assert len(db2.audit_logs("update_voucher_template")) == 1


@pytest.mark.asyncio
async def test_update_voucher_template_returns_404_when_missing():
    db = _MockDb(get_map={FinanceCenterMumarenVoucherTemplate: {}})
    with pytest.raises(HTTPException) as exc:
        await update_voucher_template(
            template_id=999, body=VoucherTemplateUpdate(book_id=1, template_name="x"),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_voucher_template_writes_audit_log_and_rejects_cross_book():
    tpl = _template(tid=1, book_id=1)
    db = _MockDb(get_map={FinanceCenterMumarenVoucherTemplate: {1: tpl}})
    res = await delete_voucher_template(template_id=1, book_id=1, current_user=_FakeUser(user_id=9), db=db)
    assert res.success
    assert len(db.deleted) == 1
    assert len(db.audit_logs("delete_voucher_template")) == 1

    tpl2 = _template(tid=2, book_id=1)
    db2 = _MockDb(get_map={FinanceCenterMumarenVoucherTemplate: {2: tpl2}})
    with pytest.raises(HTTPException) as exc:
        await delete_voucher_template(template_id=2, book_id=99, current_user=_FakeUser(), db=db2)
    assert exc.value.status_code == 400
