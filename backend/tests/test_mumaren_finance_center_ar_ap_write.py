"""AR/AP 独立写入 API 的 TDD 测试。

这些测试验证新模块在 ``finance_center_mumaren`` schema 内提供"草稿 →
财务审核 → 人工结算"的固定流程,且严格不产生任何凭证分录、不跨账簿关联
counterparty。所有用例只通过 mock Db 验证服务层行为,不触碰真实数据库。
"""
import os
from datetime import date
from decimal import Decimal

import pytest


os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenArApSettlement,
    FinanceCenterMumarenCounterparty,
    FinanceCenterMumarenPayableOrder,
    FinanceCenterMumarenReceivableOrder,
)


class _Result:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _MockDb:
    """记录所有 add/execute/flush 调用,用于断言不产生凭证分录。"""

    def __init__(self, *, counterparty=None, order=None):
        self.added = []
        self.counterparty = counterparty
        self.order = order
        self._next_id = 100

    async def execute(self, statement):
        text = str(statement)
        # counterparty lookup returns the configured counterparty (or None)
        if "finance_center_mumaren_counterparties" in text:
            return _Result(self.counterparty)
        # order lookup returns the configured order
        if "finance_center_mumaren_receivable_orders" in text or "finance_center_mumaren_payable_orders" in text:
            return _Result(self.order)
        return _Result(None)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                self._next_id += 1
                item.id = self._next_id

    async def get(self, model, primary_id):
        if model is FinanceCenterMumarenReceivableOrder and isinstance(self.order, FinanceCenterMumarenReceivableOrder):
            return self.order
        if model is FinanceCenterMumarenPayableOrder and isinstance(self.order, FinanceCenterMumarenPayableOrder):
            return self.order
        return None

    @property
    def voucher_entries(self):
        return [item for item in self.added if isinstance(item, (FinanceCenterMumarenVoucher, FinanceCenterMumarenVoucherLine))]


def _counterparty(book_id=1, cp_id=10, cp_type="customer"):
    return FinanceCenterMumarenCounterparty(
        id=cp_id, book_id=book_id, counterparty_type=cp_type,
        counterparty_code="C001", counterparty_name="客户甲", is_active=True,
    )


# ---------------------------------------------------------------------------
# SubTask 2.1: 创建 AR/AP 草稿
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_receivable_draft_persists_order_in_draft_status_without_voucher_entries():
    from app.services.mumaren_finance_center.ar_ap import create_ar_ap_order

    db = _MockDb(counterparty=_counterparty(book_id=1))
    order = await create_ar_ap_order(
        db,
        book_id=1,
        order_type="receivable",
        order_no="AR-2026-0001",
        order_date=date(2026, 7, 31),
        counterparty_id=10,
        counterparty_name="客户甲",
        total_amount=Decimal("1000.00"),
        operator_id=5,
    )

    assert isinstance(order, FinanceCenterMumarenReceivableOrder)
    assert order.book_id == 1
    assert order.workflow_status == "draft"
    assert order.settlement_status == "open"
    assert order.settled_amount == Decimal("0")
    assert order.total_amount == Decimal("1000.00")
    assert order.created_by == 5
    # 不产生任何凭证分录
    assert db.voucher_entries == []


@pytest.mark.asyncio
async def test_create_payable_draft_uses_payable_model():
    from app.services.mumaren_finance_center.ar_ap import create_ar_ap_order

    db = _MockDb(counterparty=_counterparty(book_id=2, cp_id=20, cp_type="supplier"))
    order = await create_ar_ap_order(
        db,
        book_id=2,
        order_type="payable",
        order_no="AP-2026-0001",
        order_date=date(2026, 7, 31),
        counterparty_id=20,
        counterparty_name="供应商乙",
        total_amount=Decimal("500.00"),
        operator_id=5,
    )

    assert isinstance(order, FinanceCenterMumarenPayableOrder)
    assert order.workflow_status == "draft"
    assert db.voucher_entries == []


# ---------------------------------------------------------------------------
# SubTask 2.2: 财务审核 AR/AP 单据
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_review_ar_ap_draft_transitions_to_reviewed_and_blocks_non_draft():
    from app.services.mumaren_finance_center.ar_ap import (
        InvalidOrderTransition,
        review_ar_ap_order,
    )

    order = FinanceCenterMumarenReceivableOrder(
        id=1, book_id=1, order_no="AR-1", order_date=date(2026, 7, 31),
        period="2026-07", counterparty_name="客户甲",
        total_amount=Decimal("100"), settled_amount=Decimal("0"),
        workflow_status="draft", settlement_status="open",
    )
    db = _MockDb(order=order)

    reviewed = await review_ar_ap_order(db, order_id=1, order_type="receivable", operator_id=7)
    assert reviewed.workflow_status == "reviewed"
    assert reviewed.reviewed_by == 7
    assert db.voucher_entries == []

    # 已审核再审核应被拒绝
    db2 = _MockDb(order=reviewed)
    with pytest.raises(InvalidOrderTransition):
        await review_ar_ap_order(db2, order_id=1, order_type="receivable", operator_id=7)


# ---------------------------------------------------------------------------
# SubTask 2.3: 人工结算 AR/AP 防超额
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settle_ar_ap_rejects_overpayment_and_updates_settlement_status():
    from app.services.mumaren_finance_center.ar_ap import (
        settle_ar_ap_order,
    )

    order = FinanceCenterMumarenReceivableOrder(
        id=1, book_id=1, order_no="AR-1", order_date=date(2026, 7, 31),
        period="2026-07", counterparty_name="客户甲",
        total_amount=Decimal("1000.00"), settled_amount=Decimal("800.00"),
        workflow_status="reviewed", settlement_status="partial",
    )
    # 超额结算应被拒绝
    db_over = _MockDb(order=order)
    with pytest.raises(ValueError, match="超过"):
        await settle_ar_ap_order(
            db_over, order_id=1, order_type="receivable",
            settlement_date=date(2026, 8, 5), amount=Decimal("300.00"), operator_id=8,
        )
    assert not any(isinstance(item, FinanceCenterMumarenArApSettlement) for item in db_over.added)

    # 正常部分结算
    db_ok = _MockDb(order=order)
    result = await settle_ar_ap_order(
        db_ok, order_id=1, order_type="receivable",
        settlement_date=date(2026, 8, 5), amount=Decimal("200.00"), operator_id=8,
    )
    assert order.settled_amount == Decimal("1000.00")
    assert order.settlement_status == "settled"
    settlements = [item for item in db_ok.added if isinstance(item, FinanceCenterMumarenArApSettlement)]
    assert len(settlements) == 1
    assert settlements[0].amount == Decimal("200.00")
    assert settlements[0].settlement_type == "receivable"
    assert settlements[0].voucher_id is None
    # 不产生凭证分录
    assert db_ok.voucher_entries == []


# ---------------------------------------------------------------------------
# SubTask 2.4: AR/AP 跨账簿 counterparty 校验
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_ar_ap_rejects_counterparty_from_another_book():
    from app.services.mumaren_finance_center.ar_ap import (
        CrossBookViolationError,
        create_ar_ap_order,
    )

    # counterparty 属于 book_id=2,但单据要写到 book_id=1
    db = _MockDb(counterparty=_counterparty(book_id=2, cp_id=10))
    with pytest.raises(CrossBookViolationError):
        await create_ar_ap_order(
            db,
            book_id=1,
            order_type="receivable",
            order_no="AR-X-1",
            order_date=date(2026, 7, 31),
            counterparty_id=10,
            counterparty_name="客户甲",
            total_amount=Decimal("100.00"),
            operator_id=5,
        )
    assert db.added == []


# ---------------------------------------------------------------------------
# SubTask 2.5: 校验新写入不产生任何凭证分录
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ar_ap_full_write_flow_never_creates_voucher_or_voucher_line():
    from app.services.mumaren_finance_center.ar_ap import (
        create_ar_ap_order,
        review_ar_ap_order,
        settle_ar_ap_order,
    )

    db = _MockDb(counterparty=_counterparty(book_id=1))
    order = await create_ar_ap_order(
        db, book_id=1, order_type="receivable", order_no="AR-FULL-1",
        order_date=date(2026, 7, 31), counterparty_id=10,
        counterparty_name="客户甲", total_amount=Decimal("200.00"), operator_id=5,
    )
    order.id = 1
    db.order = order
    await review_ar_ap_order(db, order_id=1, order_type="receivable", operator_id=7)
    await settle_ar_ap_order(
        db, order_id=1, order_type="receivable",
        settlement_date=date(2026, 8, 1), amount=Decimal("200.00"), operator_id=8,
    )

    # 整个流程不应产生任何凭证或分录对象
    assert db.voucher_entries == []
    # 不应引用旧财务表
    for item in db.added:
        assert "fin_" not in str(type(item).__table__.schema if hasattr(type(item), '__table__') else "")


@pytest.mark.asyncio
async def test_review_endpoint_uses_the_selected_order_type_when_ids_overlap():
    """A payable review must not inspect a same-ID receivable order first."""
    from app.api.v1.mumaren_finance_center_domains import review_ar_ap_order_endpoint

    receivable = FinanceCenterMumarenReceivableOrder(
        id=2, book_id=1, order_no="AR-2", order_date=date(2026, 8, 1),
        period="2026-08", counterparty_name="客户", total_amount=Decimal("100"),
        settled_amount=Decimal("0"), settlement_status="open", workflow_status="reviewed",
    )
    payable = FinanceCenterMumarenPayableOrder(
        id=2, book_id=1, order_no="AP-2", order_date=date(2026, 8, 1),
        period="2026-08", counterparty_name="供应商", total_amount=Decimal("100"),
        settled_amount=Decimal("0"), settlement_status="open", workflow_status="draft",
    )

    class CollisionDb(_MockDb):
        async def get(self, model, primary_id):
            return {
                FinanceCenterMumarenReceivableOrder: receivable,
                FinanceCenterMumarenPayableOrder: payable,
            }.get(model)

    result = await review_ar_ap_order_endpoint(
        order_id=2, order_type="payable", current_user=type("User", (), {"id": 7})(), db=CollisionDb(),
    )
    assert result.data["order_no"] == "AP-2"
    assert payable.workflow_status == "reviewed"


@pytest.mark.asyncio
async def test_settle_endpoint_uses_the_selected_order_type_when_ids_overlap():
    """A payable settlement must not settle a same-ID receivable order."""
    from app.api.v1.mumaren_finance_center_domains import ArApSettleInput, settle_ar_ap_order_endpoint

    receivable = FinanceCenterMumarenReceivableOrder(
        id=3, book_id=1, order_no="AR-3", order_date=date(2026, 8, 1),
        period="2026-08", counterparty_name="客户", total_amount=Decimal("100"),
        settled_amount=Decimal("0"), settlement_status="open", workflow_status="reviewed",
    )
    payable = FinanceCenterMumarenPayableOrder(
        id=3, book_id=1, order_no="AP-3", order_date=date(2026, 8, 1),
        period="2026-08", counterparty_name="供应商", total_amount=Decimal("100"),
        settled_amount=Decimal("0"), settlement_status="open", workflow_status="reviewed",
    )

    class CollisionDb(_MockDb):
        async def get(self, model, primary_id):
            return {
                FinanceCenterMumarenReceivableOrder: receivable,
                FinanceCenterMumarenPayableOrder: payable,
            }.get(model)

    result = await settle_ar_ap_order_endpoint(
        order_id=3, order_type="payable", body=ArApSettleInput(settlement_date=date(2026, 8, 1), amount=Decimal("100")),
        current_user=type("User", (), {"id": 7})(), db=CollisionDb(),
    )
    assert result.data["order_no"] == "AP-3"
    assert payable.settlement_status == "settled"
    assert receivable.settlement_status == "open"
