"""
账套管理 + 科目管理 API
对标虎狼 routes.py 中 api_list_books / api_create_book / api_update_book / api_switch_book
+ settings/accounts / settings/initial-balances / settings/aux
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from pydantic import BaseModel

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User
from app.models.finance.accounting import FinBook, FinAccount
from app.models.finance.settings import FinAuxCategory, FinAuxItem, FinAuditLog
from app.services.finance_book_service import create_book as svc_create_book, init_subjects as svc_init_subjects

router = APIRouter(prefix="/finance")


# ── Schemas ──
class BookCreate(BaseModel):
    book_code: str
    book_name: str
    company_name: str = "牧马人服饰"
    accounting_standard: str = "小企业会计准则"
    base_currency: str = "CNY"
    start_date: Optional[str] = None

class BookUpdate(BaseModel):
    book_name: Optional[str] = None
    company_name: Optional[str] = None
    current_period: Optional[str] = None
    safety_cash_line: Optional[float] = None
    enable_ai_summary: Optional[bool] = None
    status: Optional[str] = None

class AccountCreate(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    direction: str = "debit"
    parent_id: Optional[int] = None
    level: int = 1

class AccountUpdate(BaseModel):
    account_name: Optional[str] = None
    is_active: Optional[bool] = None

class InitBalanceItem(BaseModel):
    account_id: int
    init_debit: float = 0
    init_credit: float = 0

class AuxItemUpsert(BaseModel):
    aux_type: str
    aux_code: str
    aux_name: str
    is_active: Optional[bool] = None


AUX_TYPE_NAMES = {
    "customer": "客户",
    "supplier": "供应商",
    "department": "部门",
    "project": "项目",
    "store": "店铺",
    "employee": "员工",
}


async def _get_or_create_aux_category(db: AsyncSession, book_id: int, aux_type: str) -> FinAuxCategory:
    category = (await db.execute(
        select(FinAuxCategory).where(
            FinAuxCategory.book_id == book_id,
            FinAuxCategory.category_code == aux_type,
        )
    )).scalar_one_or_none()
    if category:
        return category
    category = FinAuxCategory(
        book_id=book_id,
        category_code=aux_type,
        category_name=AUX_TYPE_NAMES.get(aux_type, aux_type),
    )
    db.add(category)
    await db.flush()
    return category


# ═══════════════════════════════════════════════════════════
# 账套
# ═══════════════════════════════════════════════════════════

@router.get("/books")
async def list_books(
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """账套列表"""
    result = await db.execute(select(FinBook).order_by(FinBook.id))
    books = result.scalars().all()
    return {
        "books": [
            {
                "id": b.id, "book_code": b.book_code, "book_name": b.book_name,
                "company_name": b.company_name, "accounting_standard": b.accounting_standard,
                "base_currency": b.base_currency, "start_date": b.start_date,
                "current_period": b.current_period, "status": b.status,
                "safety_cash_line": float(b.safety_cash_line or 0),
                "enable_ai_summary": b.enable_ai_summary,
            }
            for b in books
        ],
        "current_book_id": 1,  # 默认账套
    }


@router.post("/books", status_code=201)
async def create_book(
    body: BookCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """创建新账套（自动初始化科目 + 辅助核算）"""
    book = FinBook(
        book_code=body.book_code, book_name=body.book_name,
        company_name=body.company_name, accounting_standard=body.accounting_standard,
        base_currency=body.base_currency, start_date=body.start_date,
        created_by=current_user.username if hasattr(current_user, 'username') else str(current_user.id),
    )
    db.add(book)
    await db.flush()

    # 从默认账套复制科目
    src_accounts = await db.execute(
        select(FinAccount).where(FinAccount.book_id == 1).order_by(FinAccount.account_code)
    )
    for sa in src_accounts.scalars():
        db.add(FinAccount(
            book_id=book.id, account_code=sa.account_code, account_name=sa.account_name,
            account_type=sa.account_type, direction=sa.direction, level=sa.level,
        ))

    # 初始化辅助核算
    for code, name in [("customer","客户"),("supplier","供应商"),("department","部门"),
                        ("project","项目"),("store","店铺"),("employee","员工")]:
        db.add(FinAuxCategory(book_id=book.id, category_code=code, category_name=name))

    await db.flush()

    # 审计日志
    db.add(FinAuditLog(book_id=book.id, operator=str(current_user.id), action="create_book", target=f"book:{book.id}", detail=body.book_name))

    return {"id": book.id, "book_code": book.book_code, "book_name": book.book_name}


@router.put("/books/{book_id}")
async def update_book(
    book_id: int, body: BookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """更新账套"""
    result = await db.execute(select(FinBook).where(FinBook.id == book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(404, "账套不存在")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(book, k, v)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 会计科目
# ═══════════════════════════════════════════════════════════

@router.get("/accounts")
async def list_accounts(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """科目列表"""
    result = await db.execute(
        select(FinAccount).where(FinAccount.book_id == book_id).order_by(FinAccount.account_code)
    )
    return {
        "accounts": [
            {
                "id": a.id, "account_code": a.account_code, "account_name": a.account_name,
                "account_type": a.account_type, "direction": a.direction, "level": a.level,
                "parent_id": a.parent_id, "is_active": a.is_active,
            }
            for a in result.scalars()
        ]
    }


@router.post("/settings/accounts", status_code=201)
async def create_account(
    body: AccountCreate, book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """新增科目"""
    acct = FinAccount(book_id=book_id, **body.model_dump())
    db.add(acct)
    await db.flush()
    db.add(FinAuditLog(book_id=book_id, operator=str(current_user.id), action="create_account", target=f"account:{acct.id}", detail=body.account_code))
    return {"id": acct.id, "account_code": acct.account_code}


@router.put("/settings/accounts/{account_id}")
async def update_account(
    account_id: int, body: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """更新科目"""
    result = await db.execute(select(FinAccount).where(FinAccount.id == account_id))
    acct = result.scalar_one_or_none()
    if not acct:
        raise HTTPException(404, "科目不存在")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(acct, k, v)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 期初余额
# ═══════════════════════════════════════════════════════════

@router.get("/settings/initial-balances")
async def get_initial_balances(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """期初余额列表"""
    result = await db.execute(text("""
        SELECT a.id, a.account_code, a.account_name, a.account_type, a.direction,
               COALESCE(lb.opening_debit, 0) AS init_debit,
               COALESCE(lb.opening_credit, 0) AS init_credit
        FROM fin_accounts a
        LEFT JOIN fin_ledger_balances lb ON lb.account_id = a.id
            AND lb.book_id = :bid AND lb.period = (SELECT start_date FROM fin_books WHERE id = :bid)
        WHERE a.book_id = :bid AND a.is_active = true
        ORDER BY a.account_code
    """), {"bid": book_id})
    return {
        "rows": [
            {
                "id": r["id"], "account_code": r["account_code"], "account_name": r["account_name"],
                "account_type": r["account_type"], "direction": r["direction"],
                "init_debit": float(r["init_debit"]), "init_credit": float(r["init_credit"]),
            }
            for r in result.mappings()
        ]
    }


# ═══════════════════════════════════════════════════════════
# 辅助核算
# ═══════════════════════════════════════════════════════════

@router.get("/aux/categories")
async def list_aux_categories(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    result = await db.execute(
        select(FinAuxCategory).where(FinAuxCategory.book_id == book_id)
    )
    return {"rows": [{"id": c.id, "category_code": c.category_code, "category_name": c.category_name, "is_active": c.is_active} for c in result.scalars()]}


@router.get("/aux/items")
async def list_aux_items(
    category_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    result = await db.execute(
        select(FinAuxItem).where(FinAuxItem.category_id == category_id)
    )
    return {"rows": [{"id": i.id, "item_code": i.item_code, "item_name": i.item_name, "is_active": i.is_active} for i in result.scalars()]}


@router.post("/aux/items", status_code=201)
async def create_aux_item(
    category_id: int, item_code: str, item_name: str,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    item = FinAuxItem(category_id=category_id, item_code=item_code, item_name=item_name)
    db.add(item)
    await db.flush()
    return {"id": item.id}


def _aux_item_row(item: FinAuxItem, category: FinAuxCategory):
    return {
        "id": item.id,
        "aux_type": category.category_code,
        "aux_code": item.item_code,
        "aux_name": item.item_name,
        "is_active": item.is_active,
    }


@router.get("/aux-items")
async def list_aux_items_flat(
    book_id: int = Query(1),
    aux_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    stmt = (
        select(FinAuxItem, FinAuxCategory)
        .join(FinAuxCategory, FinAuxItem.category_id == FinAuxCategory.id)
        .where(FinAuxCategory.book_id == book_id)
        .order_by(FinAuxCategory.category_code, FinAuxItem.item_code)
    )
    if aux_type:
        stmt = stmt.where(FinAuxCategory.category_code == aux_type)
    result = await db.execute(stmt)
    return {"rows": [_aux_item_row(item, category) for item, category in result.all()]}


@router.post("/aux-items", status_code=201)
async def create_aux_item_flat(
    payload: AuxItemUpsert,
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    if not payload.aux_type or not payload.aux_code or not payload.aux_name:
        raise HTTPException(status_code=400, detail="核算类别、编码、名称不能为空")
    category = await _get_or_create_aux_category(db, book_id, payload.aux_type)
    existing = (await db.execute(
        select(FinAuxItem).where(
            FinAuxItem.category_id == category.id,
            FinAuxItem.item_code == payload.aux_code,
        )
    )).scalar_one_or_none()
    if existing:
        if existing.is_active:
            raise HTTPException(status_code=400, detail="同类别下编码已存在")
        existing.item_name = payload.aux_name
        existing.is_active = True if payload.is_active is None else payload.is_active
        item = existing
    else:
        item = FinAuxItem(
            category_id=category.id,
            item_code=payload.aux_code,
            item_name=payload.aux_name,
            is_active=True if payload.is_active is None else payload.is_active,
        )
        db.add(item)
    await db.commit()
    await db.refresh(item)
    return _aux_item_row(item, category)


@router.put("/aux-items/{item_id}")
async def update_aux_item_flat(
    item_id: int,
    payload: AuxItemUpsert,
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    row = (await db.execute(
        select(FinAuxItem, FinAuxCategory)
        .join(FinAuxCategory, FinAuxItem.category_id == FinAuxCategory.id)
        .where(FinAuxItem.id == item_id, FinAuxCategory.book_id == book_id)
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="核算项不存在")
    item, category = row
    target_category = category
    if payload.aux_type and payload.aux_type != category.category_code:
        target_category = await _get_or_create_aux_category(db, book_id, payload.aux_type)
    duplicate = (await db.execute(
        select(FinAuxItem).where(
            FinAuxItem.category_id == target_category.id,
            FinAuxItem.item_code == payload.aux_code,
            FinAuxItem.id != item_id,
        )
    )).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=400, detail="同类别下编码已存在")
    item.category_id = target_category.id
    item.item_code = payload.aux_code
    item.item_name = payload.aux_name
    if payload.is_active is not None:
        item.is_active = payload.is_active
    await db.commit()
    await db.refresh(item)
    return _aux_item_row(item, target_category)


@router.delete("/aux-items/{item_id}")
async def delete_aux_item_flat(
    item_id: int,
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    row = (await db.execute(
        select(FinAuxItem, FinAuxCategory)
        .join(FinAuxCategory, FinAuxItem.category_id == FinAuxCategory.id)
        .where(FinAuxItem.id == item_id, FinAuxCategory.book_id == book_id)
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="核算项不存在")
    item, _ = row
    item.is_active = False
    await db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 审计日志
# ═══════════════════════════════════════════════════════════

@router.get("/audit-logs")
async def list_audit_logs(
    book_id: int = Query(1),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    result = await db.execute(
        select(FinAuditLog).where(FinAuditLog.book_id == book_id)
        .order_by(FinAuditLog.created_at.desc()).limit(limit)
    )
    return {
        "rows": [
            {"id": l.id, "action": l.action, "target": l.target, "detail": l.detail,
             "operator": l.operator, "created_at": str(l.created_at) if l.created_at else ""}
            for l in result.scalars()
        ],
        "total": 0,
    }

# ═══════════════════════════════════════════════════════════
# 账套操作：重新初始化科目
# ═══════════════════════════════════════════════════════════

@router.post("/books/{book_id}/init-subjects", status_code=200)
async def reinit_subjects(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Re-init subjects from default template (skip existing ones)"""
    book = await db.get(FinBook, book_id)
    if not book:
        raise HTTPException(404, "账套不存在")
    n = await svc_init_subjects(db, book_id, operator=str(current_user.id))
    await db.commit()
    return {"book_id": book_id, "subjects_added": n}


# ═══════════════════════════════════════════════════════════
# 凭证模板
# ═══════════════════════════════════════════════════════════
from app.models.finance.accounting import FinVoucherTemplate


class VoucherTemplateCreate(BaseModel):
    name: str
    voucher_type: str = "记"
    summary: str = ""
    lines: list = []


@router.get("/voucher-templates")
async def list_voucher_templates(
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    result = await db.execute(
        select(FinVoucherTemplate)
        .where(FinVoucherTemplate.book_id == book_id)
        .order_by(FinVoucherTemplate.id)
    )
    return {
        "templates": [
            {
                "id": t.id, "name": t.name, "voucher_type": t.voucher_type,
                "summary": t.summary, "lines": t.lines,
                "created_by": t.created_by,
                "created_at": str(t.created_at) if t.created_at else "",
            }
            for t in result.scalars()
        ]
    }


@router.post("/voucher-templates", status_code=201)
async def create_voucher_template(
    body: VoucherTemplateCreate,
    book_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    tpl = FinVoucherTemplate(
        book_id=book_id, name=body.name, voucher_type=body.voucher_type,
        summary=body.summary, lines=body.lines, created_by=str(current_user.id),
    )
    db.add(tpl)
    await db.flush()
    await db.commit()
    return {"id": tpl.id, "name": tpl.name}


@router.put("/voucher-templates/{tpl_id}")
async def update_voucher_template(
    tpl_id: int,
    body: VoucherTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    tpl = await db.get(FinVoucherTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "模板不存在")
    tpl.name = body.name
    tpl.voucher_type = body.voucher_type
    tpl.summary = body.summary
    tpl.lines = body.lines
    await db.commit()
    return {"ok": True}


@router.delete("/voucher-templates/{tpl_id}", status_code=204)
async def delete_voucher_template(
    tpl_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    tpl = await db.get(FinVoucherTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "模板不存在")
    await db.delete(tpl)
    await db.commit()
