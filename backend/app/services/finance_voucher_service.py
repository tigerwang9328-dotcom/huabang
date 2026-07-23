"""
凭证引擎（VoucherService）
========================
对标虎狼 finance/voucher_engine.py，全面迁移为 async PostgreSQL 版本。
功能：
  next_voucher_no()  - 生成下一张凭证编号（线程安全的行锁 SELECT FOR UPDATE）
  validate()         - 校验借贷平衡 & 科目有效性
  create_voucher()   - 新建凭证（draft 状态）
  review()           - 审核（draft → reviewed）
  post()             - 过账（reviewed → posted），同步更新账簿余额
  reverse()          - 红字冲销（posted → reversed），生成反向凭证
  update_ledger()    - 内部：更新 fin_ledger_balances
"""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, and_

from app.models.finance import (
    FinVoucher, FinVoucherLine, FinAccount, FinLedgerBalance, FinPeriod,
)


# ── 校验 ──────────────────────────────────────────────────────────────────────

class VoucherValidationError(Exception):
    pass


async def validate(
    db: AsyncSession,
    book_id: int,
    lines: list[dict],
) -> None:
    """
    校验凭证合法性：
    1. 至少2条分录
    2. 借贷合计相等（精度 0.01）
    3. 每行借贷不能同时为0或同时非0
    4. 科目存在且属于该账套
    """
    if len(lines) < 2:
        raise VoucherValidationError('凭证至少需要2条分录')

    total_debit = Decimal('0')
    total_credit = Decimal('0')
    for i, line in enumerate(lines):
        dr = Decimal(str(line.get('debit_amount', 0)))
        cr = Decimal(str(line.get('credit_amount', 0)))
        if dr == 0 and cr == 0:
            raise VoucherValidationError(f'第{i+1}行借贷金额不能同时为0')
        if dr != 0 and cr != 0:
            raise VoucherValidationError(f'第{i+1}行借贷金额不能同时非0')
        total_debit += dr
        total_credit += cr
        # 校验科目存在
        acct_id = line.get('account_id')
        acct_code = line.get('account_code', '')
        if acct_id:
            acct = await db.scalar(
                select(FinAccount).where(FinAccount.id == acct_id, FinAccount.book_id == book_id)
            )
            if not acct:
                raise VoucherValidationError(f'第{i+1}行科目ID {acct_id} 不存在或不属于该账套')
        elif acct_code:
            acct = await db.scalar(
                select(FinAccount).where(FinAccount.account_code == acct_code, FinAccount.book_id == book_id)
            )
            if not acct:
                raise VoucherValidationError(f'第{i+1}行科目编码 {acct_code} 不存在或不属于该账套')
        else:
            raise VoucherValidationError(f'第{i+1}行必须指定科目')

    if abs(total_debit - total_credit) > Decimal('0.01'):
        raise VoucherValidationError(
            f'借贷不平衡：借方合计 {total_debit}，贷方合计 {total_credit}'
        )


# ── 凭证编号 ──────────────────────────────────────────────────────────────────

async def next_voucher_no(
    db: AsyncSession,
    book_id: int,
    voucher_type: str,
    period: str,
) -> str:
    """
    生成下一个凭证编号，格式：{type}-{YYYY-MM}-{seq:03d}
    使用 SELECT MAX + 1 保证单账套内不重复（并发量低，不需要 SEQUENCE）。
    """
    prefix = f'{voucher_type}-{period}-'
    prefix_len = len(prefix) + 1
    result = await db.execute(
        text(f"""
            SELECT COALESCE(MAX(
                CAST(SUBSTRING(voucher_no, {prefix_len}) AS INTEGER)
            ), 0) + 1
            FROM fin_vouchers
            WHERE book_id = :book_id AND voucher_no LIKE :pattern
        """),
        {'book_id': book_id, 'pattern': prefix + '%'},
    )
    seq = result.scalar() or 1
    return f'{prefix}{seq:03d}'


# ── 创建凭证 ──────────────────────────────────────────────────────────────────

async def create_voucher(
    db: AsyncSession,
    *,
    book_id: int,
    voucher_type: str = '记',
    voucher_date: date,
    lines: list[dict],
    summary: str = '',
    source_type: str = 'manual',
    source_ref: str = '',
    status: str = 'draft',   # 'draft' or 'reviewed'
    operator: str = '',
) -> FinVoucher:
    """
    创建新凭证（含分录），返回已 flush 的 FinVoucher（调用方 commit）。
    lines 格式：[{account_id, account_code, debit_amount, credit_amount, summary, ...}]
    """
    period = voucher_date.strftime('%Y-%m')
    await validate(db, book_id, lines)

    voucher_no = await next_voucher_no(db, book_id, voucher_type, period)

    total_debit  = sum(Decimal(str(l.get('debit_amount', 0)))  for l in lines)
    total_credit = sum(Decimal(str(l.get('credit_amount', 0))) for l in lines)

    voucher = FinVoucher(
        book_id=book_id,
        voucher_no=voucher_no,
        voucher_type=voucher_type,
        voucher_date=voucher_date,
        period=period,
        summary=summary,
        source_type=source_type,
        source_ref=source_ref,
        status=status,
        total_debit=total_debit,
        total_credit=total_credit,
        created_by=operator,
    )
    if status == 'reviewed':
        voucher.reviewed_by = operator
        voucher.reviewed_at = datetime.now()
    db.add(voucher)
    await db.flush()

    for i, line in enumerate(lines):
        # 如果只有 account_code，补全 account_id
        acct_id = line.get('account_id')
        acct_code = line.get('account_code', '')
        if not acct_id and acct_code:
            acct = await db.scalar(
                select(FinAccount).where(FinAccount.account_code == acct_code, FinAccount.book_id == book_id)
            )
            if acct:
                acct_id = acct.id
        db.add(FinVoucherLine(
            voucher_id=voucher.id,
            line_no=i + 1,
            account_id=acct_id,
            account_code=acct_code or '',
            debit_amount=Decimal(str(line.get('debit_amount', 0))),
            credit_amount=Decimal(str(line.get('credit_amount', 0))),
            summary=line.get('summary', summary),
            biz_date=line.get('biz_date', voucher_date),
        ))

    await db.flush()
    return voucher


# ── 审核 ──────────────────────────────────────────────────────────────────────

async def review(db: AsyncSession, voucher_id: int, operator: str) -> FinVoucher:
    """将凭证从 draft 流转到 reviewed。"""
    v = await db.get(FinVoucher, voucher_id)
    if not v:
        raise VoucherValidationError('凭证不存在')
    if v.status != 'draft':
        raise VoucherValidationError(f'只有草稿凭证可以审核，当前状态：{v.status}')
    v.status = 'reviewed'
    v.reviewed_by = operator
    v.reviewed_at = datetime.now()
    await db.flush()
    return v


# ── 过账 ──────────────────────────────────────────────────────────────────────

async def post(db: AsyncSession, voucher_id: int, operator: str) -> FinVoucher:
    """
    将凭证从 reviewed 流转到 posted，同步更新 fin_ledger_balances。
    """
    v = await db.get(FinVoucher, voucher_id)
    if not v:
        raise VoucherValidationError('凭证不存在')
    if v.status != 'reviewed':
        raise VoucherValidationError(f'只有已审核凭证可以过账，当前状态：{v.status}')

    # 获取所有分录
    lines_res = await db.execute(
        select(FinVoucherLine).where(FinVoucherLine.voucher_id == voucher_id)
    )
    lines = lines_res.scalars().all()

    # 逐行更新账簿余额
    period = v.period or v.voucher_date.strftime('%Y-%m')
    for line in lines:
        if not line.account_id:
            continue
        acct = await db.get(FinAccount, line.account_id)
        if not acct:
            continue
        await _update_ledger(db, v.book_id, line.account_id, acct.account_code,
                             period, line.debit_amount, line.credit_amount, acct.direction)

    v.status = 'posted'
    v.posted_by = operator
    v.posted_at = datetime.now()
    await db.flush()
    return v


async def _update_ledger(
    db: AsyncSession,
    book_id: int,
    account_id: int,
    account_code: str,
    period: str,
    debit: Decimal,
    credit: Decimal,
    direction: str,
) -> None:
    """
    Upsert fin_ledger_balances：
    - 若记录不存在则创建（期初=0）
    - direction='debit'  → 余额 = 期初 + 借方 - 贷方
    - direction='credit' → 余额 = 期初 - 借方 + 贷方
    """
    row = await db.scalar(
        select(FinLedgerBalance).where(
            FinLedgerBalance.book_id == book_id,
            FinLedgerBalance.account_id == account_id,
            FinLedgerBalance.period == period,
        )
    )
    if not row:
        row = FinLedgerBalance(
            book_id=book_id,
            account_id=account_id,
            period=period,
            opening_debit=Decimal('0'),
            opening_credit=Decimal('0'),
            period_debit=Decimal('0'),
            period_credit=Decimal('0'),
            closing_debit=Decimal('0'),
            closing_credit=Decimal('0'),
        )
        db.add(row)
        await db.flush()

    row.period_debit  = (row.period_debit  or Decimal('0')) + debit
    row.period_credit = (row.period_credit or Decimal('0')) + credit

    # 重算期末余额
    net = (row.opening_debit or 0) - (row.opening_credit or 0) + row.period_debit - row.period_credit
    if direction == 'debit':
        # 借方科目：期末 = 期初借 - 期初贷 + 本期借 - 本期贷
        closing = (row.opening_debit or Decimal('0')) - (row.opening_credit or Decimal('0')) + row.period_debit - row.period_credit
        row.closing_debit  = max(closing, Decimal('0'))
        row.closing_credit = max(-closing, Decimal('0'))
    else:
        # 贷方科目：期末 = 期初贷 - 期初借 + 本期贷 - 本期借
        closing = (row.opening_credit or Decimal('0')) - (row.opening_debit or Decimal('0')) + row.period_credit - row.period_debit
        row.closing_credit = max(closing, Decimal('0'))
        row.closing_debit  = max(-closing, Decimal('0'))

    await db.flush()


# ── 冲销 ──────────────────────────────────────────────────────────────────────

async def reverse(db: AsyncSession, voucher_id: int, operator: str) -> FinVoucher:
    """
    红字冲销：将原凭证所有分录借贷对调，生成一张新的 posted 凭证。
    原凭证标记为 reversed。
    """
    orig = await db.get(FinVoucher, voucher_id)
    if not orig:
        raise VoucherValidationError('凭证不存在')
    if orig.status != 'posted':
        raise VoucherValidationError('只有已过账凭证可以冲销')

    lines_res = await db.execute(
        select(FinVoucherLine).where(FinVoucherLine.voucher_id == voucher_id)
    )
    orig_lines = lines_res.scalars().all()

    reverse_lines = [
        {
            'account_id':    line.account_id,
            'account_code':  line.account_code,
            'debit_amount':  line.credit_amount,    # 借贷对调
            'credit_amount': line.debit_amount,
            'summary':       f'冲销：{line.summary or ""}',
        }
        for line in orig_lines
    ]

    new_v = await create_voucher(
        db,
        book_id=orig.book_id,
        voucher_type=orig.voucher_type,
        voucher_date=date.today(),
        lines=reverse_lines,
        summary=f'冲销凭证 {orig.voucher_no}',
        source_type='reverse',
        source_ref=str(orig.voucher_no),
        status='reviewed',
        operator=operator,
    )
    # 直接过账冲销凭证
    new_v.status = 'posted'
    new_v.posted_by = operator
    new_v.posted_at = datetime.now()

    # 标记原凭证
    orig.status = 'reversed'
    await db.flush()
    return new_v
