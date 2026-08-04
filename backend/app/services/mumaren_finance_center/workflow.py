"""凭证与历史记录的纯领域规则，不依赖华邦旧财务服务。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenAuditLog,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenFiscalPeriod,
    FinanceCenterMumarenHistoryVoucher,
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)


_BOOK_CODE_PATTERN = re.compile(r"^[A-Z0-9_-]{1,64}$")
_STARTER_ACCOUNTS: tuple[tuple[str, str, str, str], ...] = (
    ("1001", "库存现金", "asset", "debit"), ("1002", "银行存款", "asset", "debit"),
    ("1122", "应收账款", "asset", "debit"), ("1405", "库存商品", "asset", "debit"),
    ("1601", "固定资产", "asset", "debit"), ("2202", "应付账款", "liability", "credit"),
    ("2211", "应付职工薪酬", "liability", "credit"), ("2221", "应交税费", "liability", "credit"),
    ("4001", "实收资本", "equity", "credit"), ("4103", "本年利润", "equity", "credit"),
    ("6001", "主营业务收入", "income", "credit"), ("6401", "主营业务成本", "expense", "debit"),
    ("6601", "销售费用", "expense", "debit"), ("6602", "管理费用", "expense", "debit"),
    ("6603", "财务费用", "expense", "debit"),
)


class InvalidVoucherTransition(ValueError):
    """凭证状态转换不符合人工审核/过账规则。"""


class UnbalancedVoucherError(ValueError):
    """凭证分录不符合借贷记账的基本约束。"""


class HistoricalRecordReadonlyError(ValueError):
    """历史来源数据不得进入当前账工作流或被修改。"""


async def create_book(
    db: AsyncSession, *, book_code: str, book_name: str, company_name: str | None,
    status: str, operator_id: int,
) -> FinanceCenterMumarenBook:
    """Create an isolated current ledger with the minimum starter chart and periods."""
    normalized_code = book_code.strip().upper()
    normalized_name = book_name.strip()
    normalized_company = company_name.strip() if company_name else None
    if not _BOOK_CODE_PATTERN.fullmatch(normalized_code):
        raise ValueError("账簿编码只能包含大写字母、数字、下划线或连字符，长度不超过64位")
    if not normalized_name:
        raise ValueError("账簿名称不能为空")
    if status not in {"active", "inactive"}:
        raise ValueError("账簿状态只能为 active 或 inactive")
    existing = (await db.execute(
        select(FinanceCenterMumarenBook).where(FinanceCenterMumarenBook.book_code == normalized_code)
    )).scalar_one_or_none()
    if existing is not None:
        raise ValueError("账簿编码已存在")
    book = FinanceCenterMumarenBook(
        book_code=normalized_code, book_name=normalized_name, company_name=normalized_company,
        status=status, is_readonly=False, created_by=operator_id,
    )
    db.add(book)
    await db.flush()
    for account_code, account_name, account_type, direction in _STARTER_ACCOUNTS:
        db.add(FinanceCenterMumarenAccount(
            book_id=book.id, account_code=account_code, account_name=account_name,
            account_type=account_type, direction=direction, level=1, is_active=True,
        ))
    fiscal_year = date.today().year
    for month in range(1, 13):
        next_month = date(fiscal_year, month + 1, 1) if month < 12 else date(fiscal_year + 1, 1, 1)
        db.add(FinanceCenterMumarenFiscalPeriod(
            book_id=book.id, period_code=f"{fiscal_year}-{month:02d}", start_date=date(fiscal_year, month, 1),
            end_date=next_month.fromordinal(next_month.toordinal() - 1), status="open",
        ))
    db.add(FinanceCenterMumarenAuditLog(
        book_id=book.id, action="create_book", operator_id=operator_id, detail=normalized_code,
    ))
    return book


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


async def assert_book_writable(db: AsyncSession, *, book_id: int) -> FinanceCenterMumarenBook:
    """Return a current book and reject all mutation attempts against Kingdee books."""
    book = await db.get(FinanceCenterMumarenBook, book_id)
    if book is None:
        raise LookupError("账簿不存在")
    if book.is_readonly:
        raise HistoricalRecordReadonlyError("历史迁移账簿只读，不能维护基础资料")
    return book


async def update_book(
    db: AsyncSession, *, book_id: int, book_name: str | None, company_name: str | None,
    operator_id: int,
) -> FinanceCenterMumarenBook:
    """Update only current-book display metadata; a Kingdee book remains immutable."""
    book = await assert_book_writable(db, book_id=book_id)
    if book_name is not None:
        normalized_name = book_name.strip()
        if not normalized_name:
            raise ValueError("账簿名称不能为空")
        book.book_name = normalized_name
    if company_name is not None:
        book.company_name = company_name.strip() or None
    db.add(FinanceCenterMumarenAuditLog(
        book_id=book_id, action="update_book", operator_id=operator_id, detail=book.book_code,
    ))
    await db.flush()
    return book


async def replenish_starter_accounts(
    db: AsyncSession, *, book_id: int, operator_id: int,
) -> int:
    """Idempotently add only missing starter accounts to a writable current book."""
    await assert_book_writable(db, book_id=book_id)
    existing_rows = list((await db.execute(
        select(FinanceCenterMumarenAccount).where(FinanceCenterMumarenAccount.book_id == book_id)
    )).scalars().all())
    existing_codes = {row.account_code for row in existing_rows}
    added = 0
    for account_code, account_name, account_type, direction in _STARTER_ACCOUNTS:
        if account_code in existing_codes:
            continue
        result = await db.execute(
            pg_insert(FinanceCenterMumarenAccount)
            .values(
                book_id=book_id, account_code=account_code, account_name=account_name,
                account_type=account_type, direction=direction, level=1, is_active=True,
            )
            .on_conflict_do_nothing(index_elements=["book_id", "account_code"])
            .returning(FinanceCenterMumarenAccount.id)
        )
        added += int(result.scalar_one_or_none() is not None)
    db.add(FinanceCenterMumarenAuditLog(
        book_id=book_id, action="replenish_starter_accounts", operator_id=operator_id,
        detail=f"added={added}",
    ))
    await db.flush()
    return added


async def create_account(
    db: AsyncSession, *, book_id: int, account_code: str, account_name: str,
    account_type: str, direction: str, level: int, operator_id: int,
) -> FinanceCenterMumarenAccount:
    """Create one current-book account; historical books are immutable."""
    await assert_book_writable(db, book_id=book_id)
    normalized_code, normalized_name = account_code.strip(), account_name.strip()
    if not normalized_code or not normalized_name:
        raise ValueError("科目编码和名称不能为空")
    if account_type not in {"asset", "liability", "equity", "income", "expense"}:
        raise ValueError("科目类别无效")
    if direction not in {"debit", "credit"}:
        raise ValueError("余额方向无效")
    if level < 1 or level > 10:
        raise ValueError("科目级次必须在1到10之间")
    existing = (await db.execute(select(FinanceCenterMumarenAccount).where(
        FinanceCenterMumarenAccount.book_id == book_id,
        FinanceCenterMumarenAccount.account_code == normalized_code,
    ))).scalar_one_or_none()
    if existing is not None:
        raise ValueError("科目编码已存在")
    account = FinanceCenterMumarenAccount(
        book_id=book_id, account_code=normalized_code, account_name=normalized_name,
        account_type=account_type, direction=direction, level=level, is_active=True,
    )
    db.add(account)
    db.add(FinanceCenterMumarenAuditLog(
        book_id=book_id, action="create_account", operator_id=operator_id, detail=normalized_code,
    ))
    await db.flush()
    return account


async def update_account(
    db: AsyncSession, *, account_id: int, book_id: int, account_name: str | None,
    account_type: str | None, direction: str | None, level: int | None,
    is_active: bool | None, operator_id: int,
) -> FinanceCenterMumarenAccount:
    """Update controlled account attributes without changing account code or book."""
    await assert_book_writable(db, book_id=book_id)
    account = await db.get(FinanceCenterMumarenAccount, account_id)
    if account is None or account.book_id != book_id:
        raise LookupError("科目不存在")
    if account.is_readonly:
        raise HistoricalRecordReadonlyError("历史迁移科目只读，不能维护")
    if account_name is not None:
        if not account_name.strip():
            raise ValueError("科目名称不能为空")
        account.account_name = account_name.strip()
    if account_type is not None:
        if account_type not in {"asset", "liability", "equity", "income", "expense"}:
            raise ValueError("科目类别无效")
        account.account_type = account_type
    if direction is not None:
        if direction not in {"debit", "credit"}:
            raise ValueError("余额方向无效")
        account.direction = direction
    if level is not None:
        if level < 1 or level > 10:
            raise ValueError("科目级次必须在1到10之间")
        account.level = level
    if is_active is not None:
        account.is_active = is_active
    db.add(FinanceCenterMumarenAuditLog(
        book_id=book_id, action="update_account", operator_id=operator_id, detail=account.account_code,
    ))
    await db.flush()
    return account


async def create_voucher(
    db: AsyncSession,
    *,
    book_id: int,
    voucher_no: str | None,
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
    voucher_no = (voucher_no or "").strip() or await next_voucher_number(
        db, book_id=book_id, voucher_date=effective_date, voucher_type=voucher_type,
    )
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


async def next_voucher_number(
    db: AsyncSession, *, book_id: int, voucher_date: date, voucher_type: str = "记",
) -> str:
    """Generate the next number for one book/date/type; this only reserves a display value."""
    prefix = f"{voucher_type}-{voucher_date:%Y%m}-"
    rows = (await db.execute(
        select(FinanceCenterMumarenVoucher.voucher_no).where(
            FinanceCenterMumarenVoucher.book_id == book_id,
            FinanceCenterMumarenVoucher.voucher_date == voucher_date,
            FinanceCenterMumarenVoucher.voucher_no.like(f"{prefix}%"),
        )
    )).scalars().all()
    used = set()
    for value in rows:
        match = re.fullmatch(re.escape(prefix) + r"(\d{3,})", str(value or ""))
        if match:
            used.add(int(match.group(1)))
    sequence = 1
    while sequence in used:
        sequence += 1
    return f"{prefix}{sequence:03d}"


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
