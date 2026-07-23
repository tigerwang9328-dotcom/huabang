"""
账套初始化服务
============
对标虎狼 finance/book_service.py，全面迁移为 async PostgreSQL 版本。
功能：
  1. create_book()        - 创建新账套（含验证/期间初始化/科目初始化）
  2. init_subjects()      - 从标准科目模板初始化会计科目体系
  3. get_current_period() - 获取账套当前期间
  4. list_books()         - 拉取当前用户有权访问的账套列表
"""
from __future__ import annotations
import calendar
from datetime import date, datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.models.finance import FinBook, FinAccount, FinPeriod


# ── 默认科目模板（小企业会计准则，一级科目）────────────────────────────────
# (code, name, type, direction, level, is_cash_flow)
_DEFAULT_SUBJECTS: list[tuple] = [
    # 资产类
    ('1001', '库存现金',           'asset',     'debit',  1, True),
    ('1002', '银行存款',           'asset',     'debit',  1, True),
    ('1012', '其他货币资金',       'asset',     'debit',  1, True),
    ('1101', '短期投资',           'asset',     'debit',  1, False),
    ('1121', '应收票据',           'asset',     'debit',  1, False),
    ('1122', '应收账款',           'asset',     'debit',  1, False),
    ('1123', '预付账款',           'asset',     'debit',  1, False),
    ('1131', '应收股利',           'asset',     'debit',  1, False),
    ('1132', '应收利息',           'asset',     'debit',  1, False),
    ('1221', '其他应收款',         'asset',     'debit',  1, False),
    ('1401', '材料采购',           'asset',     'debit',  1, False),
    ('1402', '在途物资',           'asset',     'debit',  1, False),
    ('1403', '原材料',             'asset',     'debit',  1, False),
    ('1405', '库存商品',           'asset',     'debit',  1, False),
    ('1408', '委托加工物资',       'asset',     'debit',  1, False),
    ('1411', '包装物及低值易耗品', 'asset',     'debit',  1, False),
    ('1601', '固定资产',           'asset',     'debit',  1, False),
    ('1602', '累计折旧',           'asset',     'credit', 1, False),
    ('1604', '在建工程',           'asset',     'debit',  1, False),
    ('1701', '无形资产',           'asset',     'debit',  1, False),
    ('1801', '长期待摊费用',       'asset',     'debit',  1, False),
    ('1901', '待处理财产损溢',     'asset',     'debit',  1, False),
    # 负债类
    ('2001', '短期借款',           'liability', 'credit', 1, False),
    ('2101', '应付票据',           'liability', 'credit', 1, False),
    ('2202', '应付账款',           'liability', 'credit', 1, False),
    ('2203', '预收账款',           'liability', 'credit', 1, False),
    ('2211', '应付职工薪酬',       'liability', 'credit', 1, False),
    ('2221', '应交税费',           'liability', 'credit', 1, False),
    ('2231', '其他应付款',         'liability', 'credit', 1, False),
    ('2241', '预计负债',           'liability', 'credit', 1, False),
    ('2401', '递延收益',           'liability', 'credit', 1, False),
    ('2501', '长期借款',           'liability', 'credit', 1, False),
    # 所有者权益
    ('3001', '实收资本',           'equity',    'credit', 1, False),
    ('3002', '资本公积',           'equity',    'credit', 1, False),
    ('3101', '盈余公积',           'equity',    'credit', 1, False),
    ('3103', '本年利润',           'equity',    'credit', 1, False),
    ('3104', '利润分配',           'equity',    'credit', 1, False),
    # 收入类
    ('6001', '主营业务收入',       'income',    'credit', 1, False),
    ('6051', '其他业务收入',       'income',    'credit', 1, False),
    ('6111', '投资收益',           'income',    'credit', 1, False),
    ('6301', '营业外收入',         'income',    'credit', 1, False),
    # 费用类
    ('5001', '生产成本',           'expense',   'debit',  1, False),
    ('5101', '制造费用',           'expense',   'debit',  1, False),
    ('6401', '主营业务成本',       'expense',   'debit',  1, False),
    ('6402', '其他业务成本',       'expense',   'debit',  1, False),
    ('6403', '税金及附加',         'expense',   'debit',  1, False),
    ('6601', '销售费用',           'expense',   'debit',  1, False),
    ('6602', '管理费用',           'expense',   'debit',  1, False),
    ('6603', '财务费用',           'expense',   'debit',  1, False),
    ('6701', '资产减值损失',       'expense',   'debit',  1, False),
    ('6711', '营业外支出',         'expense',   'debit',  1, False),
    ('6801', '所得税费用',         'expense',   'debit',  1, False),
]


async def init_subjects(db: AsyncSession, book_id: int, operator: str = 'system') -> int:
    """
    从默认科目模板初始化会计科目，跳过已存在的科目。
    返回实际插入数量。
    """
    inserted = 0
    for code, name, acct_type, direction, level, is_cash_flow in _DEFAULT_SUBJECTS:
        existing = await db.scalar(
            select(FinAccount).where(FinAccount.book_id == book_id, FinAccount.account_code == code)
        )
        if existing:
            continue
        acct = FinAccount(
            book_id=book_id,
            account_code=code,
            account_name=name,
            account_type=acct_type,
            direction=direction,
            level=level,
            is_cash_flow=is_cash_flow,
            is_active=True,
        )
        db.add(acct)
        inserted += 1
    await db.flush()
    return inserted


async def _init_periods(db: AsyncSession, book_id: int, start_period: str) -> None:
    """从启用月份到当年12月，初始化所有会计期间为 open 状态。"""
    y, m = int(start_period[:4]), int(start_period[5:7])
    current_year = date.today().year
    # 初始化到当前年年底（最多撑3年）
    end_year = min(current_year + 1, y + 2)
    for year in range(y, end_year + 1):
        start_m = m if year == y else 1
        for month in range(start_m, 13):
            period_str = f'{year:04d}-{month:02d}'
            existing = await db.scalar(
                select(FinPeriod).where(FinPeriod.book_id == book_id, FinPeriod.period == period_str)
            )
            if not existing:
                db.add(FinPeriod(book_id=book_id, period=period_str, status='open'))
    await db.flush()


async def create_book(
    db: AsyncSession,
    *,
    book_code: str,
    book_name: str,
    company_name: str = '牧马人服饰',
    accounting_standard: str = '小企业会计准则',
    start_date: str,        # YYYY-MM-DD
    operator: str = 'system',
    safety_cash_line: float = 300000.0,
) -> FinBook:
    """
    创建新账套并自动完成初始化：
      1. 插入 fin_books 记录
      2. 初始化当年所有会计期间（open）
      3. 从标准模板批量导入会计科目
    返回已 flush 但未 commit 的 FinBook 实例（调用方负责 commit）。
    """
    # 校验 book_code 唯一
    dup = await db.scalar(select(FinBook).where(FinBook.book_code == book_code))
    if dup:
        raise ValueError(f'账套编码 {book_code} 已存在')

    start_period = start_date[:7]   # YYYY-MM
    book = FinBook(
        book_code=book_code,
        book_name=book_name,
        company_name=company_name,
        accounting_standard=accounting_standard,
        start_date=start_date,
        current_period=start_period,
        status='active',
        safety_cash_line=safety_cash_line,
        created_by=operator,
    )
    db.add(book)
    await db.flush()   # 拿到 book.id

    await _init_periods(db, book.id, start_period)
    await init_subjects(db, book.id, operator)

    return book


async def list_books(db: AsyncSession, user_id: Optional[int] = None) -> list[FinBook]:
    """拉取账套列表（暂不过滤权限，后续按 fin_book_permissions 过滤）。"""
    q = select(FinBook).where(FinBook.status != 'deleted').order_by(FinBook.id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_current_period(db: AsyncSession, book_id: int) -> str:
    """获取账套当前会计期间（YYYY-MM）。"""
    book = await db.get(FinBook, book_id)
    if not book:
        raise ValueError(f'账套 {book_id} 不存在')
    return book.current_period or date.today().strftime('%Y-%m')
