"""牧马人财务中心 CRUD 接口:基于新建表的持久化接口。

所有路由前缀 /finance-center/mumaren,操作仅落 finance_center_mumaren schema,
不调用旧财务接口,所有写操作产生 draft 状态并追加审计日志。
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.mumaren_finance_center import (
    require_mumaren_finance_access,
    require_mumaren_voucher_write,
)
from app.core.database import get_db
from app.models.mumaren_finance_center import FinanceCenterMumarenAuditLog
from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAccount,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenVoucher,
)
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenAuxiliaryAccounting,
    FinanceCenterMumarenAutoVoucherRule,
    FinanceCenterMumarenAutoVoucherRun,
    FinanceCenterMumarenBankReconciliation,
    FinanceCenterMumarenExpenseEntry,
    FinanceCenterMumarenSalesMonthlyReport,
    FinanceCenterMumarenVoucherTemplate,
)
from app.services.mumaren_finance_center.auto_voucher import (
    AutoVoucherRuleConfigurationError,
    build_auto_voucher_draft,
)
from app.services.mumaren_finance_center.workflow import create_voucher
from app.models.sys import SysUser
from app.schemas.common import ApiResponse


router = APIRouter(prefix="/finance-center/mumaren", tags=["牧马人财务中心:CRUD"])


def _actor_id(user: SysUser) -> int:
    return int(user.id)


async def _add_audit_log(db: AsyncSession, *, book_id: int | None, action: str, operator_id: int, detail: str | None = None):
    """追加审计日志并在同一事务 flush。"""
    db.add(FinanceCenterMumarenAuditLog(
        book_id=book_id,
        action=action,
        operator_id=operator_id,
        detail=detail,
    ))
    await db.flush()


# ===========================================================================
# Task 9: 凭证模板 CRUD(finance_center_mumaren_voucher_templates)
# ===========================================================================

class VoucherTemplateLine(BaseModel):
    account_id: int = Field(ge=1)
    summary: str | None = Field(default=None, max_length=500)
    debit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    credit_amount: Decimal = Field(default=Decimal("0"), ge=0)


class VoucherTemplateLines(BaseModel):
    lines: list[VoucherTemplateLine] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_balanced_lines(self):
        debit = sum((line.debit_amount for line in self.lines), Decimal("0"))
        credit = sum((line.credit_amount for line in self.lines), Decimal("0"))
        for line in self.lines:
            if (line.debit_amount == 0) == (line.credit_amount == 0):
                raise ValueError("每条模板分录必须且只能填写借方或贷方金额")
        if debit != credit:
            raise ValueError(f"借贷不平衡: 借方={debit}, 贷方={credit}")
        return self


class VoucherTemplateInput(BaseModel):
    book_id: int = Field(ge=1)
    template_name: str = Field(min_length=1, max_length=128)
    voucher_type: str = Field(default="记", max_length=16)
    summary: str | None = Field(default=None, max_length=500)
    lines_json: VoucherTemplateLines


class VoucherTemplateUpdate(BaseModel):
    book_id: int = Field(ge=1)
    template_name: str | None = None
    voucher_type: str | None = None
    summary: str | None = None
    lines_json: VoucherTemplateLines | None = None


async def _require_writable_book(db: AsyncSession, book_id: int) -> FinanceCenterMumarenBook:
    book = await db.get(FinanceCenterMumarenBook, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"账簿 {book_id} 不存在")
    if book.is_readonly:
        raise HTTPException(status_code=409, detail="金蝶迁移账簿只读，不能维护凭证模板")
    return book


async def _validate_template_accounts(
    db: AsyncSession, *, book_id: int, lines_json: VoucherTemplateLines | None,
) -> None:
    if lines_json is None:
        return
    for line_no, line in enumerate(lines_json.lines, start=1):
        account = (await db.execute(
            select(FinanceCenterMumarenAccount).where(
                FinanceCenterMumarenAccount.id == line.account_id,
                FinanceCenterMumarenAccount.book_id == book_id,
                FinanceCenterMumarenAccount.is_active.is_(True),
            )
        )).scalar_one_or_none()
        if account is None:
            raise HTTPException(status_code=400, detail=f"第{line_no}行会计科目不存在、不属于账簿或已停用")


def _voucher_template_data(tpl: FinanceCenterMumarenVoucherTemplate) -> dict:
    return {
        "id": tpl.id,
        "book_id": tpl.book_id,
        "template_name": tpl.template_name,
        "voucher_type": tpl.voucher_type,
        "summary": tpl.summary,
        "lines_json": tpl.lines_json,
        "created_by": tpl.created_by,
        "created_at": tpl.created_at,
    }


@router.get("/voucher-templates", response_model=ApiResponse)
async def list_voucher_templates(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出凭证模板,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenVoucherTemplate)
        .where(FinanceCenterMumarenVoucherTemplate.book_id == book_id)
        .order_by(FinanceCenterMumarenVoucherTemplate.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_voucher_template_data(row) for row in rows])


@router.post("/voucher-templates", response_model=ApiResponse)
async def create_voucher_template(
    body: VoucherTemplateInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建凭证模板;不自动审核、不自动过账。"""
    await _require_writable_book(db, body.book_id)
    await _validate_template_accounts(db, book_id=body.book_id, lines_json=body.lines_json)
    tpl = FinanceCenterMumarenVoucherTemplate(
        book_id=body.book_id,
        template_name=body.template_name,
        voucher_type=body.voucher_type,
        summary=body.summary,
        lines_json=body.lines_json.model_dump(mode="json") if body.lines_json else None,
        created_by=_actor_id(current_user),
    )
    db.add(tpl)
    await db.flush()
    await _add_audit_log(
        db, book_id=body.book_id, action="create_voucher_template",
        operator_id=_actor_id(current_user),
        detail=f"创建凭证模板 {body.template_name}",
    )
    return ApiResponse.ok(data=_voucher_template_data(tpl), message="凭证模板已创建")


@router.put("/voucher-templates/{template_id}", response_model=ApiResponse)
async def update_voucher_template(
    template_id: int,
    body: VoucherTemplateUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新凭证模板;强制同账簿校验。"""
    tpl = await db.get(FinanceCenterMumarenVoucherTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"凭证模板 {template_id} 不存在")
    if tpl.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    await _require_writable_book(db, body.book_id)
    await _validate_template_accounts(db, book_id=body.book_id, lines_json=body.lines_json)
    for field in ("template_name", "voucher_type", "summary", "lines_json"):
        value = getattr(body, field)
        if value is not None:
            setattr(tpl, field, value.model_dump(mode="json") if field == "lines_json" and value else value)
    await db.flush()
    await _add_audit_log(
        db, book_id=tpl.book_id, action="update_voucher_template",
        operator_id=_actor_id(current_user),
        detail=f"更新凭证模板 {tpl.template_name}",
    )
    return ApiResponse.ok(data=_voucher_template_data(tpl), message="凭证模板已更新")


@router.delete("/voucher-templates/{template_id}", response_model=ApiResponse)
async def delete_voucher_template(
    template_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除凭证模板;强制同账簿校验。"""
    tpl = await db.get(FinanceCenterMumarenVoucherTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"凭证模板 {template_id} 不存在")
    if tpl.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    await _require_writable_book(db, book_id)
    template_name = tpl.template_name
    await db.delete(tpl)
    await _add_audit_log(
        db, book_id=book_id, action="delete_voucher_template",
        operator_id=_actor_id(current_user),
        detail=f"删除凭证模板 {template_name}",
    )
    return ApiResponse.ok(message="凭证模板已删除")


# ===========================================================================
# Task 10: 自动凭证规则 CRUD(finance_center_mumaren_auto_voucher_rules)
# ===========================================================================

class AutoVoucherRuleInput(BaseModel):
    book_id: int = Field(ge=1)
    rule_name: str = Field(min_length=1, max_length=128)
    trigger_event: str = Field(min_length=1, max_length=64)
    debit_account_id: int = Field(ge=1)
    credit_account_id: int = Field(ge=1)
    default_amount: Decimal | None = Field(default=None, gt=0)
    summary: str | None = Field(default=None, max_length=500)
    voucher_type: str = Field(default="记", min_length=1, max_length=16)
    is_active: bool = True


class AutoVoucherRuleUpdate(BaseModel):
    book_id: int = Field(ge=1)
    rule_name: str | None = None
    trigger_event: str | None = None
    debit_account_id: int | None = Field(default=None, ge=1)
    credit_account_id: int | None = Field(default=None, ge=1)
    default_amount: Decimal | None = Field(default=None, gt=0)
    summary: str | None = Field(default=None, max_length=500)
    voucher_type: str | None = Field(default=None, min_length=1, max_length=16)
    is_active: bool | None = None


def _auto_voucher_rule_data(rule: FinanceCenterMumarenAutoVoucherRule) -> dict:
    return {
        "id": rule.id,
        "book_id": rule.book_id,
        "rule_name": rule.rule_name,
        "trigger_event": rule.trigger_event,
        "debit_account_id": rule.debit_account_id,
        "credit_account_id": rule.credit_account_id,
        "default_amount": rule.default_amount,
        "summary": rule.summary,
        "voucher_type": rule.voucher_type,
        "is_active": rule.is_active,
        "created_by": rule.created_by,
        "created_at": rule.created_at,
    }


@router.get("/auto-voucher-rules", response_model=ApiResponse)
async def list_auto_voucher_rules(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出自动凭证规则,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenAutoVoucherRule)
        .where(FinanceCenterMumarenAutoVoucherRule.book_id == book_id)
        .order_by(FinanceCenterMumarenAutoVoucherRule.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_auto_voucher_rule_data(row) for row in rows])


@router.post("/auto-voucher-rules", response_model=ApiResponse)
async def create_auto_voucher_rule(
    body: AutoVoucherRuleInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建自动凭证规则；生成时只形成草稿，绝不自动过账。"""
    await _require_writable_book(db, body.book_id)
    await _validate_auto_voucher_accounts(db, body.book_id, body.debit_account_id, body.credit_account_id)
    rule = FinanceCenterMumarenAutoVoucherRule(
        book_id=body.book_id,
        rule_name=body.rule_name,
        trigger_event=body.trigger_event,
        debit_account_id=body.debit_account_id,
        credit_account_id=body.credit_account_id,
        default_amount=body.default_amount,
        summary=body.summary,
        voucher_type=body.voucher_type,
        is_active=body.is_active,
        created_by=_actor_id(current_user),
    )
    db.add(rule)
    await db.flush()
    await _add_audit_log(
        db, book_id=body.book_id, action="create_auto_voucher_rule",
        operator_id=_actor_id(current_user),
        detail=f"创建自动凭证规则 {body.rule_name}",
    )
    return ApiResponse.ok(data=_auto_voucher_rule_data(rule), message="自动凭证规则已创建")


@router.put("/auto-voucher-rules/{rule_id}", response_model=ApiResponse)
async def update_auto_voucher_rule(
    rule_id: int,
    body: AutoVoucherRuleUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新自动凭证规则;强制同账簿校验。"""
    rule = await db.get(FinanceCenterMumarenAutoVoucherRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"自动凭证规则 {rule_id} 不存在")
    if rule.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    await _require_writable_book(db, body.book_id)
    debit_account_id = body.debit_account_id if body.debit_account_id is not None else rule.debit_account_id
    credit_account_id = body.credit_account_id if body.credit_account_id is not None else rule.credit_account_id
    await _validate_auto_voucher_accounts(db, body.book_id, debit_account_id, credit_account_id)
    for field in ("rule_name", "trigger_event", "debit_account_id", "credit_account_id", "default_amount", "summary", "voucher_type", "is_active"):
        value = getattr(body, field)
        if value is not None:
            setattr(rule, field, value)
    await db.flush()
    await _add_audit_log(
        db, book_id=rule.book_id, action="update_auto_voucher_rule",
        operator_id=_actor_id(current_user),
        detail=f"更新自动凭证规则 {rule.rule_name}",
    )
    return ApiResponse.ok(data=_auto_voucher_rule_data(rule), message="自动凭证规则已更新")


@router.delete("/auto-voucher-rules/{rule_id}", response_model=ApiResponse)
async def delete_auto_voucher_rule(
    rule_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除自动凭证规则;强制同账簿校验。"""
    rule = await db.get(FinanceCenterMumarenAutoVoucherRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"自动凭证规则 {rule_id} 不存在")
    if rule.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    await _require_writable_book(db, book_id)
    rule_name = rule.rule_name
    await db.delete(rule)
    await _add_audit_log(
        db, book_id=book_id, action="delete_auto_voucher_rule",
        operator_id=_actor_id(current_user),
        detail=f"删除自动凭证规则 {rule_name}",
    )
    return ApiResponse.ok(message="自动凭证规则已删除")


async def _validate_auto_voucher_accounts(db: AsyncSession, book_id: int, debit_account_id: int | None, credit_account_id: int | None) -> None:
    if not debit_account_id or not credit_account_id:
        raise HTTPException(status_code=400, detail="规则必须配置借方和贷方会计科目")
    if debit_account_id == credit_account_id:
        raise HTTPException(status_code=400, detail="借方和贷方会计科目不能相同")
    for label, account_id in (("借方", debit_account_id), ("贷方", credit_account_id)):
        account = (await db.execute(select(FinanceCenterMumarenAccount).where(
            FinanceCenterMumarenAccount.id == account_id,
            FinanceCenterMumarenAccount.book_id == book_id,
            FinanceCenterMumarenAccount.is_active.is_(True),
        ))).scalar_one_or_none()
        if account is None:
            raise HTTPException(status_code=400, detail=f"{label}会计科目不存在、不属于账簿或已停用")


class AutoVoucherDraftRequest(BaseModel):
    book_id: int = Field(ge=1)
    voucher_no: str = Field(min_length=1, max_length=64)
    voucher_date: date
    source_key: str = Field(min_length=1, max_length=128)
    amount: Decimal | None = Field(default=None, gt=0)
    summary: str | None = Field(default=None, max_length=500)


async def _load_auto_rule(db: AsyncSession, rule_id: int, body: AutoVoucherDraftRequest) -> FinanceCenterMumarenAutoVoucherRule:
    rule = await db.get(FinanceCenterMumarenAutoVoucherRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="自动凭证规则不存在")
    if rule.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致，禁止跨账簿生成")
    await _require_writable_book(db, body.book_id)
    if not rule.is_active:
        raise HTTPException(status_code=409, detail="规则已停用，不能生成草稿")
    await _validate_auto_voucher_accounts(db, body.book_id, rule.debit_account_id, rule.credit_account_id)
    return rule


@router.post("/auto-voucher-rules/{rule_id}/preview", response_model=ApiResponse)
async def preview_auto_voucher_draft(rule_id: int, body: AutoVoucherDraftRequest, _: SysUser = Depends(require_mumaren_voucher_write), db: AsyncSession = Depends(get_db)):
    """预览平衡草稿，不写入数据库，也不审核或过账。"""
    rule = await _load_auto_rule(db, rule_id, body)
    try:
        draft = build_auto_voucher_draft(rule.__dict__, amount=body.amount, source_key=body.source_key)
    except AutoVoucherRuleConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.summary:
        draft["summary"] = body.summary
        for line in draft["lines"]:
            line["summary"] = body.summary
    return ApiResponse.ok(data={**draft, "voucher_no": body.voucher_no, "voucher_date": body.voucher_date})


@router.post("/auto-voucher-rules/{rule_id}/generate-draft", response_model=ApiResponse)
async def generate_auto_voucher_draft(rule_id: int, body: AutoVoucherDraftRequest, current_user: SysUser = Depends(require_mumaren_voucher_write), db: AsyncSession = Depends(get_db)):
    """按规则幂等生成当前账草稿；审核和过账必须另行人工操作。"""
    rule = await _load_auto_rule(db, rule_id, body)
    existing = (await db.execute(select(FinanceCenterMumarenAutoVoucherRun).where(
        FinanceCenterMumarenAutoVoucherRun.book_id == body.book_id,
        FinanceCenterMumarenAutoVoucherRun.rule_id == rule_id,
        FinanceCenterMumarenAutoVoucherRun.source_key == body.source_key.strip(),
    ))).scalar_one_or_none()
    if existing is not None:
        voucher = await db.get(FinanceCenterMumarenVoucher, existing.voucher_id)
        if voucher is None:
            raise HTTPException(status_code=409, detail="自动凭证幂等记录缺少关联凭证，请联系管理员核查")
        return ApiResponse.ok(data={"voucher_id": existing.voucher_id, "voucher_no": voucher.voucher_no, "status": voucher.status, "reused": True}, message="来源业务已生成过凭证")
    try:
        async with db.begin_nested():
            draft = build_auto_voucher_draft(rule.__dict__, amount=body.amount, source_key=body.source_key)
            if body.summary:
                draft["summary"] = body.summary
                for line in draft["lines"]:
                    line["summary"] = body.summary
            voucher = await create_voucher(db, book_id=body.book_id, voucher_no=body.voucher_no, voucher_date=body.voucher_date,
                lines=draft["lines"], operator_id=_actor_id(current_user), summary=draft["summary"], voucher_type=draft["voucher_type"])
            voucher.source_system = "mumaren_auto_rule"
            voucher.source_database = "finance_center_mumaren"
            voucher.source_key = str(draft["source_key"])
            voucher.source_payload = {"rule_id": rule.id, "rule_name": rule.rule_name, "trigger_event": rule.trigger_event, "source_key": body.source_key.strip()}
            db.add(FinanceCenterMumarenAutoVoucherRun(book_id=body.book_id, rule_id=rule_id, voucher_id=voucher.id, source_key=body.source_key.strip(), amount=draft["amount"], created_by=_actor_id(current_user)))
            await db.flush()
    except (AutoVoucherRuleConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        existing = (await db.execute(select(FinanceCenterMumarenAutoVoucherRun).where(
            FinanceCenterMumarenAutoVoucherRun.book_id == body.book_id,
            FinanceCenterMumarenAutoVoucherRun.rule_id == rule_id,
            FinanceCenterMumarenAutoVoucherRun.source_key == body.source_key.strip(),
        ))).scalar_one_or_none()
        if existing is None:
            raise HTTPException(status_code=409, detail="凭证号或自动凭证来源标识冲突") from exc
        voucher = await db.get(FinanceCenterMumarenVoucher, existing.voucher_id)
        if voucher is None:
            raise HTTPException(status_code=409, detail="自动凭证幂等记录缺少关联凭证，请联系管理员核查") from exc
        return ApiResponse.ok(data={"voucher_id": voucher.id, "voucher_no": voucher.voucher_no, "status": voucher.status, "reused": True}, message="来源业务已生成过凭证")
    await _add_audit_log(db, book_id=body.book_id, action="generate_auto_voucher_draft", operator_id=_actor_id(current_user), detail=f"规则 {rule.rule_name} 来源 {body.source_key.strip()}")
    return ApiResponse.ok(data={"voucher_id": voucher.id, "voucher_no": voucher.voucher_no, "status": voucher.status, "reused": False}, message="平衡草稿已生成，请到凭证列表审核后人工过账")


# ===========================================================================
# Task 11: 费用明细 CRUD(finance_center_mumaren_expense_entries)
# ===========================================================================

class ExpenseEntryInput(BaseModel):
    book_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    account_code: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(ge=0)
    remark: str | None = None


class ExpenseEntryUpdate(BaseModel):
    book_id: int = Field(ge=1)
    period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    account_code: str | None = None
    account_name: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    remark: str | None = None


def _expense_entry_data(entry: FinanceCenterMumarenExpenseEntry) -> dict:
    return {
        "id": entry.id,
        "book_id": entry.book_id,
        "period": entry.period,
        "account_code": entry.account_code,
        "account_name": entry.account_name,
        "amount": entry.amount,
        "remark": entry.remark,
        "workflow_status": entry.workflow_status,
        "created_by": entry.created_by,
        "created_at": entry.created_at,
    }


@router.get("/expense-entries", response_model=ApiResponse)
async def list_expense_entries(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出费用明细,支持 book_id 与 period 过滤,默认 limit 100,最大 500。"""
    stmt = select(FinanceCenterMumarenExpenseEntry).where(
        FinanceCenterMumarenExpenseEntry.book_id == book_id
    )
    if period is not None:
        stmt = stmt.where(FinanceCenterMumarenExpenseEntry.period == period)
    stmt = stmt.order_by(
        FinanceCenterMumarenExpenseEntry.period.desc(),
        FinanceCenterMumarenExpenseEntry.id.desc(),
    ).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_expense_entry_data(row) for row in rows])


@router.post("/expense-entries", response_model=ApiResponse)
async def create_expense_entry(
    body: ExpenseEntryInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建费用明细(workflow_status=draft);不自动审核、不自动过账。"""
    entry = FinanceCenterMumarenExpenseEntry(
        book_id=body.book_id,
        period=body.period,
        account_code=body.account_code,
        account_name=body.account_name,
        amount=body.amount,
        remark=body.remark,
        workflow_status="draft",
        created_by=_actor_id(current_user),
    )
    db.add(entry)
    await db.flush()
    await _add_audit_log(
        db, book_id=body.book_id, action="create_expense_entry",
        operator_id=_actor_id(current_user),
        detail=f"创建费用明细 {body.period} {body.account_code}",
    )
    return ApiResponse.ok(data=_expense_entry_data(entry), message="费用明细已创建")


@router.put("/expense-entries/{entry_id}", response_model=ApiResponse)
async def update_expense_entry(
    entry_id: int,
    body: ExpenseEntryUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新费用明细(仅 draft 可改);强制同账簿校验。"""
    entry = await db.get(FinanceCenterMumarenExpenseEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"费用明细 {entry_id} 不存在")
    if entry.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if entry.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {entry.workflow_status},仅 draft 可修改")
    for field in ("period", "account_code", "account_name", "amount", "remark"):
        value = getattr(body, field)
        if value is not None:
            setattr(entry, field, value)
    await db.flush()
    await _add_audit_log(
        db, book_id=entry.book_id, action="update_expense_entry",
        operator_id=_actor_id(current_user),
        detail=f"更新费用明细 {entry.period} {entry.account_code}",
    )
    return ApiResponse.ok(data=_expense_entry_data(entry), message="费用明细已更新")


@router.delete("/expense-entries/{entry_id}", response_model=ApiResponse)
async def delete_expense_entry(
    entry_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除费用明细(仅 draft 可删);强制同账簿校验。"""
    entry = await db.get(FinanceCenterMumarenExpenseEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"费用明细 {entry_id} 不存在")
    if entry.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if entry.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {entry.workflow_status},仅 draft 可删除")
    desc = f"{entry.period} {entry.account_code}"
    await db.delete(entry)
    await _add_audit_log(
        db, book_id=book_id, action="delete_expense_entry",
        operator_id=_actor_id(current_user),
        detail=f"删除费用明细 {desc}",
    )
    return ApiResponse.ok(message="费用明细已删除")


@router.post("/expense-entries/{entry_id}/review", response_model=ApiResponse)
async def review_expense_entry(
    entry_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """审核费用明细:draft → reviewed;不自动过账。"""
    entry = await db.get(FinanceCenterMumarenExpenseEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"费用明细 {entry_id} 不存在")
    if entry.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿操作")
    if entry.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {entry.workflow_status},无法审核")
    entry.workflow_status = "reviewed"
    await db.flush()
    await _add_audit_log(
        db, book_id=entry.book_id, action="review_expense_entry",
        operator_id=_actor_id(current_user),
        detail=f"审核费用明细 {entry.period} {entry.account_code}",
    )
    return ApiResponse.ok(data=_expense_entry_data(entry), message="费用明细已审核")


@router.post("/expense-entries/{entry_id}/post", response_model=ApiResponse)
async def post_expense_entry(
    entry_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """过账费用明细:reviewed → posted;draft 直接 post 返回 409。"""
    entry = await db.get(FinanceCenterMumarenExpenseEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"费用明细 {entry_id} 不存在")
    if entry.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿操作")
    if entry.workflow_status != "reviewed":
        raise HTTPException(
            status_code=409,
            detail=f"当前状态 {entry.workflow_status},仅 reviewed 可过账",
        )
    entry.workflow_status = "posted"
    await db.flush()
    await _add_audit_log(
        db, book_id=entry.book_id, action="post_expense_entry",
        operator_id=_actor_id(current_user),
        detail=f"过账费用明细 {entry.period} {entry.account_code}",
    )
    return ApiResponse.ok(data=_expense_entry_data(entry), message="费用明细已过账")


# ===========================================================================
# Task 12: 销售月报 CRUD(finance_center_mumaren_sales_monthly_reports)
# ===========================================================================

class SalesMonthlyReportInput(BaseModel):
    book_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    store_code: str = Field(min_length=1, max_length=32)
    store_name: str | None = Field(default=None, max_length=128)
    sales_amount: Decimal = Field(ge=0)
    return_amount: Decimal = Field(default=Decimal("0"), ge=0)
    remark: str | None = None


class SalesMonthlyReportUpdate(BaseModel):
    book_id: int = Field(ge=1)
    period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    store_code: str | None = None
    store_name: str | None = None
    sales_amount: Decimal | None = Field(default=None, ge=0)
    return_amount: Decimal | None = Field(default=None, ge=0)
    remark: str | None = None


def _sales_monthly_report_data(report: FinanceCenterMumarenSalesMonthlyReport) -> dict:
    return {
        "id": report.id,
        "book_id": report.book_id,
        "period": report.period,
        "store_code": report.store_code,
        "store_name": report.store_name,
        "sales_amount": report.sales_amount,
        "return_amount": report.return_amount,
        "net_sales": Decimal(report.sales_amount) - Decimal(report.return_amount),
        "remark": report.remark,
        "created_by": report.created_by,
        "created_at": report.created_at,
    }


@router.get("/sales-monthly-reports", response_model=ApiResponse)
async def list_sales_monthly_reports(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出销售月报,支持 book_id 与 period 过滤,默认 limit 100,最大 500。"""
    stmt = select(FinanceCenterMumarenSalesMonthlyReport).where(
        FinanceCenterMumarenSalesMonthlyReport.book_id == book_id
    )
    if period is not None:
        stmt = stmt.where(FinanceCenterMumarenSalesMonthlyReport.period == period)
    stmt = stmt.order_by(
        FinanceCenterMumarenSalesMonthlyReport.period.desc(),
        FinanceCenterMumarenSalesMonthlyReport.id.desc(),
    ).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_sales_monthly_report_data(row) for row in rows])


@router.post("/sales-monthly-reports", response_model=ApiResponse)
async def create_sales_monthly_report(
    body: SalesMonthlyReportInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建销售月报;不自动审核、不自动过账。"""
    await _require_writable_book(db, body.book_id)
    report = FinanceCenterMumarenSalesMonthlyReport(
        book_id=body.book_id,
        period=body.period,
        store_code=body.store_code,
        store_name=body.store_name,
        sales_amount=body.sales_amount,
        return_amount=body.return_amount,
        remark=body.remark,
        created_by=_actor_id(current_user),
    )
    db.add(report)
    await db.flush()
    await _add_audit_log(
        db, book_id=body.book_id, action="create_sales_monthly_report",
        operator_id=_actor_id(current_user),
        detail=f"创建销售月报 {body.period} {body.store_code}",
    )
    return ApiResponse.ok(data=_sales_monthly_report_data(report), message="销售月报已创建")


@router.put("/sales-monthly-reports/{report_id}", response_model=ApiResponse)
async def update_sales_monthly_report(
    report_id: int,
    body: SalesMonthlyReportUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新销售月报;强制同账簿校验。"""
    report = await db.get(FinanceCenterMumarenSalesMonthlyReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"销售月报 {report_id} 不存在")
    if report.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    await _require_writable_book(db, body.book_id)
    for field in ("period", "store_code", "store_name", "sales_amount", "return_amount", "remark"):
        value = getattr(body, field)
        if value is not None:
            setattr(report, field, value)
    await db.flush()
    await _add_audit_log(
        db, book_id=report.book_id, action="update_sales_monthly_report",
        operator_id=_actor_id(current_user),
        detail=f"更新销售月报 {report.period} {report.store_code}",
    )
    return ApiResponse.ok(data=_sales_monthly_report_data(report), message="销售月报已更新")


@router.delete("/sales-monthly-reports/{report_id}", response_model=ApiResponse)
async def delete_sales_monthly_report(
    report_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除销售月报;强制同账簿校验。"""
    report = await db.get(FinanceCenterMumarenSalesMonthlyReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"销售月报 {report_id} 不存在")
    if report.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    await _require_writable_book(db, book_id)
    desc = f"{report.period} {report.store_code}"
    await db.delete(report)
    await _add_audit_log(
        db, book_id=book_id, action="delete_sales_monthly_report",
        operator_id=_actor_id(current_user),
        detail=f"删除销售月报 {desc}",
    )
    return ApiResponse.ok(message="销售月报已删除")


# ===========================================================================
# Task 13: 银行调节表 CRUD(finance_center_mumaren_bank_reconciliations)
# ===========================================================================

class BankReconciliationInput(BaseModel):
    book_id: int = Field(ge=1)
    cash_account_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    bank_balance: Decimal = Field(ge=0)
    book_balance: Decimal = Field(ge=0)
    adjusted_balance: Decimal = Field(ge=0)
    items_json: dict | None = None


class BankReconciliationUpdate(BaseModel):
    book_id: int = Field(ge=1)
    cash_account_id: int | None = Field(default=None, ge=1)
    period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    bank_balance: Decimal | None = Field(default=None, ge=0)
    book_balance: Decimal | None = Field(default=None, ge=0)
    adjusted_balance: Decimal | None = Field(default=None, ge=0)
    items_json: dict | None = None


def _bank_reconciliation_data(rec: FinanceCenterMumarenBankReconciliation) -> dict:
    return {
        "id": rec.id,
        "book_id": rec.book_id,
        "cash_account_id": rec.cash_account_id,
        "period": rec.period,
        "bank_balance": rec.bank_balance,
        "book_balance": rec.book_balance,
        "adjusted_balance": rec.adjusted_balance,
        "items_json": rec.items_json,
        "workflow_status": rec.workflow_status,
        "created_by": rec.created_by,
        "created_at": rec.created_at,
    }


@router.get("/bank-reconciliations", response_model=ApiResponse)
async def list_bank_reconciliations(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出银行调节表,支持 book_id 与 period 过滤,默认 limit 100,最大 500。"""
    stmt = select(FinanceCenterMumarenBankReconciliation).where(
        FinanceCenterMumarenBankReconciliation.book_id == book_id
    )
    if period is not None:
        stmt = stmt.where(FinanceCenterMumarenBankReconciliation.period == period)
    stmt = stmt.order_by(
        FinanceCenterMumarenBankReconciliation.period.desc(),
        FinanceCenterMumarenBankReconciliation.id.desc(),
    ).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_bank_reconciliation_data(row) for row in rows])


@router.post("/bank-reconciliations", response_model=ApiResponse)
async def create_bank_reconciliation(
    body: BankReconciliationInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建银行调节表(workflow_status=draft);不自动审核、不自动过账。"""
    rec = FinanceCenterMumarenBankReconciliation(
        book_id=body.book_id,
        cash_account_id=body.cash_account_id,
        period=body.period,
        bank_balance=body.bank_balance,
        book_balance=body.book_balance,
        adjusted_balance=body.adjusted_balance,
        items_json=body.items_json,
        workflow_status="draft",
        created_by=_actor_id(current_user),
    )
    db.add(rec)
    await db.flush()
    await _add_audit_log(
        db, book_id=body.book_id, action="create_bank_reconciliation",
        operator_id=_actor_id(current_user),
        detail=f"创建银行调节表 {body.period} 账户 {body.cash_account_id}",
    )
    return ApiResponse.ok(data=_bank_reconciliation_data(rec), message="银行调节表已创建")


@router.put("/bank-reconciliations/{rec_id}", response_model=ApiResponse)
async def update_bank_reconciliation(
    rec_id: int,
    body: BankReconciliationUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新银行调节表(仅 draft 可改);强制同账簿校验。"""
    rec = await db.get(FinanceCenterMumarenBankReconciliation, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"银行调节表 {rec_id} 不存在")
    if rec.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if rec.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {rec.workflow_status},仅 draft 可修改")
    for field in ("cash_account_id", "period", "bank_balance", "book_balance", "adjusted_balance", "items_json"):
        value = getattr(body, field)
        if value is not None:
            setattr(rec, field, value)
    await db.flush()
    await _add_audit_log(
        db, book_id=rec.book_id, action="update_bank_reconciliation",
        operator_id=_actor_id(current_user),
        detail=f"更新银行调节表 {rec.period} 账户 {rec.cash_account_id}",
    )
    return ApiResponse.ok(data=_bank_reconciliation_data(rec), message="银行调节表已更新")


@router.delete("/bank-reconciliations/{rec_id}", response_model=ApiResponse)
async def delete_bank_reconciliation(
    rec_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除银行调节表(仅 draft 可删);强制同账簿校验。"""
    rec = await db.get(FinanceCenterMumarenBankReconciliation, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"银行调节表 {rec_id} 不存在")
    if rec.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if rec.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {rec.workflow_status},仅 draft 可删除")
    desc = f"{rec.period} 账户 {rec.cash_account_id}"
    await db.delete(rec)
    await _add_audit_log(
        db, book_id=book_id, action="delete_bank_reconciliation",
        operator_id=_actor_id(current_user),
        detail=f"删除银行调节表 {desc}",
    )
    return ApiResponse.ok(message="银行调节表已删除")


# ===========================================================================
# Task 14: 辅助核算 CRUD(finance_center_mumaren_auxiliary_accountings)
# ===========================================================================

class AuxiliaryAccountingInput(BaseModel):
    book_id: int = Field(ge=1)
    aux_type: str = Field(pattern=r"^(customer|supplier|employee|project|department)$")
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = Field(default=None, ge=1)


class AuxiliaryAccountingUpdate(BaseModel):
    book_id: int = Field(ge=1)
    aux_type: str | None = Field(default=None, pattern=r"^(customer|supplier|employee|project|department)$")
    code: str | None = None
    name: str | None = None
    parent_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


def _auxiliary_accounting_data(aux: FinanceCenterMumarenAuxiliaryAccounting) -> dict:
    return {
        "id": aux.id,
        "book_id": aux.book_id,
        "aux_type": aux.aux_type,
        "code": aux.code,
        "name": aux.name,
        "parent_id": aux.parent_id,
        "is_active": aux.is_active,
        "created_by": aux.created_by,
        "created_at": aux.created_at,
    }


@router.get("/auxiliary-accountings", response_model=ApiResponse)
async def list_auxiliary_accountings(
    book_id: int = Query(ge=1),
    aux_type: str | None = Query(
        default=None, pattern=r"^(customer|supplier|employee|project|department)$"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出辅助核算,支持 book_id 与 aux_type 过滤,默认 limit 100,最大 500。"""
    stmt = select(FinanceCenterMumarenAuxiliaryAccounting).where(
        FinanceCenterMumarenAuxiliaryAccounting.book_id == book_id
    )
    if aux_type is not None:
        stmt = stmt.where(FinanceCenterMumarenAuxiliaryAccounting.aux_type == aux_type)
    stmt = stmt.order_by(
        FinanceCenterMumarenAuxiliaryAccounting.aux_type,
        FinanceCenterMumarenAuxiliaryAccounting.id.desc(),
    ).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_auxiliary_accounting_data(row) for row in rows])


@router.post("/auxiliary-accountings", response_model=ApiResponse)
async def create_auxiliary_accounting(
    body: AuxiliaryAccountingInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建辅助核算;不自动审核、不自动过账。"""
    aux = FinanceCenterMumarenAuxiliaryAccounting(
        book_id=body.book_id,
        aux_type=body.aux_type,
        code=body.code,
        name=body.name,
        parent_id=body.parent_id,
        is_active=True,
        created_by=_actor_id(current_user),
    )
    db.add(aux)
    await db.flush()
    await _add_audit_log(
        db, book_id=body.book_id, action="create_auxiliary_accounting",
        operator_id=_actor_id(current_user),
        detail=f"创建辅助核算 {body.aux_type} {body.code}",
    )
    return ApiResponse.ok(data=_auxiliary_accounting_data(aux), message="辅助核算已创建")


@router.put("/auxiliary-accountings/{aux_id}", response_model=ApiResponse)
async def update_auxiliary_accounting(
    aux_id: int,
    body: AuxiliaryAccountingUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新辅助核算;强制同账簿校验。"""
    aux = await db.get(FinanceCenterMumarenAuxiliaryAccounting, aux_id)
    if aux is None:
        raise HTTPException(status_code=404, detail=f"辅助核算 {aux_id} 不存在")
    if aux.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    for field in ("aux_type", "code", "name", "parent_id", "is_active"):
        value = getattr(body, field)
        if value is not None:
            setattr(aux, field, value)
    await db.flush()
    await _add_audit_log(
        db, book_id=aux.book_id, action="update_auxiliary_accounting",
        operator_id=_actor_id(current_user),
        detail=f"更新辅助核算 {aux.aux_type} {aux.code}",
    )
    return ApiResponse.ok(data=_auxiliary_accounting_data(aux), message="辅助核算已更新")


@router.delete("/auxiliary-accountings/{aux_id}", response_model=ApiResponse)
async def delete_auxiliary_accounting(
    aux_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除辅助核算:活跃账户软删除置 is_active=false;已停用账户硬删除。"""
    aux = await db.get(FinanceCenterMumarenAuxiliaryAccounting, aux_id)
    if aux is None:
        raise HTTPException(status_code=404, detail=f"辅助核算 {aux_id} 不存在")
    if aux.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    desc = f"{aux.aux_type} {aux.code}"
    if aux.is_active:
        aux.is_active = False
        await db.flush()
        await _add_audit_log(
            db, book_id=book_id, action="delete_auxiliary_accounting",
            operator_id=_actor_id(current_user),
            detail=f"停用辅助核算 {desc}",
        )
        return ApiResponse.ok(data=_auxiliary_accounting_data(aux), message="辅助核算已停用")
    await db.delete(aux)
    await _add_audit_log(
        db, book_id=book_id, action="delete_auxiliary_accounting",
        operator_id=_actor_id(current_user),
        detail=f"删除辅助核算 {desc}",
    )
    return ApiResponse.ok(message="辅助核算已删除")
