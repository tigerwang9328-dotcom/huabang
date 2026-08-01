"""牧马人财务中心独立税务台账计算与写入服务。

写入路径只持久化到 ``finance_center_mumaren`` schema 的税务表,绝不创建
凭证或分录,也不调用华邦旧财务服务。固定流程为"草稿 → 财务审核 →
人工缴税",且缴税前强制校验同一账簿与防超额。
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenTaxRecord,
    FinanceCenterMumarenTaxType,
)
from app.services.mumaren_finance_center.workflow import assert_book_writable


class InvalidTaxTransition(ValueError):
    """税务单据状态转换不符合"草稿 → 审核 → 缴税"规则。"""


class CrossBookTaxViolationError(ValueError):
    """关联的 tax type 属于其他账簿,禁止跨账簿写入。"""


def _amount(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def tax_record_balance(tax_amount: Any, paid_amount: Any) -> Decimal:
    tax, paid = _amount(tax_amount), _amount(paid_amount)
    if tax < 0 or paid < 0 or paid > tax:
        raise ValueError("税务实缴金额无效")
    return tax - paid


async def create_tax_type(
    db: AsyncSession, *, book_id: int, tax_code: str, tax_name: str,
    default_rate: Any, operator_id: int, tax_category: str | None = None,
) -> FinanceCenterMumarenTaxType:
    """Create a tax type only for a writable current book."""
    await assert_book_writable(db, book_id=book_id)
    code, name = tax_code.strip().upper(), tax_name.strip()
    rate = _amount(default_rate)
    if not code or not name:
        raise ValueError("税种编码和名称不能为空")
    if rate < 0 or rate > 1:
        raise ValueError("默认税率必须在0到1之间")
    existing = (await db.execute(select(FinanceCenterMumarenTaxType).where(
        FinanceCenterMumarenTaxType.book_id == book_id,
        FinanceCenterMumarenTaxType.tax_code == code,
    ))).scalar_one_or_none()
    if existing is not None:
        raise ValueError("税种编码已存在")
    row = FinanceCenterMumarenTaxType(
        book_id=book_id, tax_code=code, tax_name=name, default_rate=rate,
        tax_category=tax_category.strip() if tax_category else None, is_active=True,
    )
    db.add(row)
    await db.flush()
    return row


async def update_tax_type(
    db: AsyncSession, *, tax_type_id: int, book_id: int, tax_name: str | None,
    default_rate: Any | None, tax_category: str | None, is_active: bool | None,
    operator_id: int,
) -> FinanceCenterMumarenTaxType:
    """Update non-key tax-type fields while preserving historical immutability."""
    await assert_book_writable(db, book_id=book_id)
    row = await db.get(FinanceCenterMumarenTaxType, tax_type_id)
    if row is None or row.book_id != book_id:
        raise LookupError("税种不存在")
    if tax_name is not None:
        if not tax_name.strip():
            raise ValueError("税种名称不能为空")
        row.tax_name = tax_name.strip()
    if default_rate is not None:
        rate = _amount(default_rate)
        if rate < 0 or rate > 1:
            raise ValueError("默认税率必须在0到1之间")
        row.default_rate = rate
    if tax_category is not None:
        row.tax_category = tax_category.strip() or None
    if is_active is not None:
        row.is_active = is_active
    await db.flush()
    return row


def build_tax_alerts(records: Iterable[Mapping[str, Any]], *, today: date) -> list[dict]:
    alerts = []
    for record in records:
        outstanding = tax_record_balance(record.get("tax_amount"), record.get("paid_amount"))
        due_date = record.get("due_date")
        if outstanding <= 0 or not isinstance(due_date, date):
            continue
        if due_date < today:
            level = "danger"
        elif due_date <= today + timedelta(days=7):
            level = "warning"
        else:
            continue
        alerts.append({"tax_name": record.get("tax_name"), "period": record.get("period"), "outstanding": outstanding, "due_date": due_date, "level": level})
    return sorted(alerts, key=lambda item: item["due_date"])


async def _load_tax_type(db: AsyncSession, *, tax_type_id: int, book_id: int) -> FinanceCenterMumarenTaxType:
    """加载 tax type 并强制校验同一账簿,禁止跨账簿关联。"""
    tax_type = (await db.execute(
        select(FinanceCenterMumarenTaxType).where(
            FinanceCenterMumarenTaxType.id == tax_type_id,
        )
    )).scalar_one_or_none()
    if tax_type is None:
        raise CrossBookTaxViolationError(f"税种 {tax_type_id} 不存在")
    if tax_type.book_id != book_id:
        raise CrossBookTaxViolationError(
            f"税种属于账簿 {tax_type.book_id},与目标账簿 {book_id} 不一致"
        )
    if not tax_type.is_active:
        raise CrossBookTaxViolationError(f"税种 {tax_type_id} 已停用")
    return tax_type


async def create_tax_record(
    db: AsyncSession,
    *,
    book_id: int,
    tax_type_id: int,
    period: str,
    tax_amount: Any,
    operator_id: int,
    due_date: date | None = None,
    remark: str | None = None,
) -> FinanceCenterMumarenTaxRecord:
    """创建税务草稿单据;强制同账簿校验,且不产生任何凭证分录。"""
    await _load_tax_type(db, tax_type_id=tax_type_id, book_id=book_id)
    amount = _amount(tax_amount)
    if amount < 0:
        raise ValueError("应缴税额不能为负数")

    record = FinanceCenterMumarenTaxRecord(
        book_id=book_id,
        tax_type_id=tax_type_id,
        period=period,
        tax_amount=amount,
        paid_amount=Decimal("0"),
        due_date=due_date,
        status="pending",
        workflow_status="draft",
        voucher_id=None,
        remark=remark,
    )
    db.add(record)
    await db.flush()
    return record


async def review_tax_record(
    db: AsyncSession,
    *,
    record_id: int,
    operator_id: int,
) -> FinanceCenterMumarenTaxRecord:
    """财务审核:仅允许 draft 进入 reviewed,不产生凭证分录。"""
    record = await db.get(FinanceCenterMumarenTaxRecord, record_id)
    if record is None:
        raise LookupError(f"税务单据 {record_id} 不存在")
    if record.workflow_status != "draft":
        raise InvalidTaxTransition(f"当前状态 {record.workflow_status},无法审核")
    record.workflow_status = "reviewed"
    return record


async def pay_tax_record(
    db: AsyncSession,
    *,
    record_id: int,
    payment_date: date,
    amount: Any,
    operator_id: int,
    remark: str | None = None,
) -> FinanceCenterMumarenTaxRecord:
    """人工缴税:防超额,更新独立税务记录,不产生凭证分录。"""
    record = await db.get(FinanceCenterMumarenTaxRecord, record_id)
    if record is None:
        raise LookupError(f"税务单据 {record_id} 不存在")
    if record.workflow_status not in ("reviewed", "posted"):
        raise InvalidTaxTransition(f"当前状态 {record.workflow_status},需先审核再缴税")

    payment = _amount(amount)
    if payment <= 0:
        raise ValueError("缴税金额必须为正数")
    tax = _amount(record.tax_amount)
    paid = _amount(record.paid_amount)
    if payment > tax - paid:
        raise ValueError(f"缴税金额超过未缴余额: 未缴 {tax - paid}, 本次 {payment}")

    record.paid_amount = paid + payment
    record.status = "paid" if record.paid_amount == tax else "pending"
    if remark:
        record.remark = remark
    return record
