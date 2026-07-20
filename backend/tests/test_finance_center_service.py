from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.models.finance_core import (
    FinAccount,
    FinBook,
    FinLedgerBalance,
    FinSourceLink,
    FinStatementLine,
    FinStatementMapping,
    FinVoucher,
    FinVoucherEntry,
    FinVoucherVersion,
)
from app.models.kingdee_finance import (
    DimFinanceAccount,
    DimLegalEntity,
    DmFinanceStatementMonthly,
    DwdGlBalanceMonthly,
    DwdGlVoucher,
    DwdGlVoucherEntry,
)
from app.services.finance_center_service import FinanceCenterService


pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_kingdee_source(
    db,
    prefix: str,
    *,
    negative_debit_correction: bool = False,
    duplicate_voucher_no_next_period: bool = False,
    signed_credit_closing_balance: bool = False,
    signed_period_amounts: bool = False,
) -> tuple[str, int]:
    account_set_code = f"AIS{prefix}"
    entity = DimLegalEntity(
        entity_code=f"ENT{prefix}",
        entity_name=f"Huabang Test {prefix}",
        short_name=f"HB{prefix}",
        source_system="kingdee",
        source_database=account_set_code,
        source_pk=f"{account_set_code}:legal_entity",
        import_batch_id=f"batch-{prefix}",
        account_set_code=account_set_code,
        start_period="2026-01",
        current_period="2026-01",
        status="active",
    )
    db.add(entity)
    await db.flush()

    debit_account = DimFinanceAccount(
        legal_entity_id=entity.id,
        source_account_id="1001",
        account_code="1001",
        account_name="Cash",
        account_level=1,
        account_type="asset",
        balance_direction="debit",
        is_cash=True,
        is_bank=False,
        is_active=True,
        source_system="kingdee",
        source_database=account_set_code,
        source_pk=f"{account_set_code}:account:1001",
        import_batch_id=f"batch-{prefix}",
    )
    credit_account = DimFinanceAccount(
        legal_entity_id=entity.id,
        source_account_id="4001",
        account_code="4001",
        account_name="Revenue",
        account_level=1,
        account_type="income",
        balance_direction="credit",
        is_cash=False,
        is_bank=False,
        is_active=True,
        source_system="kingdee",
        source_database=account_set_code,
        source_pk=f"{account_set_code}:account:4001",
        import_batch_id=f"batch-{prefix}",
    )
    db.add_all([debit_account, credit_account])
    await db.flush()

    voucher = DwdGlVoucher(
        legal_entity_id=entity.id,
        voucher_no=f"记-{prefix}",
        voucher_group="记",
        voucher_date=date(2026, 1, 15),
        fiscal_year=2026,
        fiscal_period=1,
        source_status="posted",
        is_checked=True,
        is_posted=True,
        preparer_name="Kingdee",
        total_debit=Decimal("60.00") if negative_debit_correction else Decimal("100.00"),
        total_credit=Decimal("60.00") if negative_debit_correction else Decimal("100.00"),
        source_system="kingdee",
        source_database=account_set_code,
        source_pk=f"{account_set_code}:voucher:1",
        import_batch_id=f"batch-{prefix}",
    )
    db.add(voucher)
    await db.flush()
    duplicate_voucher = None
    if duplicate_voucher_no_next_period:
        duplicate_voucher = DwdGlVoucher(
            legal_entity_id=entity.id,
            voucher_no=voucher.voucher_no,
            voucher_group=voucher.voucher_group,
            voucher_date=date(2026, 2, 15),
            fiscal_year=2026,
            fiscal_period=2,
            source_status="posted",
            is_checked=True,
            is_posted=True,
            preparer_name="Kingdee",
            total_debit=Decimal("20.00"),
            total_credit=Decimal("20.00"),
            source_system="kingdee",
            source_database=account_set_code,
            source_pk=f"{account_set_code}:voucher:2",
            import_batch_id=f"batch-{prefix}",
        )
        db.add(duplicate_voucher)
        await db.flush()
    voucher_entries = [
        DwdGlVoucherEntry(
            voucher_id=voucher.id,
            legal_entity_id=entity.id,
            line_no=1,
            finance_account_id=debit_account.id,
            account_code="1001",
            summary="Kingdee import debit",
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0.00"),
            currency_code="CNY",
            exchange_rate=Decimal("1.00000000"),
            source_system="kingdee",
            source_database=account_set_code,
            source_pk=f"{account_set_code}:voucher:1:entry:1",
            import_batch_id=f"batch-{prefix}",
        ),
        DwdGlVoucherEntry(
            voucher_id=voucher.id,
            legal_entity_id=entity.id,
            line_no=2,
            finance_account_id=credit_account.id,
            account_code="4001",
            summary="Kingdee import credit",
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("60.00") if negative_debit_correction else Decimal("100.00"),
            currency_code="CNY",
            exchange_rate=Decimal("1.00000000"),
            source_system="kingdee",
            source_database=account_set_code,
            source_pk=f"{account_set_code}:voucher:1:entry:2",
            import_batch_id=f"batch-{prefix}",
        ),
    ]
    if negative_debit_correction:
        voucher_entries.append(
            DwdGlVoucherEntry(
                voucher_id=voucher.id,
                legal_entity_id=entity.id,
                line_no=3,
                finance_account_id=credit_account.id,
                account_code="4001",
                summary="Kingdee import negative debit correction",
                debit_amount=Decimal("-40.00"),
                credit_amount=Decimal("0.00"),
                currency_code="CNY",
                exchange_rate=Decimal("1.00000000"),
                source_system="kingdee",
                source_database=account_set_code,
                source_pk=f"{account_set_code}:voucher:1:entry:3",
                import_batch_id=f"batch-{prefix}",
            )
        )
    if duplicate_voucher:
        voucher_entries.extend(
            [
                DwdGlVoucherEntry(
                    voucher_id=duplicate_voucher.id,
                    legal_entity_id=entity.id,
                    line_no=1,
                    finance_account_id=debit_account.id,
                    account_code="1001",
                    summary="Kingdee duplicate no debit",
                    debit_amount=Decimal("20.00"),
                    credit_amount=Decimal("0.00"),
                    currency_code="CNY",
                    exchange_rate=Decimal("1.00000000"),
                    source_system="kingdee",
                    source_database=account_set_code,
                    source_pk=f"{account_set_code}:voucher:2:entry:1",
                    import_batch_id=f"batch-{prefix}",
                ),
                DwdGlVoucherEntry(
                    voucher_id=duplicate_voucher.id,
                    legal_entity_id=entity.id,
                    line_no=2,
                    finance_account_id=credit_account.id,
                    account_code="4001",
                    summary="Kingdee duplicate no credit",
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal("20.00"),
                    currency_code="CNY",
                    exchange_rate=Decimal("1.00000000"),
                    source_system="kingdee",
                    source_database=account_set_code,
                    source_pk=f"{account_set_code}:voucher:2:entry:2",
                    import_batch_id=f"batch-{prefix}",
                ),
            ]
        )
    db.add_all(
        [
            *voucher_entries,
            DwdGlBalanceMonthly(
                legal_entity_id=entity.id,
                finance_account_id=debit_account.id,
                period="2026-01",
                detail_id="",
                currency_code="CNY",
                opening_debit=Decimal("10.00"),
                opening_credit=Decimal("0.00"),
                period_debit=Decimal("100.00"),
                period_credit=Decimal("0.00"),
                closing_debit=Decimal("110.00"),
                closing_credit=Decimal("0.00"),
                source_system="kingdee",
                source_database=account_set_code,
                source_pk=f"{account_set_code}:balance:1001:2026-01",
                import_batch_id=f"batch-{prefix}",
            ),
            DwdGlBalanceMonthly(
                legal_entity_id=entity.id,
                finance_account_id=credit_account.id,
                period="2026-01",
                detail_id="",
                currency_code="CNY",
                opening_debit=Decimal("0.00"),
                opening_credit=Decimal("5.00"),
                period_debit=(
                    Decimal("-541.30")
                    if signed_period_amounts
                    else Decimal("146.00")
                    if signed_credit_closing_balance
                    else Decimal("0.00")
                ),
                period_credit=(
                    Decimal("-541.30")
                    if signed_period_amounts
                    else Decimal("141.00")
                    if signed_credit_closing_balance
                    else Decimal("100.00")
                ),
                closing_debit=Decimal("0.00"),
                closing_credit=Decimal("0.00") if signed_credit_closing_balance else Decimal("105.00"),
                source_system="kingdee",
                source_database=account_set_code,
                source_pk=f"{account_set_code}:balance:4001:2026-01",
                import_batch_id=f"batch-{prefix}",
            ),
        ]
    )
    await db.flush()
    return account_set_code, entity.id


async def test_imports_kingdee_history_into_writable_formal_ledger_idempotently():
    prefix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            account_set_code, _ = await _seed_kingdee_source(db, prefix)

        service = FinanceCenterService(db)
        first = await service.import_kingdee_history_to_formal_ledger(account_set_code)
        second = await service.import_kingdee_history_to_formal_ledger(account_set_code)

        assert first["status"] == "ready"
        assert first["created"] == {
            "books": 1,
            "periods": 1,
            "accounts": 2,
            "vouchers": 1,
            "voucher_entries": 2,
            "ledger_balances": 2,
        }
        assert second["created"] == {
            "books": 0,
            "periods": 0,
            "accounts": 0,
            "vouchers": 0,
            "voucher_entries": 0,
            "ledger_balances": 0,
        }

        voucher = (
            await db.execute(
                select(FinVoucher).where(
                    FinVoucher.source_database == account_set_code,
                    FinVoucher.source_pk == f"{account_set_code}:voucher:1",
                )
            )
        ).scalar_one()
        assert voucher.origin_kind == "kingdee_history"
        assert voucher.status == "posted"
        assert voucher.total_debit == Decimal("100.0000")
        assert voucher.total_credit == Decimal("100.0000")

        assert (
            await db.execute(select(func.count(FinVoucherEntry.id)).where(FinVoucherEntry.voucher_id == voucher.id))
        ).scalar_one() == 2
        assert (
            await db.execute(select(func.count(FinLedgerBalance.id)).where(FinLedgerBalance.book_id == voucher.book_id))
        ).scalar_one() == 2
        assert (
            await db.execute(select(func.count(FinSourceLink.id)).where(FinSourceLink.book_id == voucher.book_id))
        ).scalar_one() >= 5


async def test_import_normalizes_kingdee_negative_debit_lines_to_formal_credit_side():
    prefix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            account_set_code, _ = await _seed_kingdee_source(db, prefix, negative_debit_correction=True)

        service = FinanceCenterService(db)
        result = await service.import_kingdee_history_to_formal_ledger(account_set_code)

        assert result["created"]["voucher_entries"] == 3
        voucher = (
            await db.execute(
                select(FinVoucher).where(
                    FinVoucher.source_database == account_set_code,
                    FinVoucher.source_pk == f"{account_set_code}:voucher:1",
                )
            )
        ).scalar_one()
        entries = (
            await db.execute(
                select(FinVoucherEntry).where(FinVoucherEntry.voucher_id == voucher.id).order_by(FinVoucherEntry.line_no)
            )
        ).scalars().all()

        assert voucher.total_debit == Decimal("100.0000")
        assert voucher.total_credit == Decimal("100.0000")
        assert [(row.debit_amount, row.credit_amount) for row in entries] == [
            (Decimal("100.0000"), Decimal("0.0000")),
            (Decimal("0.0000"), Decimal("60.0000")),
            (Decimal("0.0000"), Decimal("40.0000")),
        ]


async def test_import_allows_same_kingdee_voucher_number_in_different_periods():
    prefix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            account_set_code, _ = await _seed_kingdee_source(
                db,
                prefix,
                duplicate_voucher_no_next_period=True,
            )

        service = FinanceCenterService(db)
        result = await service.import_kingdee_history_to_formal_ledger(account_set_code)

        assert result["created"]["periods"] == 2
        assert result["created"]["vouchers"] == 2
        assert result["created"]["voucher_entries"] == 4
        vouchers = (
            await db.execute(
                select(FinVoucher).where(FinVoucher.source_database == account_set_code).order_by(FinVoucher.period)
            )
        ).scalars().all()
        assert [row.voucher_no for row in vouchers] == [f"记-{prefix}", f"记-{prefix}"]
        assert [row.period for row in vouchers] == ["2026-01", "2026-02"]


async def test_import_preserves_signed_closing_ledger_balances():
    prefix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            account_set_code, _ = await _seed_kingdee_source(db, prefix, signed_credit_closing_balance=True)

        service = FinanceCenterService(db)
        await service.import_kingdee_history_to_formal_ledger(account_set_code)
        balance = (
            await db.execute(
                select(FinLedgerBalance)
                .join(FinAccount, FinAccount.id == FinLedgerBalance.account_id)
                .where(FinLedgerBalance.source_pk == f"{account_set_code}:balance:4001:2026-01")
            )
        ).scalar_one()

        assert balance.balance_direction == "credit"
        assert balance.period_debit == Decimal("146.0000")
        assert balance.period_credit == Decimal("141.0000")
        assert balance.closing_amount == Decimal("-5.0000")


async def test_import_preserves_signed_period_ledger_amounts():
    prefix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            account_set_code, _ = await _seed_kingdee_source(db, prefix, signed_period_amounts=True)

        service = FinanceCenterService(db)
        await service.import_kingdee_history_to_formal_ledger(account_set_code)
        balance = (
            await db.execute(
                select(FinLedgerBalance)
                .join(FinAccount, FinAccount.id == FinLedgerBalance.account_id)
                .where(FinLedgerBalance.source_pk == f"{account_set_code}:balance:4001:2026-01")
            )
        ).scalar_one()

        assert balance.balance_direction == "credit"
        assert balance.period_debit == Decimal("-541.3000")
        assert balance.period_credit == Decimal("-541.3000")
        assert balance.closing_amount == Decimal("0.0000")


async def test_revises_posted_kingdee_history_voucher_with_audited_version_and_recomputed_ledger():
    prefix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            account_set_code, _ = await _seed_kingdee_source(db, prefix)
        service = FinanceCenterService(db)
        await service.import_kingdee_history_to_formal_ledger(account_set_code)
        voucher = (
            await db.execute(select(FinVoucher).where(FinVoucher.source_database == account_set_code))
        ).scalar_one()
        accounts = {
            row.account_code: row.id
            for row in (
                await db.execute(select(FinAccount).where(FinAccount.book_id == voucher.book_id))
            ).scalars()
        }

        result = await service.revise_voucher_entries(
            voucher.id,
            entries=[
                {
                    "account_id": accounts["1001"],
                    "summary": "Adjusted debit",
                    "debit_amount": Decimal("120.00"),
                    "credit_amount": Decimal("0.00"),
                },
                {
                    "account_id": accounts["4001"],
                    "summary": "Adjusted credit",
                    "debit_amount": Decimal("0.00"),
                    "credit_amount": Decimal("120.00"),
                },
            ],
            actor_name="finance-user",
            reason="history voucher correction approved by finance",
        )

        await db.refresh(voucher)
        assert result["status"] == "posted"
        assert voucher.status == "posted"
        assert voucher.version == 2
        assert voucher.total_debit == Decimal("120.0000")
        assert voucher.total_credit == Decimal("120.0000")
        assert (
            await db.execute(select(func.count(FinVoucherVersion.id)).where(FinVoucherVersion.voucher_id == voucher.id))
        ).scalar_one() == 1
        debit_balance = (
            await db.execute(
                select(FinLedgerBalance)
                .join(FinAccount, FinAccount.id == FinLedgerBalance.account_id)
                .where(FinLedgerBalance.book_id == voucher.book_id, FinAccount.account_code == "1001")
            )
        ).scalar_one()
        assert debit_balance.period_debit == Decimal("120.0000")
        assert debit_balance.closing_amount == Decimal("130.0000")


async def test_manual_voucher_can_be_posted_and_reversed_with_ledger_audit():
    prefix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            account_set_code, _ = await _seed_kingdee_source(db, prefix)
        service = FinanceCenterService(db)
        await service.import_kingdee_history_to_formal_ledger(account_set_code)
        book = (
            await db.execute(select(FinBook).where(FinBook.book_code == account_set_code))
        ).scalar_one()
        accounts = {
            row.account_code: row.id
            for row in (
                await db.execute(select(FinAccount).where(FinAccount.book_id == book.id))
            ).scalars()
        }
        await service.open_period(book.id, "2026-02")

        draft = await service.create_voucher(
            book.id,
            period="2026-02",
            voucher_no=f"MANUAL-{prefix}",
            voucher_date=date(2026, 2, 3),
            entries=[
                {
                    "account_id": accounts["1001"],
                    "summary": "Manual receipt",
                    "debit_amount": Decimal("30.00"),
                    "credit_amount": Decimal("0.00"),
                },
                {
                    "account_id": accounts["4001"],
                    "summary": "Manual revenue",
                    "debit_amount": Decimal("0.00"),
                    "credit_amount": Decimal("30.00"),
                },
            ],
            actor_name="accountant",
            reason="manual ledger test",
        )
        posted = await service.post_voucher(draft["voucher_id"], actor_name="accountant", reason="reviewed")

        assert posted["status"] == "posted"
        debit_balance = (
            await db.execute(
                select(FinLedgerBalance).where(
                    FinLedgerBalance.book_id == book.id,
                    FinLedgerBalance.account_id == accounts["1001"],
                    FinLedgerBalance.period == "2026-02",
                )
            )
        ).scalar_one()
        assert debit_balance.period_debit == Decimal("30.0000")
        assert debit_balance.closing_amount == Decimal("30.0000")

        reversal = await service.reverse_voucher(
            draft["voucher_id"],
            voucher_no=f"REV-{prefix}",
            actor_name="accountant",
            reason="approved reversal",
        )
        await db.refresh(debit_balance)
        original = await db.get(FinVoucher, draft["voucher_id"])
        assert reversal["status"] == "posted"
        assert original.status == "reversed"
        assert original.reversed_by_id == reversal["voucher_id"]
        assert debit_balance.period_debit == Decimal("30.0000")
        assert debit_balance.period_credit == Decimal("30.0000")
        assert debit_balance.closing_amount == Decimal("0.0000")


async def test_statement_generation_requires_confirmed_mapping_and_persists_monthly_rows():
    prefix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            account_set_code, _ = await _seed_kingdee_source(db, prefix)
        service = FinanceCenterService(db)
        await service.import_kingdee_history_to_formal_ledger(account_set_code)
        book = (
            await db.execute(select(FinBook).where(FinBook.book_code == account_set_code))
        ).scalar_one()
        accounts = {
            row.account_code: row.id
            for row in (
                await db.execute(select(FinAccount).where(FinAccount.book_id == book.id))
            ).scalars()
        }

        pending = await service.generate_statement_monthly(book.id, "2026-01", "income_statement")
        assert pending["status"] == "pending_mapping"
        assert pending["items"] == []
        assert {issue["account_code"] for issue in pending["issues"]} == {"1001", "4001"}

        revenue_line = await service.upsert_statement_line(
            template_code="hb-small-enterprise",
            template_version=1,
            statement_type="income_statement",
            line_code="revenue",
            line_name="Revenue",
            display_order=10,
        )
        await service.map_account_to_statement(
            book.id,
            accounts["4001"],
            revenue_line["statement_line_id"],
            amount_sign=1,
            actor_name="finance-user",
        )
        cash_line = await service.upsert_statement_line(
            template_code="hb-small-enterprise",
            template_version=1,
            statement_type="income_statement",
            line_code="cash_movement",
            line_name="Cash Movement",
            display_order=20,
        )
        await service.map_account_to_statement(
            book.id,
            accounts["1001"],
            cash_line["statement_line_id"],
            amount_sign=1,
            actor_name="finance-user",
        )

        ready = await service.generate_statement_monthly(book.id, "2026-01", "income_statement")

        assert ready["status"] == "ready"
        assert ready["items"] == [
            {"line_code": "revenue", "line_name": "Revenue", "current_amount": 100.0, "status": "ready"},
            {"line_code": "cash_movement", "line_name": "Cash Movement", "current_amount": 100.0, "status": "ready"},
        ]
        persisted = (
            await db.execute(
                select(DmFinanceStatementMonthly)
                .where(
                    DmFinanceStatementMonthly.legal_entity_id == book.legal_entity_id,
                    DmFinanceStatementMonthly.period == "2026-01",
                    DmFinanceStatementMonthly.statement_type == "income_statement",
                )
                .order_by(DmFinanceStatementMonthly.display_order)
            )
        ).scalars().all()
        assert [row.status for row in persisted] == ["ready", "ready"]
        assert [row.current_amount for row in persisted] == [Decimal("100.0000"), Decimal("100.0000")]
