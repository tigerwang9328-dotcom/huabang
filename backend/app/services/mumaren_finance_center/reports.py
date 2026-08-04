"""牧马人财务中心的独立账簿与报表服务。

所有查询只针对 ``finance_center_mumaren`` 当前账表，且仅统计已人工过账
的凭证；历史金蝶归档表和华邦既有财务表均不参与计算。

Task 15/16/17: 在原有凭证聚合基础上，联动 12 个 CRUD 页面录入的
expense_entries / payrolls / fixed_assets / invoices / cash_flows 表，
使录入数据真正影响利润表、资产负债表与现金流量表。新增聚合结果累加到
现有计算之上，不替换原有逻辑，且不破坏既有接口签名。
"""
from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenVoucher,
    FinanceCenterMumarenVoucherLine,
)
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenCashFlow,
    FinanceCenterMumarenExpenseEntry,
    FinanceCenterMumarenFixedAsset,
    FinanceCenterMumarenInvoice,
    FinanceCenterMumarenPayroll,
)
from app.services.mumaren_finance_center.business import depreciation_for_period


_ZERO = Decimal("0")
_TOLERANCE = Decimal("0.01")

# 应收发票类型关键词：匹配 invoice_type 视为应收
_RECEIVABLE_INVOICE_MARKERS = ("receivable", "sales", "销售", "销项")
# 应付发票类型关键词：匹配 invoice_type 视为应付
_PAYABLE_INVOICE_MARKERS = ("payable", "purchase", "采购", "进项")


def _value(row: Mapping[str, Any] | object, name: str, default: Any = None) -> Any:
    return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)


def _amount(row: Mapping[str, Any] | object, name: str) -> Decimal:
    return Decimal(str(_value(row, name, _ZERO) or _ZERO))


def _account_row(account: FinanceCenterMumarenAccount | object, debit: Decimal, credit: Decimal) -> dict:
    direction = _value(account, "direction", "debit")
    net = debit - credit if direction == "debit" else credit - debit
    closing_debit = max(net, _ZERO) if direction == "debit" else max(-net, _ZERO)
    closing_credit = max(-net, _ZERO) if direction == "debit" else max(net, _ZERO)
    return {
        "account_id": _value(account, "id"),
        "account_code": _value(account, "account_code"),
        "account_name": _value(account, "account_name"),
        "direction": direction,
        "debit_amount": debit,
        "credit_amount": credit,
        "closing_debit": closing_debit,
        "closing_credit": closing_credit,
    }


def _totals_by_account(lines: Iterable[Mapping[str, Any] | object]) -> dict[int, tuple[Decimal, Decimal]]:
    totals: dict[int, tuple[Decimal, Decimal]] = {}
    for line in lines:
        account_id = _value(line, "account_id")
        if account_id is None:
            continue
        debit, credit = totals.get(account_id, (_ZERO, _ZERO))
        totals[account_id] = (debit + _amount(line, "debit_amount"), credit + _amount(line, "credit_amount"))
    return totals


def _classify_invoice(invoice_type: str) -> str | None:
    """根据 invoice_type 关键词判定应收/应付；不匹配返回 None。"""
    text = (invoice_type or "").lower()
    if any(marker in text for marker in _RECEIVABLE_INVOICE_MARKERS):
        return "receivable"
    if any(marker in text for marker in _PAYABLE_INVOICE_MARKERS):
        return "payable"
    return None


def build_trial_balance(
    accounts: Sequence[FinanceCenterMumarenAccount | object],
    posted_lines: Iterable[Mapping[str, Any] | object],
    *,
    extra_adjustments: Sequence[Mapping[str, Any]] | None = None,
) -> dict:
    """按当前账已过账分录生成科目余额及试算平衡。

    ``extra_adjustments`` 用于联动 CRUD 页面录入的应付职工薪酬、固定资产
    净值、应收/应付发票等。每条调整可命中已有科目（按 account_code 匹配
    并累加借贷），或作为合成行展示。调整结构::

        {
            "account_code": "2202",
            "account_name": "应付职工薪酬",
            "account_type": "liability",  # asset/liability/equity
            "direction": "credit",
            "debit_amount": Decimal("0"),
            "credit_amount": Decimal("5000"),
        }
    """
    totals = _totals_by_account(posted_lines)

    code_to_account: dict[str, FinanceCenterMumarenAccount | object] = {}
    code_to_type: dict[str, str | None] = {}
    for account in accounts:
        code = _value(account, "account_code")
        if code:
            code_to_account[str(code)] = account
            code_to_type[str(code)] = _value(account, "account_type")

    synthetic_rows: list[dict] = []
    if extra_adjustments:
        for adj in extra_adjustments:
            code = str(_value(adj, "account_code", "") or "")
            debit = _amount(adj, "debit_amount")
            credit = _amount(adj, "credit_amount")
            if debit == _ZERO and credit == _ZERO:
                continue
            matched_account = code_to_account.get(code) if code else None
            if matched_account is not None:
                account_id = _value(matched_account, "id")
                d, c = totals.get(account_id, (_ZERO, _ZERO))
                totals[account_id] = (d + debit, c + credit)
            else:
                direction = _value(adj, "direction", "debit")
                adj_type = _value(adj, "account_type")
                if adj_type and code:
                    code_to_type[code] = adj_type
                net = debit - credit if direction == "debit" else credit - debit
                synthetic_rows.append({
                    "account_id": None,
                    "account_code": code,
                    "account_name": _value(adj, "account_name", code),
                    "direction": direction,
                    "debit_amount": debit,
                    "credit_amount": credit,
                    "closing_debit": max(net, _ZERO) if direction == "debit" else max(-net, _ZERO),
                    "closing_credit": max(-net, _ZERO) if direction == "debit" else max(net, _ZERO),
                })

    rows = []
    for account in sorted(accounts, key=lambda item: str(_value(item, "account_code", ""))):
        debit, credit = totals.get(_value(account, "id"), (_ZERO, _ZERO))
        rows.append(_account_row(account, debit, credit))

    rows.extend(sorted(synthetic_rows, key=lambda r: str(r.get("account_code", ""))))

    total_debit = sum((row["debit_amount"] for row in rows), _ZERO)
    total_credit = sum((row["credit_amount"] for row in rows), _ZERO)

    assets_total, liabilities_total, equity_total = _classify_totals(rows, code_to_type)
    balance_check = _balance_check(assets_total, liabilities_total, equity_total)

    return {
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": total_debit == total_credit,
        "assets_total": assets_total,
        "liabilities_total": liabilities_total,
        "equity_total": equity_total,
        "balance_check": balance_check,
    }


def _classify_totals(
    rows: Iterable[Mapping[str, Any]], code_to_type: Mapping[str, str | None]
) -> tuple[Decimal, Decimal, Decimal]:
    """按 account_type（通过 code_to_type 映射）汇总资产、负债、权益净额。"""
    assets = _ZERO
    liabilities = _ZERO
    equity = _ZERO
    for row in rows:
        code = str(row.get("account_code", "") or "")
        account_type = code_to_type.get(code)
        closing_debit = _amount(row, "closing_debit")
        closing_credit = _amount(row, "closing_credit")
        if account_type == "asset":
            assets += closing_debit - closing_credit
        elif account_type == "liability":
            liabilities += closing_credit - closing_debit
        elif account_type == "equity":
            equity += closing_credit - closing_debit
    return assets, liabilities, equity


def _balance_check(assets: Decimal, liabilities: Decimal, equity: Decimal) -> dict:
    """资产 = 负债 + 权益 的平衡校验结果。"""
    difference = assets - (liabilities + equity)
    return {
        "assets_total": assets,
        "liabilities_total": liabilities,
        "equity_total": equity,
        "difference": difference,
        "is_balanced": abs(difference) < _TOLERANCE,
    }


def build_profit_statement(
    accounts: Sequence[FinanceCenterMumarenAccount | object],
    posted_lines: Iterable[Mapping[str, Any] | object],
    *,
    extra_expenses: Sequence[Mapping[str, Any]] | None = None,
) -> dict:
    """按收入贷减借、费用借减贷计算利润表；没有当前账即返回全零。

    ``extra_expenses`` 用于联动 expense_entries / payrolls / fixed_assets
    录入的费用项。每条结构::

        {
            "account_code": "6602.01",
            "account_name": "管理费用-工资",
            "amount": Decimal("5000"),
        }

    命中已有费用科目（按 account_code 匹配）则累加到该科目行，否则作为
    合成费用行展示，并计入费用合计。
    """
    totals = _totals_by_account(posted_lines)
    income_rows: list[dict] = []
    expense_rows: list[dict] = []
    code_to_account: dict[str, FinanceCenterMumarenAccount | object] = {}
    for account in accounts:
        code = _value(account, "account_code")
        if code:
            code_to_account[str(code)] = account

    for account in sorted(accounts, key=lambda item: str(_value(item, "account_code", ""))):
        debit, credit = totals.get(_value(account, "id"), (_ZERO, _ZERO))
        account_type = _value(account, "account_type")
        base = {
            "account_id": _value(account, "id"),
            "account_code": _value(account, "account_code"),
            "account_name": _value(account, "account_name"),
        }
        if account_type == "income":
            income_rows.append({**base, "amount": credit - debit})
        elif account_type == "expense":
            expense_rows.append({**base, "amount": debit - credit})

    if extra_expenses:
        for extra in extra_expenses:
            amount = _amount(extra, "amount")
            if amount == _ZERO:
                continue
            code = str(_value(extra, "account_code", "") or "")
            matched = next(
                (row for row in expense_rows if str(row.get("account_code", "")) == code and code),
                None,
            )
            if matched is not None:
                matched["amount"] = _amount(matched, "amount") + amount
            else:
                expense_rows.append({
                    "account_id": None,
                    "account_code": code,
                    "account_name": _value(extra, "account_name", code),
                    "amount": amount,
                })

    expense_rows.sort(key=lambda row: str(row.get("account_code", "")))
    total_income = sum((row["amount"] for row in income_rows), _ZERO)
    total_expense = sum((row["amount"] for row in expense_rows), _ZERO)
    return {
        "income_rows": income_rows,
        "expense_rows": expense_rows,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_profit": total_income - total_expense,
    }


def build_cash_flow_statement(
    accounts: Sequence[FinanceCenterMumarenAccount | object],
    posted_lines: Iterable[Mapping[str, Any] | object],
    *,
    cash_flow_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict:
    """构建现金流量表。

    - 按 cash_flows.category 分类（operating/investing/financing）
    - direction='in' 计入流入，direction='out' 计入流出
    - 净额 = 流入 - 流出
    - 现金净增加 = Σ(现金类科目期末借方 - 期末贷方)
    """
    totals = _totals_by_account(posted_lines)
    cash_net_increase = _ZERO
    for account in accounts:
        account_type = _value(account, "account_type")
        if account_type != "asset":
            continue
        account_name = str(_value(account, "account_name", "") or "")
        # 现金类科目：名称含“库存现金/银行存款/其他货币资金/现金”
        if not any(marker in account_name for marker in ("现金", "银行存款", "货币资金")):
            continue
        debit, credit = totals.get(_value(account, "id"), (_ZERO, _ZERO))
        cash_net_increase += debit - credit

    sections = {
        "operating": {"inflow": _ZERO, "outflow": _ZERO, "net": _ZERO},
        "investing": {"inflow": _ZERO, "outflow": _ZERO, "net": _ZERO},
        "financing": {"inflow": _ZERO, "outflow": _ZERO, "net": _ZERO},
    }
    if cash_flow_records:
        for record in cash_flow_records:
            category = _value(record, "category", "operating") or "operating"
            direction = _value(record, "direction", "in") or "in"
            amount = _amount(record, "amount")
            if category not in sections:
                continue
            if direction == "in":
                sections[category]["inflow"] += amount
            elif direction == "out":
                sections[category]["outflow"] += amount
    for section in sections.values():
        section["net"] = section["inflow"] - section["outflow"]

    total_inflow = sum((s["inflow"] for s in sections.values()), _ZERO)
    total_outflow = sum((s["outflow"] for s in sections.values()), _ZERO)
    total_net = total_inflow - total_outflow

    return {
        "sections": sections,
        "total_inflow": total_inflow,
        "total_outflow": total_outflow,
        "total_net": total_net,
        "cash_net_increase": cash_net_increase,
    }


def _period_bounds(period: str | None) -> tuple[date | None, date | None]:
    if period is None:
        return None, None
    try:
        year, month = (int(part) for part in period.split("-", 1))
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    except (TypeError, ValueError) as error:
        raise ValueError("期间必须是 YYYY-MM") from error


async def _load_posted_book_data(
    db: AsyncSession, *, book_id: int, period: str | None = None,
    start_date: date | None = None, end_date: date | None = None,
) -> tuple[list[FinanceCenterMumarenAccount], list[FinanceCenterMumarenVoucherLine]]:
    """读取新 schema 当前账：仅已过账凭证，绝不触碰历史或旧财务对象。"""
    accounts_result = await db.execute(
        select(FinanceCenterMumarenAccount)
        .where(
            FinanceCenterMumarenAccount.book_id == book_id,
            FinanceCenterMumarenAccount.is_active.is_(True),
        )
        .order_by(FinanceCenterMumarenAccount.account_code)
    )
    period_start, period_end = _period_bounds(period)
    if start_date is None:
        start_date = period_start
    if end_date is None:
        end_date = period_end
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    statement = (
        select(FinanceCenterMumarenVoucherLine)
        .join(
            FinanceCenterMumarenVoucher,
            FinanceCenterMumarenVoucherLine.voucher_id == FinanceCenterMumarenVoucher.id,
        )
        .where(
            FinanceCenterMumarenVoucher.book_id == book_id,
            FinanceCenterMumarenVoucher.status == "posted",
        )
        .order_by(FinanceCenterMumarenVoucher.voucher_date, FinanceCenterMumarenVoucherLine.line_no)
    )
    if start_date is not None and end_date is not None:
        statement = statement.where(FinanceCenterMumarenVoucher.voucher_date.between(start_date, end_date))
    lines_result = await db.execute(statement)
    return list(accounts_result.scalars()), list(lines_result.scalars())


# ---------------------------------------------------------------------------
# Task 15/16/17: CRUD 表聚合辅助函数
# ---------------------------------------------------------------------------

async def _aggregate_expense_entries(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> list[dict]:
    """已过账费用明细按 account_code 聚合，返回 extra_expenses 列表。"""
    statement = (
        select(FinanceCenterMumarenExpenseEntry)
        .where(
            FinanceCenterMumarenExpenseEntry.book_id == book_id,
            FinanceCenterMumarenExpenseEntry.workflow_status == "posted",
        )
    )
    if period is not None:
        statement = statement.where(FinanceCenterMumarenExpenseEntry.period == period)
    result = await db.execute(statement)
    grouped: dict[str, dict] = {}
    for entry in result.scalars():
        code = str(entry.account_code or "")
        bucket = grouped.setdefault(code, {
            "account_code": code,
            "account_name": entry.account_name,
            "amount": _ZERO,
        })
        bucket["amount"] += Decimal(str(entry.amount or _ZERO))
    return list(grouped.values())


async def _aggregate_paid_payrolls(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> Decimal:
    """已发放工资（workflow_status='paid'）gross_amount 合计。"""
    statement = select(
        FinanceCenterMumarenPayroll.gross_amount,
    ).where(
        FinanceCenterMumarenPayroll.book_id == book_id,
        FinanceCenterMumarenPayroll.workflow_status == "paid",
    )
    if period is not None:
        statement = statement.where(FinanceCenterMumarenPayroll.period == period)
    result = await db.execute(statement)
    return sum((Decimal(str(row[0] or _ZERO)) for row in result.all()), _ZERO)


async def _aggregate_unpaid_payrolls(
    db: AsyncSession, *, book_id: int
) -> Decimal:
    """未发放工资（workflow_status='draft'）gross_amount 合计，计入应付职工薪酬。"""
    statement = select(
        FinanceCenterMumarenPayroll.gross_amount,
    ).where(
        FinanceCenterMumarenPayroll.book_id == book_id,
        FinanceCenterMumarenPayroll.workflow_status == "draft",
    )
    result = await db.execute(statement)
    return sum((Decimal(str(row[0] or _ZERO)) for row in result.all()), _ZERO)


async def _aggregate_fixed_asset_depreciation(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> Decimal:
    """固定资产当期月折旧额合计（按月计提，封顶在可折旧额）。"""
    statement = select(FinanceCenterMumarenFixedAsset).where(
        FinanceCenterMumarenFixedAsset.book_id == book_id,
        FinanceCenterMumarenFixedAsset.status == "active",
    )
    result = await db.execute(statement)
    total = _ZERO
    for asset in result.scalars():
        try:
            monthly = depreciation_for_period(
                original_value=asset.original_value,
                residual_value=asset.residual_value,
                useful_life_months=asset.useful_life_months,
                already_depreciated=asset.accumulated_depreciation,
            )
        except ValueError:
            continue
        total += monthly
    return total


async def _aggregate_fixed_assets_net(
    db: AsyncSession, *, book_id: int
) -> Decimal:
    """固定资产净值合计 = Σ(original_value - accumulated_depreciation)。"""
    statement = select(FinanceCenterMumarenFixedAsset).where(
        FinanceCenterMumarenFixedAsset.book_id == book_id,
        FinanceCenterMumarenFixedAsset.status == "active",
    )
    result = await db.execute(statement)
    total = _ZERO
    for asset in result.scalars():
        original = Decimal(str(asset.original_value or _ZERO))
        accumulated = Decimal(str(asset.accumulated_depreciation or _ZERO))
        total += original - accumulated
    return total


async def _aggregate_invoices(
    db: AsyncSession, *, book_id: int
) -> dict:
    """发票按应收/应付聚合。

    返回::

        {
            "receivable_amount": Decimal,  # 应收金额合计
            "receivable_tax": Decimal,     # 应收税额合计
            "payable_amount": Decimal,     # 应付金额合计
        }
    """
    statement = select(FinanceCenterMumarenInvoice).where(
        FinanceCenterMumarenInvoice.book_id == book_id,
    )
    result = await db.execute(statement)
    receivable_amount = _ZERO
    receivable_tax = _ZERO
    payable_amount = _ZERO
    for invoice in result.scalars():
        classification = _classify_invoice(invoice.invoice_type or "")
        amount = Decimal(str(invoice.amount or _ZERO))
        tax = Decimal(str(invoice.tax_amount or _ZERO))
        if classification == "receivable":
            receivable_amount += amount
            receivable_tax += tax
        elif classification == "payable":
            payable_amount += amount
    return {
        "receivable_amount": receivable_amount,
        "receivable_tax": receivable_tax,
        "payable_amount": payable_amount,
    }


async def _aggregate_cash_flows(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> list[dict]:
    """已过账现金流水按 category/direction 聚合为 build_cash_flow_statement 所需记录。"""
    start_date, end_date = _period_bounds(period)
    statement = select(FinanceCenterMumarenCashFlow).where(
        FinanceCenterMumarenCashFlow.book_id == book_id,
        FinanceCenterMumarenCashFlow.workflow_status == "posted",
    )
    if start_date is not None and end_date is not None:
        statement = statement.where(
            FinanceCenterMumarenCashFlow.flow_date.between(start_date, end_date)
        )
    result = await db.execute(statement)
    records: list[dict] = []
    for flow in result.scalars():
        records.append({
            "category": flow.category or "operating",
            "direction": flow.direction,
            "amount": Decimal(str(flow.amount or _ZERO)),
        })
    return records


async def _collect_extra_expenses(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> list[dict]:
    """Task 15: 汇总 expense_entries / payrolls / fixed_assets 录入的费用。"""
    extras: list[dict] = []
    # 1. 已过账费用明细（按用户填写的 account_code/name 分组）
    extras.extend(await _aggregate_expense_entries(db, book_id=book_id, period=period))
    # 2. 已发放工资 → 管理费用-工资
    payroll_total = await _aggregate_paid_payrolls(db, book_id=book_id, period=period)
    if payroll_total != _ZERO:
        extras.append({
            "account_code": "660201",
            "account_name": "管理费用-工资",
            "amount": payroll_total,
        })
    # 3. 固定资产当期折旧 → 管理费用-折旧
    depreciation_total = await _aggregate_fixed_asset_depreciation(
        db, book_id=book_id, period=period
    )
    if depreciation_total != _ZERO:
        extras.append({
            "account_code": "660202",
            "account_name": "管理费用-折旧",
            "amount": depreciation_total,
        })
    return extras


async def _collect_balance_adjustments(
    db: AsyncSession, *, book_id: int
) -> list[dict]:
    """Task 16: 汇总 payrolls / fixed_assets / invoices 的资产负债表调整项。"""
    adjustments: list[dict] = []
    # 1. 未发放工资 → 应付职工薪酬（贷方余额）
    unpaid_payroll = await _aggregate_unpaid_payrolls(db, book_id=book_id)
    if unpaid_payroll != _ZERO:
        adjustments.append({
            "account_code": "2202",
            "account_name": "应付职工薪酬",
            "account_type": "liability",
            "direction": "credit",
            "debit_amount": _ZERO,
            "credit_amount": unpaid_payroll,
        })
    # 2. 固定资产净值 → 固定资产（借方余额）
    fixed_asset_net = await _aggregate_fixed_assets_net(db, book_id=book_id)
    if fixed_asset_net != _ZERO:
        adjustments.append({
            "account_code": "1601",
            "account_name": "固定资产",
            "account_type": "asset",
            "direction": "debit",
            "debit_amount": fixed_asset_net,
            "credit_amount": _ZERO,
        })
    # 3. 发票 → 应收账款 / 应收税额 / 应付账款
    invoice_totals = await _aggregate_invoices(db, book_id=book_id)
    if invoice_totals["receivable_amount"] != _ZERO:
        adjustments.append({
            "account_code": "1122",
            "account_name": "应收账款",
            "account_type": "asset",
            "direction": "debit",
            "debit_amount": invoice_totals["receivable_amount"],
            "credit_amount": _ZERO,
        })
    if invoice_totals["receivable_tax"] != _ZERO:
        adjustments.append({
            "account_code": "1131",
            "account_name": "应收税额",
            "account_type": "asset",
            "direction": "debit",
            "debit_amount": invoice_totals["receivable_tax"],
            "credit_amount": _ZERO,
        })
    if invoice_totals["payable_amount"] != _ZERO:
        adjustments.append({
            "account_code": "2202",
            "account_name": "应付账款",
            "account_type": "liability",
            "direction": "credit",
            "debit_amount": _ZERO,
            "credit_amount": invoice_totals["payable_amount"],
        })
    return adjustments


async def get_trial_balance(
    db: AsyncSession, *, book_id: int, period: str | None = None,
    start_date: date | None = None, end_date: date | None = None,
) -> dict:
    accounts, posted_lines = await _load_posted_book_data(
        db, book_id=book_id, period=period, start_date=start_date, end_date=end_date,
    )
    adjustments = await _collect_balance_adjustments(db, book_id=book_id)
    return build_trial_balance(accounts, posted_lines, extra_adjustments=adjustments)


async def get_profit_statement(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> dict:
    accounts, posted_lines = await _load_posted_book_data(db, book_id=book_id, period=period)
    extras = await _collect_extra_expenses(db, book_id=book_id, period=period)
    return build_profit_statement(accounts, posted_lines, extra_expenses=extras)


async def get_cash_flow_statement(
    db: AsyncSession, *, book_id: int, period: str | None = None
) -> dict:
    """Task 17: 现金流量表，联动已过账 cash_flows。"""
    accounts, posted_lines = await _load_posted_book_data(db, book_id=book_id, period=period)
    cash_flow_records = await _aggregate_cash_flows(db, book_id=book_id, period=period)
    return build_cash_flow_statement(accounts, posted_lines, cash_flow_records=cash_flow_records)
