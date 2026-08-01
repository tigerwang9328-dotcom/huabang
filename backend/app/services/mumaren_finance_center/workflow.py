"""凭证与历史记录的纯领域规则，不依赖华邦旧财务服务。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenAuditLog,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenHistoryVoucher,
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)


class InvalidVoucherTransition(ValueError):
    """凭证状态转换不符合人工审核/过账规则。"""


class UnbalancedVoucherError(ValueError):
    """凭证分录不符合借贷记账的基本约束。"""


class HistoricalRecordReadonlyError(ValueError):
    """历史来源数据不得进入当前账工作流或被修改。"""


def _amount(line: Mapping[str, object], key: str) -> Decimal:
    value = line.get(key, 0)
    return Decimal(str(value or 0))


def validate_voucher_lines(lines: Sequence[Mapping[str, object]]) -> tuple[Decimal, Decimal]:
    """验证每一行只能在借或贷一侧，且整张凭证借贷总额相等。"""
    if not lines:
        raise UnbalancedVoucherError("凭证至少需要一条分录")
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for line in lines:
        debit = _amount(line, "debit_amount")
        credit = _amount(line, "credit_amount")
        if debit < 0 or credit < 0:
            raise UnbalancedVoucherError("借贷金额不能为负数")
        if debit == 0 and credit == 0:
            raise UnbalancedVoucherError("每条分录必须填写借方或贷方金额")
        if debit > 0 and credit > 0:
            raise UnbalancedVoucherError("同一分录行不能同时填写借方和贷方金额")
        total_debit += debit
        total_credit += credit
    if total_debit != total_credit:
        raise UnbalancedVoucherError(f"借贷不平衡: 借方={total_debit}, 贷方={total_credit}")
    return total_debit, total_credit


def review_voucher(voucher: FinanceCenterMumarenVoucher, *, operator_id: int) -> None:
    """财务人员审核：只允许草稿进入已审核。"""
    if voucher.is_readonly:
        raise HistoricalRecordReadonlyError("历史迁移凭证只读，不能审核")
    if voucher.status != "draft":
        raise InvalidVoucherTransition(f"当前状态 {voucher.status}，无法审核")
    voucher.status = "reviewed"
    voucher.reviewed_by = operator_id
    voucher.reviewed_at = datetime.now(timezone.utc)


def post_voucher(voucher: FinanceCenterMumarenVoucher, *, operator_id: int) -> None:
    """人工过账：必须已经审核，领域层不提供自动过账入口。"""
    if voucher.is_readonly:
        raise HistoricalRecordReadonlyError("历史迁移凭证只读，不能人工过账")
    if voucher.status != "reviewed":
        raise InvalidVoucherTransition(f"当前状态 {voucher.status}，需先审核再人工过账")
    voucher.status = "posted"
    voucher.posted_by = operator_id
    voucher.posted_at = datetime.now(timezone.utc)


def assert_history_readonly(record: FinanceCenterMumarenHistoryVoucher) -> None:
    """历史金蝶记录是独立只读证据，禁止流入当前账修改/过账流程。"""
    if record.is_readonly and record.record_type == "historical":
        raise HistoricalRecordReadonlyError("历史数据只读，不能进入当前账工作流")


async def list_books(db: AsyncSession) -> list[FinanceCenterMumarenBook]:
    """列出新模块账簿；不访问华邦旧财务账套。"""
    result = await db.execute(select(FinanceCenterMumarenBook).order_by(FinanceCenterMumarenBook.id))
    return list(result.scalars())


async def list_accounts(db: AsyncSession, *, book_id: int) -> list[FinanceCenterMumarenAccount]:
    """列出指定新账簿的活动科目。"""
    result = await db.execute(
        select(FinanceCenterMumarenAccount)
        .where(
            FinanceCenterMumarenAccount.book_id == book_id,
            FinanceCenterMumarenAccount.is_active.is_(True),
        )
        .order_by(FinanceCenterMumarenAccount.account_code)
    )
    return list(result.scalars())


async def create_voucher(
    db: AsyncSession,
    *,
    book_id: int,
    voucher_no: str,
    voucher_date: str | date,
    lines: Sequence[Mapping[str, object]],
    operator_id: int,
    summary: str | None = None,
    voucher_type: str = "记",
) -> FinanceCenterMumarenVoucher:
    """创建草稿凭证，并在写入前强制验证借贷平衡。"""
    total_debit, total_credit = validate_voucher_lines(lines)
    for line_no, line in enumerate(lines, start=1):
        account_id = line.get("account_id")
        if not isinstance(account_id, int):
            raise ValueError(f"第{line_no}行缺少 account_id")
        account = (await db.execute(
            select(FinanceCenterMumarenAccount).where(
                FinanceCenterMumarenAccount.id == account_id,
                FinanceCenterMumarenAccount.book_id == book_id,
                FinanceCenterMumarenAccount.is_active.is_(True),
            )
        )).scalar_one_or_none()
        if account is None:
            raise ValueError(f"第{line_no}行会计科目不存在、不属于账簿或已停用")
    effective_date = date.fromisoformat(voucher_date) if isinstance(voucher_date, str) else voucher_date
    voucher = FinanceCenterMumarenVoucher(
        book_id=book_id,
        voucher_no=voucher_no,
        voucher_date=effective_date,
        summary=summary,
        voucher_type=voucher_type,
        status="draft",
        total_debit=total_debit,
        total_credit=total_credit,
        created_by=operator_id,
    )
    db.add(voucher)
    await db.flush()
    for line_no, line in enumerate(lines, start=1):
        account_id = line.get("account_id")
        db.add(
            FinanceCenterMumarenVoucherLine(
                voucher_id=voucher.id,
                line_no=line_no,
                account_id=account_id,
                summary=str(line["summary"]) if line.get("summary") is not None else None,
                debit_amount=_amount(line, "debit_amount"),
                credit_amount=_amount(line, "credit_amount"),
            )
        )
    db.add(
        FinanceCenterMumarenAuditLog(
            book_id=book_id,
            voucher_id=voucher.id,
            action="create_voucher",
            operator_id=operator_id,
            detail=voucher_no,
        )
    )
    return voucher


async def review_voucher_by_id(
    db: AsyncSession, *, voucher_id: int, operator_id: int
) -> FinanceCenterMumarenVoucher:
    """加载并审核草稿凭证，供 API 路由调用。"""
    voucher = await db.get(FinanceCenterMumarenVoucher, voucher_id)
    if voucher is None:
        raise LookupError("凭证不存在")
    review_voucher(voucher, operator_id=operator_id)
    db.add(FinanceCenterMumarenAuditLog(book_id=voucher.book_id, voucher_id=voucher.id, action="review_voucher", operator_id=operator_id, detail=voucher.voucher_no))
    return voucher


async def post_voucher_by_id(
    db: AsyncSession, *, voucher_id: int, operator_id: int
) -> FinanceCenterMumarenVoucher:
    """加载并人工过账已审核凭证；没有自动过账接口。"""
    voucher = await db.get(FinanceCenterMumarenVoucher, voucher_id)
    if voucher is None:
        raise LookupError("凭证不存在")
    post_voucher(voucher, operator_id=operator_id)
    db.add(FinanceCenterMumarenAuditLog(book_id=voucher.book_id, voucher_id=voucher.id, action="post_voucher", operator_id=operator_id, detail=voucher.voucher_no))
    return voucher


async def list_history_vouchers(
    db: AsyncSession, *, source_system: str | None = None, limit: int = 100
) -> list[FinanceCenterMumarenHistoryVoucher]:
    """读取独立历史区；返回记录必须保持只读标记。"""
    query = select(FinanceCenterMumarenHistoryVoucher).order_by(FinanceCenterMumarenHistoryVoucher.id.desc())
    if source_system:
        query = query.where(FinanceCenterMumarenHistoryVoucher.source_system == source_system)
    result = await db.execute(query.limit(min(max(limit, 1), 500)))
    return list(result.scalars())
