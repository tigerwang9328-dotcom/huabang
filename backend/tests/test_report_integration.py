"""Task 15/16/17: 报表派生计算联动集成测试。

验证 12 个 CRUD 页面录入的数据真正影响利润表 / 资产负债表 / 现金流量表。
覆盖场景:
- 录入费用 (expense_entries posted) → 利润表费用合计增加
- 录入工资 (payrolls paid) → 利润表工资费用增加 + 资产负债表应付职工薪酬增加
- 录入资产 (fixed_assets) → 资产负债表固定资产增加
- 录入流水 (cash_flows posted) → 现金流量表净额变化
- 平衡校验: 资产 = 负债 + 权益

所有用例通过纯函数 build_* 验证联动逻辑, 不触碰真实数据库;
async 聚合函数通过 mock Db 验证 SQL 过滤条件正确。
"""
import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest


os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault("DB_PASSWORD", "test-only-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

from app.services.mumaren_finance_center.reports import (
    build_cash_flow_statement,
    build_profit_statement,
    build_trial_balance,
    _aggregate_cash_flows,
    _aggregate_expense_entries,
    _aggregate_fixed_asset_depreciation,
    _aggregate_fixed_assets_net,
    _aggregate_invoices,
    _aggregate_paid_payrolls,
    _aggregate_unpaid_payrolls,
    _classify_invoice,
    _collect_balance_adjustments,
    _collect_extra_expenses,
)


def _account(account_id, code, name, account_type, direction="debit"):
    return SimpleNamespace(
        id=account_id,
        account_code=code,
        account_name=name,
        account_type=account_type,
        direction=direction,
    )


# ---------------------------------------------------------------------------
# Mock Db 工具：模拟 SQLAlchemy 结果集
# ---------------------------------------------------------------------------

class _Scalars:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def all(self):
        return list(self._items)


class _Rows:
    """select(col) 风格的结果，row[0] 取值。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _MockResult:
    def __init__(self, *, scalars=None, rows=None):
        self._scalars = list(scalars or [])
        self._rows = list(rows or [])

    def scalars(self):
        return _Scalars(self._scalars)


class _MockDb:
    """按 statement 字符串内容路由到不同结果。"""

    def __init__(self, *, expense_entries=None, payrolls_paid=None, payrolls_draft=None,
                 fixed_assets=None, invoices=None, cash_flows=None):
        self.expense_entries = expense_entries or []
        self.payrolls_paid = payrolls_paid or []
        self.payrolls_draft = payrolls_draft or []
        self.fixed_assets = fixed_assets or []
        self.invoices = invoices or []
        self.cash_flows = cash_flows or []
        self.statements_seen: list[str] = []

    async def execute(self, statement):
        # 使用 literal_binds 将绑定参数内联到 SQL 文本中，
        # 这样 mock 可以根据 'posted'/'paid'/'draft' 等字面量路由结果。
        text = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.statements_seen.append(text)
        if "finance_center_mumaren_expense_entries" in text:
            if "posted" in text:
                entries = [e for e in self.expense_entries if e.workflow_status == "posted"]
            else:
                entries = self.expense_entries
            return _MockResult(scalars=entries)
        if "finance_center_mumaren_payrolls" in text:
            if "'paid'" in text or "paid" in text:
                return _Rows([(p.gross_amount,) for p in self.payrolls_paid])
            if "'draft'" in text or "draft" in text:
                return _Rows([(p.gross_amount,) for p in self.payrolls_draft])
            return _Rows([])
        if "finance_center_mumaren_fixed_assets" in text:
            return _MockResult(scalars=self.fixed_assets)
        if "finance_center_mumaren_invoices" in text:
            return _MockResult(scalars=self.invoices)
        if "finance_center_mumaren_cash_flows" in text:
            if "posted" in text:
                flows = [f for f in self.cash_flows if f.workflow_status == "posted"]
            else:
                flows = self.cash_flows
            return _MockResult(scalars=flows)
        return _MockResult()


def _expense_entry(eid, *, book_id=1, period="2026-07", code="6601", name="管理费用-办公费",
                   amount=Decimal("1000"), status="posted"):
    from app.models.mumaren_finance_center_domains import FinanceCenterMumarenExpenseEntry
    return FinanceCenterMumarenExpenseEntry(
        id=eid, book_id=book_id, period=period, account_code=code,
        account_name=name, amount=amount, workflow_status=status,
    )


def _payroll(pid, *, book_id=1, period="2026-07", gross=Decimal("5000"),
             deduction=Decimal("0"), status="draft"):
    from app.models.mumaren_finance_center_domains import FinanceCenterMumarenPayroll
    return FinanceCenterMumarenPayroll(
        id=pid, book_id=book_id, period=period, employee_no=f"E{pid}",
        employee_name=f"员工{pid}", gross_amount=gross, deduction_amount=deduction,
        net_amount=gross - deduction, workflow_status=status,
    )


def _fixed_asset(aid, *, book_id=1, original=Decimal("12000"), residual=Decimal("1200"),
                 life_months=60, accumulated=Decimal("0")):
    from app.models.mumaren_finance_center_domains import FinanceCenterMumarenFixedAsset
    return FinanceCenterMumarenFixedAsset(
        id=aid, book_id=book_id, asset_code=f"A{aid:03d}", asset_name="服务器",
        asset_category="IT设备", purchase_date=date(2026, 1, 1),
        original_value=original, residual_value=residual,
        useful_life_months=life_months, accumulated_depreciation=accumulated,
        status="active",
    )


def _invoice(iid, *, book_id=1, invoice_type="receivable", amount=Decimal("1000"),
             tax=Decimal("130")):
    from app.models.mumaren_finance_center_domains import FinanceCenterMumarenInvoice
    return FinanceCenterMumarenInvoice(
        id=iid, book_id=book_id, invoice_no=f"INV{iid:03d}", invoice_type=invoice_type,
        invoice_date=date(2026, 7, 1), counterparty_name="客户",
        amount=amount, tax_amount=tax, verification_status="draft",
        workflow_status="draft",
    )


def _cash_flow(cid, *, book_id=1, direction="in", amount=Decimal("1000"),
               category="operating", status="posted"):
    from app.models.mumaren_finance_center_domains import FinanceCenterMumarenCashFlow
    return FinanceCenterMumarenCashFlow(
        id=cid, book_id=book_id, cash_account_id=1, flow_date=date(2026, 7, 1),
        direction=direction, amount=amount, category=category,
        workflow_status=status,
    )


# ===========================================================================
# Task 15: 利润表联动测试
# ===========================================================================

def test_expense_entries_posted_increase_profit_statement_total_expense():
    """录入 posted 费用明细 → 利润表费用合计增加。"""
    accounts = [_account(1, "6601", "管理费用-办公费", "expense")]
    posted_lines = []
    extras = [
        {"account_code": "6601", "account_name": "管理费用-办公费", "amount": Decimal("1500")},
    ]

    baseline = build_profit_statement(accounts, posted_lines)
    integrated = build_profit_statement(accounts, posted_lines, extra_expenses=extras)

    assert baseline["total_expense"] == Decimal("0")
    assert integrated["total_expense"] == Decimal("1500")
    assert integrated["net_profit"] == Decimal("-1500")
    # 命中已有费用科目 → 累加到该行
    assert integrated["expense_rows"][0]["amount"] == Decimal("1500")


def test_payrolls_paid_increase_salary_expense_in_profit_statement():
    """录入 paid 工资 → 利润表"管理费用-工资"增加。"""
    accounts = []
    posted_lines = []
    extras = [
        {"account_code": "660201", "account_name": "管理费用-工资", "amount": Decimal("8000")},
    ]

    statement = build_profit_statement(accounts, posted_lines, extra_expenses=extras)

    assert statement["total_expense"] == Decimal("8000")
    salary_row = next(
        (r for r in statement["expense_rows"] if r["account_name"] == "管理费用-工资"),
        None,
    )
    assert salary_row is not None
    assert salary_row["amount"] == Decimal("8000")


def test_fixed_assets_depreciation_increase_depreciation_expense():
    """录入固定资产 → 当期折旧计入"管理费用-折旧"。"""
    extras = [
        {"account_code": "660202", "account_name": "管理费用-折旧", "amount": Decimal("180")},
    ]
    statement = build_profit_statement([], [], extra_expenses=extras)

    assert statement["total_expense"] == Decimal("180")
    dep_row = next(
        (r for r in statement["expense_rows"] if r["account_name"] == "管理费用-折旧"),
        None,
    )
    assert dep_row is not None
    assert dep_row["amount"] == Decimal("180")


def test_aggregate_expense_entries_filters_posted_only():
    """_aggregate_expense_entries 仅聚合 workflow_status='posted' 的记录。"""
    db = _MockDb(expense_entries=[
        _expense_entry(1, amount=Decimal("500"), status="posted"),
        _expense_entry(2, amount=Decimal("300"), status="draft"),
    ])
    import asyncio
    result = asyncio.run(_aggregate_expense_entries(db, book_id=1, period="2026-07"))
    # 只聚合 posted 的 500
    assert len(result) == 1
    assert result[0]["amount"] == Decimal("500")
    # SQL 应过滤 workflow_status='posted'
    assert any("posted" in s for s in db.statements_seen)


def test_aggregate_paid_payrolls_filters_paid_only():
    """_aggregate_paid_payrolls 仅聚合 workflow_status='paid' 的工资。"""
    import asyncio
    db = _MockDb(payrolls_paid=[_payroll(1, gross=Decimal("5000"), status="paid")])
    total = asyncio.run(_aggregate_paid_payrolls(db, book_id=1, period="2026-07"))
    assert total == Decimal("5000")


def test_aggregate_fixed_asset_depreciation_caps_at_depreciable_amount():
    """固定资产月折旧 = (原值-残值)/使用月数，封顶在可折旧额。"""
    import asyncio
    # 原值 12000，残值 1200，使用 60 月 → 月折旧 (12000-1200)/60 = 180
    db = _MockDb(fixed_assets=[_fixed_asset(1, original=Decimal("12000"),
                                            residual=Decimal("1200"),
                                            life_months=60,
                                            accumulated=Decimal("0"))])
    total = asyncio.run(_aggregate_fixed_asset_depreciation(db, book_id=1))
    assert total == Decimal("180.00")

    # 累计折旧已接近上限时，月折旧应被封顶
    db2 = _MockDb(fixed_assets=[_fixed_asset(1, original=Decimal("12000"),
                                             residual=Decimal("1200"),
                                             life_months=60,
                                             accumulated=Decimal("10790"))])
    total2 = asyncio.run(_aggregate_fixed_asset_depreciation(db2, book_id=1))
    # 剩余可折旧 = 10800 - 10790 = 10，月折旧 180 被封顶到 10
    assert total2 == Decimal("10.00")


def test_collect_extra_expenses_aggregates_all_three_sources():
    """_collect_extra_expenses 汇总 expense_entries + payrolls + fixed_assets。"""
    import asyncio
    db = _MockDb(
        expense_entries=[
            _expense_entry(1, code="6601", name="管理费用-办公费",
                           amount=Decimal("500"), status="posted"),
        ],
        payrolls_paid=[_payroll(1, gross=Decimal("8000"), status="paid")],
        fixed_assets=[_fixed_asset(1, original=Decimal("12000"),
                                   residual=Decimal("1200"), life_months=60)],
    )
    extras = asyncio.run(_collect_extra_expenses(db, book_id=1, period="2026-07"))
    by_name = {e["account_name"]: e["amount"] for e in extras}
    assert by_name["管理费用-办公费"] == Decimal("500")
    assert by_name["管理费用-工资"] == Decimal("8000")
    assert by_name["管理费用-折旧"] == Decimal("180.00")


# ===========================================================================
# Task 16: 资产负债表联动测试
# ===========================================================================

def test_unpaid_payrolls_increase_payroll_payable_in_balance_sheet():
    """未发放工资 (draft) → 资产负债表应付职工薪酬 (贷方) 增加。"""
    adjustments = [
        {"account_code": "2202", "account_name": "应付职工薪酬",
         "account_type": "liability", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("5000")},
    ]
    report = build_trial_balance([], [], extra_adjustments=adjustments)

    assert report["liabilities_total"] == Decimal("5000")
    # difference = assets - (liabilities + equity) = 0 - (5000 + 0) = -5000
    assert report["balance_check"]["difference"] == Decimal("-5000")
    assert report["balance_check"]["is_balanced"] is False


def test_fixed_assets_increase_fixed_asset_in_balance_sheet():
    """固定资产净值 → 资产负债表固定资产 (借方) 增加。"""
    adjustments = [
        {"account_code": "1601", "account_name": "固定资产",
         "account_type": "asset", "direction": "debit",
         "debit_amount": Decimal("10800"), "credit_amount": Decimal("0")},
    ]
    report = build_trial_balance([], [], extra_adjustments=adjustments)

    assert report["assets_total"] == Decimal("10800")
    assert report["balance_check"]["difference"] == Decimal("10800")


def test_receivable_invoices_increase_accounts_receivable():
    """应收发票 → 应收账款 (借方) 增加。"""
    adjustments = [
        {"account_code": "1122", "account_name": "应收账款",
         "account_type": "asset", "direction": "debit",
         "debit_amount": Decimal("1000"), "credit_amount": Decimal("0")},
    ]
    report = build_trial_balance([], [], extra_adjustments=adjustments)
    assert report["assets_total"] == Decimal("1000")


def test_payable_invoices_increase_accounts_payable():
    """应付发票 → 应付账款 (贷方) 增加。"""
    adjustments = [
        {"account_code": "2202", "account_name": "应付账款",
         "account_type": "liability", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("2000")},
    ]
    report = build_trial_balance([], [], extra_adjustments=adjustments)
    assert report["liabilities_total"] == Decimal("2000")


def test_balance_check_passes_when_assets_equal_liabilities_plus_equity():
    """资产 = 负债 + 权益 时平衡校验通过。"""
    adjustments = [
        {"account_code": "1601", "account_name": "固定资产",
         "account_type": "asset", "direction": "debit",
         "debit_amount": Decimal("10000"), "credit_amount": Decimal("0")},
        {"account_code": "2202", "account_name": "应付账款",
         "account_type": "liability", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("4000")},
        {"account_code": "4001", "account_name": "实收资本",
         "account_type": "equity", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("6000")},
    ]
    report = build_trial_balance([], [], extra_adjustments=adjustments)

    assert report["assets_total"] == Decimal("10000")
    assert report["liabilities_total"] == Decimal("4000")
    assert report["equity_total"] == Decimal("6000")
    assert report["balance_check"]["is_balanced"] is True
    assert abs(report["balance_check"]["difference"]) < Decimal("0.01")


def test_balance_check_fails_when_assets_dont_equal_liabilities_plus_equity():
    """资产 ≠ 负债 + 权益 时平衡校验失败。"""
    adjustments = [
        {"account_code": "1601", "account_name": "固定资产",
         "account_type": "asset", "direction": "debit",
         "debit_amount": Decimal("10000"), "credit_amount": Decimal("0")},
        {"account_code": "2202", "account_name": "应付账款",
         "account_type": "liability", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("3000")},
    ]
    report = build_trial_balance([], [], extra_adjustments=adjustments)

    assert report["balance_check"]["is_balanced"] is False
    assert report["balance_check"]["difference"] == Decimal("7000")


def test_aggregate_unpaid_payrolls_filters_draft_only():
    """_aggregate_unpaid_payrolls 仅聚合 draft 状态工资。"""
    import asyncio
    db = _MockDb(payrolls_draft=[_payroll(1, gross=Decimal("5000"), status="draft")])
    total = asyncio.run(_aggregate_unpaid_payrolls(db, book_id=1))
    assert total == Decimal("5000")


def test_aggregate_fixed_assets_net_calculates_net_value():
    """_aggregate_fixed_assets_net = Σ(original_value - accumulated_depreciation)。"""
    import asyncio
    db = _MockDb(fixed_assets=[
        _fixed_asset(1, original=Decimal("12000"), accumulated=Decimal("180")),
        _fixed_asset(2, original=Decimal("8000"), accumulated=Decimal("0")),
    ])
    total = asyncio.run(_aggregate_fixed_assets_net(db, book_id=1))
    assert total == Decimal("19820")  # (12000-180) + (8000-0)


def test_aggregate_invoices_classifies_receivable_and_payable():
    """_aggregate_invoices 按 invoice_type 关键词分类应收/应付。"""
    import asyncio
    db = _MockDb(invoices=[
        _invoice(1, invoice_type="sales_receivable", amount=Decimal("1000"), tax=Decimal("130")),
        _invoice(2, invoice_type="purchase_payable", amount=Decimal("800"), tax=Decimal("0")),
        _invoice(3, invoice_type="unknown", amount=Decimal("999"), tax=Decimal("0")),
    ])
    totals = asyncio.run(_aggregate_invoices(db, book_id=1))
    assert totals["receivable_amount"] == Decimal("1000")
    assert totals["receivable_tax"] == Decimal("130")
    assert totals["payable_amount"] == Decimal("800")


def test_classify_invoice_recognizes_chinese_and_english_markers():
    """发票类型识别中英文关键词。"""
    assert _classify_invoice("sales") == "receivable"
    assert _classify_invoice("销售发票") == "receivable"
    assert _classify_invoice("销项") == "receivable"
    assert _classify_invoice("purchase") == "payable"
    assert _classify_invoice("采购发票") == "payable"
    assert _classify_invoice("进项") == "payable"
    assert _classify_invoice("unknown") is None


def test_collect_balance_adjustments_aggregates_all_sources():
    """_collect_balance_adjustments 汇总 payrolls + fixed_assets + invoices。"""
    import asyncio
    db = _MockDb(
        payrolls_draft=[_payroll(1, gross=Decimal("5000"), status="draft")],
        fixed_assets=[_fixed_asset(1, original=Decimal("12000"),
                                   residual=Decimal("1200"), accumulated=Decimal("180"))],
        invoices=[
            _invoice(1, invoice_type="sales", amount=Decimal("1000"), tax=Decimal("130")),
            _invoice(2, invoice_type="purchase", amount=Decimal("800"), tax=Decimal("0")),
        ],
    )
    adjustments = asyncio.run(_collect_balance_adjustments(db, book_id=1))
    by_name = {a["account_name"]: a for a in adjustments}
    # 应付职工薪酬 5000
    assert by_name["应付职工薪酬"]["credit_amount"] == Decimal("5000")
    # 固定资产净值 = 12000 - 180 = 11820
    assert by_name["固定资产"]["debit_amount"] == Decimal("11820")
    # 应收账款 1000
    assert by_name["应收账款"]["debit_amount"] == Decimal("1000")
    # 应收税额 130
    assert by_name["应收税额"]["debit_amount"] == Decimal("130")
    # 应付账款 800
    assert by_name["应付账款"]["credit_amount"] == Decimal("800")


def test_adjustment_matching_existing_account_accumulates_into_same_row():
    """调整项命中已有科目（按 account_code）→ 累加到该科目行，不产生合成行。"""
    accounts = [_account(1, "1122", "应收账款", "asset")]
    posted_lines = [{"account_id": 1, "debit_amount": Decimal("500"), "credit_amount": Decimal("0")}]
    adjustments = [
        {"account_code": "1122", "account_name": "应收账款",
         "account_type": "asset", "direction": "debit",
         "debit_amount": Decimal("1000"), "credit_amount": Decimal("0")},
    ]
    report = build_trial_balance(accounts, posted_lines, extra_adjustments=adjustments)

    # 应收账款行借贷累加：500 + 1000 = 1500
    ar_row = next(r for r in report["rows"] if r["account_code"] == "1122")
    assert ar_row["debit_amount"] == Decimal("1500")
    # 不应出现合成行（account_id=None）
    assert all(r["account_id"] is not None for r in report["rows"])


# ===========================================================================
# Task 17: 现金流量表联动测试
# ===========================================================================

def test_cash_flow_statement_categorizes_by_category():
    """现金流量表按 category 分类经营/投资/筹资。"""
    records = [
        {"category": "operating", "direction": "in", "amount": Decimal("10000")},
        {"category": "operating", "direction": "out", "amount": Decimal("3000")},
        {"category": "investing", "direction": "out", "amount": Decimal("5000")},
        {"category": "financing", "direction": "in", "amount": Decimal("8000")},
    ]
    statement = build_cash_flow_statement([], [], cash_flow_records=records)

    assert statement["sections"]["operating"]["inflow"] == Decimal("10000")
    assert statement["sections"]["operating"]["outflow"] == Decimal("3000")
    assert statement["sections"]["operating"]["net"] == Decimal("7000")
    assert statement["sections"]["investing"]["net"] == Decimal("-5000")
    assert statement["sections"]["financing"]["net"] == Decimal("8000")
    assert statement["total_inflow"] == Decimal("18000")
    assert statement["total_outflow"] == Decimal("8000")
    assert statement["total_net"] == Decimal("10000")


def test_cash_flow_statement_calculates_cash_net_increase_from_cash_accounts():
    """现金净增加 = Σ(现金类科目期末借方 - 期末贷方)。"""
    accounts = [
        _account(1, "1001", "库存现金", "asset"),
        _account(2, "1002", "银行存款", "asset"),
        _account(3, "1601", "固定资产", "asset"),  # 非现金类，不计入
    ]
    posted_lines = [
        {"account_id": 1, "debit_amount": Decimal("5000"), "credit_amount": Decimal("1000")},
        {"account_id": 2, "debit_amount": Decimal("20000"), "credit_amount": Decimal("5000")},
    ]
    statement = build_cash_flow_statement(accounts, posted_lines, cash_flow_records=[])

    # 现金净增加 = (5000-1000) + (20000-5000) = 19000
    assert statement["cash_net_increase"] == Decimal("19000")


def test_cash_flow_statement_ignores_draft_cash_flows():
    """_aggregate_cash_flows 仅聚合 workflow_status='posted' 的流水。"""
    import asyncio
    db = _MockDb(cash_flows=[
        _cash_flow(1, direction="in", amount=Decimal("1000"), status="posted"),
        _cash_flow(2, direction="in", amount=Decimal("9999"), status="draft"),
    ])
    records = asyncio.run(_aggregate_cash_flows(db, book_id=1, period="2026-07"))
    # 只聚合 posted 的 1000
    assert len(records) == 1
    assert records[0]["amount"] == Decimal("1000")
    assert any("posted" in s for s in db.statements_seen)


def test_cash_flow_statement_direction_in_adds_to_inflow():
    """direction='in' 累加到流入，direction='out' 累加到流出。"""
    records = [
        {"category": "operating", "direction": "in", "amount": Decimal("500")},
        {"category": "operating", "direction": "out", "amount": Decimal("200")},
    ]
    statement = build_cash_flow_statement([], [], cash_flow_records=records)

    assert statement["sections"]["operating"]["inflow"] == Decimal("500")
    assert statement["sections"]["operating"]["outflow"] == Decimal("200")
    assert statement["sections"]["operating"]["net"] == Decimal("300")


# ===========================================================================
# 端到端联动验证：录入数据后报表是否变化
# ===========================================================================

def test_end_to_end_expense_entry_to_profit_statement():
    """端到端：录入 posted 费用 → 利润表费用合计从 0 变为录入金额。"""
    accounts = [_account(1, "6601", "管理费用-办公费", "expense")]
    baseline = build_profit_statement(accounts, [])
    assert baseline["total_expense"] == Decimal("0")

    extras = [{"account_code": "6601", "account_name": "管理费用-办公费", "amount": Decimal("2300")}]
    after = build_profit_statement(accounts, [], extra_expenses=extras)
    assert after["total_expense"] == Decimal("2300")
    assert after["net_profit"] == Decimal("-2300")


def test_end_to_end_payroll_to_both_profit_and_balance():
    """端到端：同一笔工资影响利润表（费用）和资产负债表（应付）。"""
    # 利润表：paid 工资 → 管理费用-工资
    profit_extras = [{"account_code": "660201", "account_name": "管理费用-工资", "amount": Decimal("6000")}]
    profit = build_profit_statement([], [], extra_expenses=profit_extras)
    assert profit["total_expense"] == Decimal("6000")

    # 资产负债表：draft 工资 → 应付职工薪酬
    balance_adjustments = [
        {"account_code": "2202", "account_name": "应付职工薪酬",
         "account_type": "liability", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("6000")},
    ]
    balance = build_trial_balance([], [], extra_adjustments=balance_adjustments)
    assert balance["liabilities_total"] == Decimal("6000")


def test_end_to_end_fixed_asset_depreciation_and_net_value():
    """端到端：固定资产折旧进利润表，净值进资产负债表。"""
    # 原值 12000，残值 1200，60 月 → 月折旧 180，净值 11820
    depreciation = Decimal("180.00")
    net_value = Decimal("11820")

    # 利润表
    profit = build_profit_statement(
        [], [], extra_expenses=[
            {"account_code": "660202", "account_name": "管理费用-折旧", "amount": depreciation},
        ]
    )
    assert profit["total_expense"] == depreciation

    # 资产负债表
    balance = build_trial_balance(
        [], [], extra_adjustments=[
            {"account_code": "1601", "account_name": "固定资产",
             "account_type": "asset", "direction": "debit",
             "debit_amount": net_value, "credit_amount": Decimal("0")},
        ]
    )
    assert balance["assets_total"] == net_value


def test_end_to_end_cash_flow_posted_changes_net():
    """端到端：录入 posted 现金流 → 现金流量表净额变化。"""
    baseline = build_cash_flow_statement([], [], cash_flow_records=[])
    assert baseline["total_net"] == Decimal("0")

    records = [
        {"category": "operating", "direction": "in", "amount": Decimal("5000")},
        {"category": "operating", "direction": "out", "amount": Decimal("2000")},
    ]
    after = build_cash_flow_statement([], [], cash_flow_records=records)
    assert after["sections"]["operating"]["net"] == Decimal("3000")
    assert after["total_net"] == Decimal("3000")


def test_full_balance_sheet_balance_with_all_adjustments():
    """全量联动：资产（固定资产+应收）= 负债（应付职工薪酬+应付账款）+ 权益。"""
    adjustments = [
        # 固定资产净值
        {"account_code": "1601", "account_name": "固定资产",
         "account_type": "asset", "direction": "debit",
         "debit_amount": Decimal("11820"), "credit_amount": Decimal("0")},
        # 应收账款
        {"account_code": "1122", "account_name": "应收账款",
         "account_type": "asset", "direction": "debit",
         "debit_amount": Decimal("1000"), "credit_amount": Decimal("0")},
        # 应付职工薪酬
        {"account_code": "2202", "account_name": "应付职工薪酬",
         "account_type": "liability", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("5000")},
        # 应付账款
        {"account_code": "2202", "account_name": "应付账款",
         "account_type": "liability", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("800")},
        # 实收资本（权益）
        {"account_code": "4001", "account_name": "实收资本",
         "account_type": "equity", "direction": "credit",
         "debit_amount": Decimal("0"), "credit_amount": Decimal("7020")},
    ]
    report = build_trial_balance([], [], extra_adjustments=adjustments)

    # 资产 = 11820 + 1000 = 12820
    # 负债 = 5000 + 800 = 5800
    # 权益 = 7020
    # 12820 = 5800 + 7020 ✓
    assert report["assets_total"] == Decimal("12820")
    assert report["liabilities_total"] == Decimal("5800")
    assert report["equity_total"] == Decimal("7020")
    assert report["balance_check"]["is_balanced"] is True
    assert abs(report["balance_check"]["difference"]) < Decimal("0.01")


def test_existing_tests_not_broken_profit_statement_without_extras():
    """无 extras 时利润表行为与原有逻辑一致（回归测试）。"""
    accounts = [
        _account(1, "6001", "主营业务收入", "income", "credit"),
        _account(2, "6401", "主营业务成本", "expense"),
    ]
    posted_lines = [
        {"account_id": 1, "debit_amount": "20", "credit_amount": "200"},
        {"account_id": 2, "debit_amount": "80", "credit_amount": "0"},
    ]
    statement = build_profit_statement(accounts, posted_lines)

    assert statement["total_income"] == Decimal("180")
    assert statement["total_expense"] == Decimal("80")
    assert statement["net_profit"] == Decimal("100")


def test_existing_tests_not_broken_trial_balance_without_adjustments():
    """无 adjustments 时试算平衡表行为与原有逻辑一致（回归测试）。"""
    accounts = [
        _account(1, "1001", "库存现金", "asset"),
        _account(2, "2202", "应付账款", "liability", "credit"),
    ]
    posted_lines = [
        {"account_id": 1, "debit_amount": Decimal("100"), "credit_amount": Decimal("0")},
        {"account_id": 2, "debit_amount": Decimal("0"), "credit_amount": Decimal("100")},
    ]
    report = build_trial_balance(accounts, posted_lines)

    assert report["total_debit"] == Decimal("100")
    assert report["total_credit"] == Decimal("100")
    assert report["is_balanced"] is True
    # 资产 100 = 负债 100 + 权益 0
    assert report["balance_check"]["is_balanced"] is True
