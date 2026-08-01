"""Independent Mumaren AR/AP and tax read/write APIs.

These endpoints operate only on the isolated ``finance_center_mumaren`` schema.
They do not create vouchers and never call the legacy Huabang finance routers.
The write path follows the fixed "draft → finance review → manual settle/pay"
flow and never auto-generates or posts accounting entries.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.mumaren_finance_center import (
    require_mumaren_finance_access,
    require_mumaren_voucher_post,
    require_mumaren_voucher_review,
    require_mumaren_voucher_write,
)
from app.core.database import get_db
from app.core.store_whitelist import ALLOWED_STORE_CODES
from app.models.mumaren_finance_center import (
    FinanceCenterMumarenAuditLog,
    FinanceCenterMumarenBook,
    FinanceCenterMumarenFiscalPeriod,
    FinanceCenterMumarenVoucher,
)
from app.models.mumaren_finance_center_domains import (
    FinanceCenterMumarenCashAccount,
    FinanceCenterMumarenCashFlow,
    FinanceCenterMumarenDailyAdCost,
    FinanceCenterMumarenDailyOperatingParameter,
    FinanceCenterMumarenArApSettlement,
    FinanceCenterMumarenFixedAsset,
    FinanceCenterMumarenInvoice,
    FinanceCenterMumarenPayableOrder,
    FinanceCenterMumarenPayableOrderLine,
    FinanceCenterMumarenPayroll,
    FinanceCenterMumarenReceivableOrder,
    FinanceCenterMumarenReceivableOrderLine,
    FinanceCenterMumarenStoreGroup,
    FinanceCenterMumarenTaxRecord,
    FinanceCenterMumarenTaxType,
)
from app.services.mumaren_finance_center.business import depreciation_for_period
from app.models.sys import SysUser
from app.schemas.common import ApiResponse
from app.services.mumaren_finance_center.ar_ap import (
    CrossBookViolationError,
    InvalidOrderTransition,
    build_aging,
    create_ar_ap_order,
    review_ar_ap_order,
    settle_ar_ap_order,
)
from app.services.mumaren_finance_center.tax import (
    CrossBookTaxViolationError,
    InvalidTaxTransition,
    build_tax_alerts,
    create_tax_record,
    pay_tax_record,
    review_tax_record,
    tax_record_balance,
)


router = APIRouter(prefix="/finance-center/mumaren", tags=["牧马人财务中心：往来与税务"])


_DAILY_PARAMETER_FIELDS = frozenset({
    "platform_income_rate", "estimated_return_rate_pct", "refund_only_rate_pct",
    "freight_insurance_unit_cost", "express_unit_cost", "package_unit_cost",
    "promotion_unit_cost", "return_labor_unit_cost", "goods_loss_unit_cost",
    "return_rate_warning_threshold_pct",
})


def _is_allowed_operating_store(store_code: str) -> bool:
    return store_code.strip().upper() in ALLOWED_STORE_CODES


def _daily_parameter_data(row: FinanceCenterMumarenDailyOperatingParameter) -> dict:
    return {
        "id": row.id, "book_id": row.book_id, "period": row.period,
        "store_code": row.store_code, "store_name": row.store_name or row.store_code,
        **{field: getattr(row, field) for field in _DAILY_PARAMETER_FIELDS},
        "warning_enabled": row.warning_enabled, "remark": row.remark,
        "updated_at": row.updated_at,
    }


def _daily_ad_cost_data(row: FinanceCenterMumarenDailyAdCost) -> dict:
    return {
        "id": row.id, "book_id": row.book_id, "business_date": row.business_date,
        "store_code": row.store_code, "store_name": row.store_name or row.store_code,
        "platform": row.platform, "ad_cost": row.ad_cost,
        "compensation_amount": row.compensation_amount, "remark": row.remark,
        "updated_at": row.updated_at,
    }


async def _require_writable_operating_book(db: AsyncSession, book_id: int) -> FinanceCenterMumarenBook:
    """Return a current book, or fail before a history-write reaches the DB trigger."""
    book = await db.get(FinanceCenterMumarenBook, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="账簿不存在")
    if book.is_readonly:
        raise HTTPException(status_code=409, detail="金蝶迁移账簿只读，不能维护经营设置")
    return book


class StoreGroupInput(BaseModel):
    book_id: int = Field(ge=1)
    group_name: str = Field(min_length=1, max_length=128)
    store_codes: list[str] = Field(min_length=1, max_length=7)

    @field_validator("store_codes")
    @classmethod
    def normalize_store_codes(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))
        if not normalized or any(not _is_allowed_operating_store(value) for value in normalized):
            raise ValueError("店铺必须是华邦允许的销售门店")
        return normalized


class DailyOperatingParameterInput(BaseModel):
    store_code: str = Field(min_length=1, max_length=32)
    store_name: str | None = Field(default=None, max_length=128)
    platform_income_rate: Decimal = Field(default=Decimal("1"), ge=0, le=2)
    estimated_return_rate_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    refund_only_rate_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    freight_insurance_unit_cost: Decimal = Field(default=Decimal("0"), ge=0, le=1000000)
    express_unit_cost: Decimal = Field(default=Decimal("0"), ge=0, le=1000000)
    package_unit_cost: Decimal = Field(default=Decimal("0"), ge=0, le=1000000)
    promotion_unit_cost: Decimal = Field(default=Decimal("0"), ge=0, le=1000000)
    return_labor_unit_cost: Decimal = Field(default=Decimal("0"), ge=0, le=1000000)
    goods_loss_unit_cost: Decimal = Field(default=Decimal("0"), ge=0, le=1000000)
    return_rate_warning_threshold_pct: Decimal = Field(default=Decimal("8"), ge=0, le=100)
    warning_enabled: bool = True
    remark: str | None = Field(default=None, max_length=500)

    @field_validator("store_code")
    @classmethod
    def ensure_allowed_store(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _is_allowed_operating_store(normalized):
            raise ValueError("店铺必须是华邦允许的销售门店")
        return normalized


class DailyOperatingParameterSaveInput(BaseModel):
    book_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    rows: list[DailyOperatingParameterInput] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def reject_duplicate_store_codes(self):
        if len({row.store_code for row in self.rows}) != len(self.rows):
            raise ValueError("店铺编码不能重复")
        return self


class DailyOperatingParameterBatchInput(BaseModel):
    book_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    field: str = Field(min_length=1, max_length=64)
    value: Decimal = Field(ge=0, le=1000000)
    store_codes: list[str] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_known_field(self):
        if self.field not in _DAILY_PARAMETER_FIELDS:
            raise ValueError("不支持批量维护该参数字段")
        if self.field in {"platform_income_rate"} and self.value > 2:
            raise ValueError("平台收入系数不能超过 2")
        if self.field.endswith("_pct") and self.value > 100:
            raise ValueError("百分比参数不能超过 100")
        self.store_codes = StoreGroupInput(book_id=self.book_id, group_name="批量", store_codes=self.store_codes).store_codes
        return self


class DailyParameterCopyInput(BaseModel):
    book_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    overwrite: bool = False


class DailyAdCostInput(BaseModel):
    store_code: str = Field(min_length=1, max_length=32)
    store_name: str | None = Field(default=None, max_length=128)
    platform: str | None = Field(default=None, max_length=64)
    ad_cost: Decimal = Field(default=Decimal("0"), ge=0, le=100000000)
    compensation_amount: Decimal = Field(default=Decimal("0"), ge=0, le=100000000)
    remark: str | None = Field(default=None, max_length=500)

    @field_validator("store_code")
    @classmethod
    def ensure_allowed_store(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _is_allowed_operating_store(normalized):
            raise ValueError("店铺必须是华邦允许的销售门店")
        return normalized


class DailyAdCostSaveInput(BaseModel):
    book_id: int = Field(ge=1)
    business_date: date
    rows: list[DailyAdCostInput] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def reject_duplicate_store_codes(self):
        if len({row.store_code for row in self.rows}) != len(self.rows):
            raise ValueError("店铺编码不能重复")
        return self


class DailyAdCostBatchInput(BaseModel):
    book_id: int = Field(ge=1)
    business_date: date
    store_codes: list[str] = Field(min_length=1, max_length=7)
    ad_cost: Decimal = Field(ge=0, le=100000000)

    @field_validator("store_codes")
    @classmethod
    def normalize_store_codes(cls, values: list[str]) -> list[str]:
        return StoreGroupInput(book_id=1, group_name="批量", store_codes=values).store_codes


def _apply_daily_parameter(
    row: FinanceCenterMumarenDailyOperatingParameter,
    payload: DailyOperatingParameterInput,
    *,
    actor_id: int,
) -> None:
    row.store_name = payload.store_name or payload.store_code
    for field in _DAILY_PARAMETER_FIELDS:
        setattr(row, field, getattr(payload, field))
    row.warning_enabled = payload.warning_enabled
    row.remark = payload.remark
    row.updated_by = actor_id


async def _upsert_daily_parameter_rows(
    db: AsyncSession,
    *,
    book_id: int,
    period: str,
    rows: list[DailyOperatingParameterInput],
    actor_id: int,
) -> list[FinanceCenterMumarenDailyOperatingParameter]:
    codes = [row.store_code for row in rows]
    existing = {
        row.store_code: row
        for row in (await db.execute(select(FinanceCenterMumarenDailyOperatingParameter).where(
            FinanceCenterMumarenDailyOperatingParameter.book_id == book_id,
            FinanceCenterMumarenDailyOperatingParameter.period == period,
            FinanceCenterMumarenDailyOperatingParameter.store_code.in_(codes),
        ))).scalars()
    }
    result = []
    for payload in rows:
        row = existing.get(payload.store_code)
        if row is None:
            row = FinanceCenterMumarenDailyOperatingParameter(
                book_id=book_id, period=period, store_code=payload.store_code,
            )
            db.add(row)
        _apply_daily_parameter(row, payload, actor_id=actor_id)
        result.append(row)
    await db.flush()
    return result


async def _upsert_daily_ad_cost_rows(
    db: AsyncSession,
    *,
    book_id: int,
    business_date: date,
    rows: list[DailyAdCostInput],
    actor_id: int,
) -> list[FinanceCenterMumarenDailyAdCost]:
    codes = [row.store_code for row in rows]
    existing = {
        row.store_code: row
        for row in (await db.execute(select(FinanceCenterMumarenDailyAdCost).where(
            FinanceCenterMumarenDailyAdCost.book_id == book_id,
            FinanceCenterMumarenDailyAdCost.business_date == business_date,
            FinanceCenterMumarenDailyAdCost.store_code.in_(codes),
        ))).scalars()
    }
    result = []
    for payload in rows:
        row = existing.get(payload.store_code)
        if row is None:
            row = FinanceCenterMumarenDailyAdCost(
                book_id=book_id, business_date=business_date, store_code=payload.store_code,
            )
            db.add(row)
        row.store_name = payload.store_name or payload.store_code
        row.platform = payload.platform
        row.ad_cost = payload.ad_cost
        row.compensation_amount = payload.compensation_amount
        row.remark = payload.remark
        row.updated_by = actor_id
        result.append(row)
    await db.flush()
    return result


@router.get("/operating/store-groups", response_model=ApiResponse)
async def list_operating_store_groups(
    book_id: int = Query(ge=1),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(FinanceCenterMumarenStoreGroup).where(
        FinanceCenterMumarenStoreGroup.book_id == book_id,
    ).order_by(FinanceCenterMumarenStoreGroup.group_name))).scalars())
    return ApiResponse.ok(data=[{"id": row.id, "book_id": row.book_id, "group_name": row.group_name, "store_codes": row.store_codes} for row in rows])


@router.post("/operating/store-groups", response_model=ApiResponse)
async def create_operating_store_group(
    body: StoreGroupInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    await _require_writable_operating_book(db, body.book_id)
    row = FinanceCenterMumarenStoreGroup(
        book_id=body.book_id, group_name=body.group_name.strip(), store_codes=body.store_codes, created_by=_actor_id(current_user),
    )
    db.add(row)
    try:
        await db.flush()
    except Exception as error:
        raise HTTPException(status_code=409, detail="店铺组名称已存在") from error
    _add_audit_log(db, book_id=body.book_id, action="create_store_group", operator_id=_actor_id(current_user), detail=f"创建店铺组 {row.group_name}")
    return ApiResponse.ok(data={"id": row.id, "book_id": row.book_id, "group_name": row.group_name, "store_codes": row.store_codes})


@router.put("/operating/store-groups/{group_id}", response_model=ApiResponse)
async def update_operating_store_group(
    group_id: int,
    body: StoreGroupInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    await _require_writable_operating_book(db, body.book_id)
    row = await db.get(FinanceCenterMumarenStoreGroup, group_id)
    if row is None or row.book_id != body.book_id:
        raise HTTPException(status_code=404, detail="店铺组不存在")
    row.group_name, row.store_codes = body.group_name.strip(), body.store_codes
    await db.flush()
    _add_audit_log(db, book_id=body.book_id, action="update_store_group", operator_id=_actor_id(current_user), detail=f"更新店铺组 {row.group_name}")
    return ApiResponse.ok(data={"id": row.id, "book_id": row.book_id, "group_name": row.group_name, "store_codes": row.store_codes})


@router.delete("/operating/store-groups/{group_id}", response_model=ApiResponse)
async def delete_operating_store_group(
    group_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    await _require_writable_operating_book(db, book_id)
    row = await db.get(FinanceCenterMumarenStoreGroup, group_id)
    if row is None or row.book_id != book_id:
        raise HTTPException(status_code=404, detail="店铺组不存在")
    await db.delete(row)
    _add_audit_log(db, book_id=book_id, action="delete_store_group", operator_id=_actor_id(current_user), detail=f"删除店铺组 {row.group_name}")
    return ApiResponse.ok(data=None)


@router.get("/operating/daily-parameters", response_model=ApiResponse)
async def list_daily_operating_parameters(
    book_id: int = Query(ge=1),
    period: str = Query(pattern=r"^\d{4}-\d{2}$"),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(FinanceCenterMumarenDailyOperatingParameter).where(
        FinanceCenterMumarenDailyOperatingParameter.book_id == book_id,
        FinanceCenterMumarenDailyOperatingParameter.period == period,
    ))).scalars())
    by_code = {row.store_code: row for row in rows}
    data = [_daily_parameter_data(row) for row in rows]
    for code in sorted(ALLOWED_STORE_CODES - by_code.keys()):
        data.append(_daily_parameter_data(FinanceCenterMumarenDailyOperatingParameter(
            book_id=book_id, period=period, store_code=code, store_name=code,
        )))
    return ApiResponse.ok(data=sorted(data, key=lambda row: row["store_code"]))


@router.post("/operating/daily-parameters/batch-save", response_model=ApiResponse)
async def save_daily_operating_parameters(
    body: DailyOperatingParameterSaveInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    await _require_writable_operating_book(db, body.book_id)
    rows = await _upsert_daily_parameter_rows(db, book_id=body.book_id, period=body.period, rows=body.rows, actor_id=_actor_id(current_user))
    _add_audit_log(db, book_id=body.book_id, action="save_daily_operating_parameters", operator_id=_actor_id(current_user), detail=f"保存 {body.period} 日报参数 {len(rows)} 条")
    return ApiResponse.ok(data=[_daily_parameter_data(row) for row in rows])


@router.post("/operating/daily-parameters/batch-field", response_model=ApiResponse)
async def batch_update_daily_operating_parameter(
    body: DailyOperatingParameterBatchInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    await _require_writable_operating_book(db, body.book_id)
    existing = {row.store_code: row for row in (await db.execute(select(FinanceCenterMumarenDailyOperatingParameter).where(
        FinanceCenterMumarenDailyOperatingParameter.book_id == body.book_id,
        FinanceCenterMumarenDailyOperatingParameter.period == body.period,
        FinanceCenterMumarenDailyOperatingParameter.store_code.in_(body.store_codes),
    ))).scalars()}
    result = []
    for code in body.store_codes:
        row = existing.get(code)
        if row is None:
            row = FinanceCenterMumarenDailyOperatingParameter(book_id=body.book_id, period=body.period, store_code=code, store_name=code, updated_by=_actor_id(current_user))
            db.add(row)
        setattr(row, body.field, body.value)
        row.updated_by = _actor_id(current_user)
        result.append(row)
    await db.flush()
    _add_audit_log(db, book_id=body.book_id, action="batch_update_daily_operating_parameter", operator_id=_actor_id(current_user), detail=f"批量更新 {body.period} 参数 {body.field}，{len(result)} 家店铺")
    return ApiResponse.ok(data=[_daily_parameter_data(row) for row in result])


@router.post("/operating/daily-parameters/copy-previous", response_model=ApiResponse)
async def copy_previous_daily_operating_parameters(
    body: DailyParameterCopyInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    await _require_writable_operating_book(db, body.book_id)
    year, month = (int(part) for part in body.period.split("-"))
    previous_period = f"{year - 1:04d}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"
    source = list((await db.execute(select(FinanceCenterMumarenDailyOperatingParameter).where(
        FinanceCenterMumarenDailyOperatingParameter.book_id == body.book_id,
        FinanceCenterMumarenDailyOperatingParameter.period == previous_period,
    ))).scalars())
    if not source:
        raise HTTPException(status_code=404, detail="上月没有可复制的日报参数")
    current = {row.store_code: row for row in (await db.execute(select(FinanceCenterMumarenDailyOperatingParameter).where(
        FinanceCenterMumarenDailyOperatingParameter.book_id == body.book_id,
        FinanceCenterMumarenDailyOperatingParameter.period == body.period,
    ))).scalars()}
    copied = []
    for source_row in source:
        target = current.get(source_row.store_code)
        if target is not None and not body.overwrite:
            continue
        if target is None:
            target = FinanceCenterMumarenDailyOperatingParameter(book_id=body.book_id, period=body.period, store_code=source_row.store_code)
            db.add(target)
        for field in _DAILY_PARAMETER_FIELDS:
            setattr(target, field, getattr(source_row, field))
        target.store_name = source_row.store_name
        target.warning_enabled = source_row.warning_enabled
        target.remark = source_row.remark
        target.updated_by = _actor_id(current_user)
        copied.append(target)
    await db.flush()
    _add_audit_log(db, book_id=body.book_id, action="copy_daily_operating_parameters", operator_id=_actor_id(current_user), detail=f"从 {previous_period} 复制到 {body.period}，{len(copied)} 条")
    return ApiResponse.ok(data={"source_period": previous_period, "copied_count": len(copied), "rows": [_daily_parameter_data(row) for row in copied]})


@router.get("/operating/daily-ad-costs", response_model=ApiResponse)
async def list_daily_ad_costs(
    book_id: int = Query(ge=1),
    business_date: date = Query(),
    platform: str | None = Query(default=None, max_length=64),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    statement = select(FinanceCenterMumarenDailyAdCost).where(
        FinanceCenterMumarenDailyAdCost.book_id == book_id,
        FinanceCenterMumarenDailyAdCost.business_date == business_date,
    )
    if platform:
        statement = statement.where(FinanceCenterMumarenDailyAdCost.platform == platform)
    rows = list((await db.execute(statement)).scalars())
    by_code = {row.store_code: row for row in rows}
    data = [_daily_ad_cost_data(row) for row in rows]
    if not platform:
        for code in sorted(ALLOWED_STORE_CODES - by_code.keys()):
            data.append(_daily_ad_cost_data(FinanceCenterMumarenDailyAdCost(book_id=book_id, business_date=business_date, store_code=code, store_name=code)))
    return ApiResponse.ok(data=sorted(data, key=lambda row: row["store_code"]))


@router.post("/operating/daily-ad-costs/batch-save", response_model=ApiResponse)
async def save_daily_ad_costs(
    body: DailyAdCostSaveInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    await _require_writable_operating_book(db, body.book_id)
    rows = await _upsert_daily_ad_cost_rows(db, book_id=body.book_id, business_date=body.business_date, rows=body.rows, actor_id=_actor_id(current_user))
    _add_audit_log(db, book_id=body.book_id, action="save_daily_ad_costs", operator_id=_actor_id(current_user), detail=f"保存 {body.business_date} 广告费 {len(rows)} 条")
    return ApiResponse.ok(data=[_daily_ad_cost_data(row) for row in rows])


@router.post("/operating/daily-ad-costs/batch-ad-cost", response_model=ApiResponse)
async def batch_update_daily_ad_cost(
    body: DailyAdCostBatchInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    await _require_writable_operating_book(db, body.book_id)
    rows = await _upsert_daily_ad_cost_rows(
        db, book_id=body.book_id, business_date=body.business_date,
        rows=[DailyAdCostInput(store_code=code, ad_cost=body.ad_cost) for code in body.store_codes], actor_id=_actor_id(current_user),
    )
    _add_audit_log(db, book_id=body.book_id, action="batch_update_daily_ad_cost", operator_id=_actor_id(current_user), detail=f"批量设置 {body.business_date} 广告费，{len(rows)} 家店铺")
    return ApiResponse.ok(data=[_daily_ad_cost_data(row) for row in rows])


def _actor_id(user: SysUser) -> int:
    return int(user.id)


class ArApOrderLineInput(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    spec: str | None = Field(default=None, max_length=255)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0)
    amount: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    remark: str | None = Field(default=None, max_length=500)


class ArApOrderInput(BaseModel):
    book_id: int = Field(ge=1)
    order_type: str = Field(pattern=r"^(receivable|payable)$")
    order_no: str = Field(min_length=1, max_length=64)
    order_date: date
    counterparty_id: int | None = Field(default=None, ge=1)
    counterparty_name: str = Field(min_length=1, max_length=128)
    total_amount: Decimal = Field(ge=0)
    remark: str | None = Field(default=None, max_length=500)
    lines: list[ArApOrderLineInput] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_detail_total(self):
        if self.lines and sum((line.amount for line in self.lines), Decimal("0")) != self.total_amount:
            raise ValueError("明细金额合计必须等于单据总金额")
        return self


class ArApSettleInput(BaseModel):
    settlement_date: date
    amount: Decimal = Field(gt=0)
    remark: str | None = Field(default=None, max_length=500)


class TaxRecordInput(BaseModel):
    book_id: int = Field(ge=1)
    tax_type_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    tax_amount: Decimal = Field(ge=0)
    due_date: date | None = None
    remark: str | None = Field(default=None, max_length=500)


class TaxPayInput(BaseModel):
    payment_date: date
    amount: Decimal = Field(gt=0)
    remark: str | None = Field(default=None, max_length=500)


def _order_data(order, *, has_details: bool = False) -> dict:
    return {
        "id": order.id,
        "book_id": order.book_id,
        "order_type": getattr(order, "settlement_type", None) or type(order).__name__,
        "order_no": order.order_no,
        "order_date": order.order_date,
        "counterparty_id": order.counterparty_id,
        "counterparty_name": order.counterparty_name,
        "total_amount": order.total_amount,
        "settled_amount": order.settled_amount,
        "settlement_status": order.settlement_status,
        "workflow_status": order.workflow_status,
        "has_details": has_details,
    }


_AR_AP_LINE_MODELS = {
    "receivable": FinanceCenterMumarenReceivableOrderLine,
    "payable": FinanceCenterMumarenPayableOrderLine,
}


def _ar_ap_line_data(line) -> dict:
    return {
        "id": line.id, "line_no": line.line_no, "item_name": line.item_name,
        "spec": line.spec, "quantity": line.quantity, "unit_price": line.unit_price,
        "amount": line.amount, "tax_rate": line.tax_rate, "tax_amount": line.tax_amount,
        "remark": line.remark,
    }


def _ar_ap_settlement_data(settlement) -> dict:
    return {
        "id": settlement.id, "settlement_date": settlement.settlement_date,
        "amount": settlement.amount, "remark": settlement.remark,
        "created_by": settlement.created_by, "created_at": settlement.created_at,
    }


async def _ar_ap_order_detail_data(db: AsyncSession, order, order_type: Literal["receivable", "payable"]) -> dict:
    line_model = _AR_AP_LINE_MODELS[order_type]
    lines = list((await db.execute(
        select(line_model).where(line_model.order_id == order.id).order_by(line_model.line_no, line_model.id)
    )).scalars())
    settlements = list((await db.execute(
        select(FinanceCenterMumarenArApSettlement)
        .where(
            FinanceCenterMumarenArApSettlement.book_id == order.book_id,
            FinanceCenterMumarenArApSettlement.settlement_type == order_type,
            FinanceCenterMumarenArApSettlement.order_id == order.id,
        )
        .order_by(FinanceCenterMumarenArApSettlement.settlement_date.desc(), FinanceCenterMumarenArApSettlement.id.desc())
    )).scalars())
    return {**_order_data(order), "lines": [_ar_ap_line_data(line) for line in lines], "settlements": [_ar_ap_settlement_data(row) for row in settlements]}


def _tax_record_data(record, *, tax_code=None, tax_name=None) -> dict:
    return {
        "id": record.id,
        "book_id": record.book_id,
        "tax_type_id": record.tax_type_id,
        "tax_code": tax_code,
        "tax_name": tax_name,
        "period": record.period,
        "tax_amount": record.tax_amount,
        "paid_amount": record.paid_amount,
        "unpaid_amount": tax_record_balance(record.tax_amount, record.paid_amount),
        "due_date": record.due_date,
        "status": record.status,
        "workflow_status": record.workflow_status,
    }


@router.get("/ar-ap/aging", response_model=ApiResponse)
async def get_ar_ap_aging(
    book_id: int = Query(ge=1),
    order_type: str = Query(default="receivable", pattern=r"^(receivable|payable)$"),
    as_of: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """Return ageing derived only from current, isolated AR/AP orders."""
    model = FinanceCenterMumarenReceivableOrder if order_type == "receivable" else FinanceCenterMumarenPayableOrder
    cutoff = as_of or date.today()
    rows = list((await db.execute(
        select(model).where(model.book_id == book_id, model.order_date <= cutoff).order_by(model.order_date, model.id).limit(limit)
    )).scalars())
    settled_as_of = {}
    if rows:
        settlement_rows = (await db.execute(
            select(FinanceCenterMumarenArApSettlement.order_id, func.coalesce(func.sum(FinanceCenterMumarenArApSettlement.amount), 0))
            .where(
                FinanceCenterMumarenArApSettlement.book_id == book_id,
                FinanceCenterMumarenArApSettlement.settlement_type == order_type,
                FinanceCenterMumarenArApSettlement.settlement_date <= cutoff,
                FinanceCenterMumarenArApSettlement.order_id.in_([row.id for row in rows]),
            )
            .group_by(FinanceCenterMumarenArApSettlement.order_id)
        )).all()
        settled_as_of = {order_id: amount for order_id, amount in settlement_rows}
    result = build_aging(({
        "counterparty_name": row.counterparty_name,
        "order_no": row.order_no,
        "order_date": row.order_date,
        "total_amount": row.total_amount,
        "settled_amount": settled_as_of.get(row.id, 0),
    } for row in rows), as_of=cutoff)
    return ApiResponse.ok(data={"order_type": order_type, **result})


@router.get("/tax-types", response_model=ApiResponse)
async def list_tax_types(
    book_id: int = Query(ge=1),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """List active tax types configured for one isolated finance book."""
    rows = list((await db.execute(
        select(FinanceCenterMumarenTaxType)
        .where(
            FinanceCenterMumarenTaxType.book_id == book_id,
            FinanceCenterMumarenTaxType.is_active.is_(True),
        )
        .order_by(FinanceCenterMumarenTaxType.tax_code, FinanceCenterMumarenTaxType.id)
    )).scalars().all())
    return ApiResponse.ok(data=[{
        "id": row.id,
        "tax_code": row.tax_code,
        "tax_name": row.tax_name,
        "default_rate": float(row.default_rate),
    } for row in rows])


@router.get("/tax/alerts", response_model=ApiResponse)
async def get_tax_alerts(
    book_id: int = Query(ge=1),
    today: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """Return unpaid/near-due tax alerts without creating accounting entries."""
    rows = list((await db.execute(
        select(FinanceCenterMumarenTaxRecord, FinanceCenterMumarenTaxType.tax_name)
        .join(FinanceCenterMumarenTaxType, FinanceCenterMumarenTaxType.id == FinanceCenterMumarenTaxRecord.tax_type_id)
        .where(FinanceCenterMumarenTaxRecord.book_id == book_id)
        .order_by(FinanceCenterMumarenTaxRecord.due_date, FinanceCenterMumarenTaxRecord.id)
        .limit(limit)
    )).all())
    records = [{
        "tax_name": tax_name,
        "period": record.period,
        "tax_amount": record.tax_amount,
        "paid_amount": record.paid_amount,
        "due_date": record.due_date,
    } for record, tax_name in rows]
    alerts = build_tax_alerts(records, today=today or date.today())
    return ApiResponse.ok(data={"alerts": alerts, "record_count": len(records)})


@router.get("/tax/records", response_model=ApiResponse)
async def get_tax_records(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """List isolated tax records and calculated unpaid balances."""
    rows = list((await db.execute(
        select(FinanceCenterMumarenTaxRecord, FinanceCenterMumarenTaxType.tax_code, FinanceCenterMumarenTaxType.tax_name)
        .join(FinanceCenterMumarenTaxType, FinanceCenterMumarenTaxType.id == FinanceCenterMumarenTaxRecord.tax_type_id)
        .where(FinanceCenterMumarenTaxRecord.book_id == book_id)
        .order_by(FinanceCenterMumarenTaxRecord.period.desc(), FinanceCenterMumarenTaxRecord.id.desc())
        .limit(limit)
    )).all())
    return ApiResponse.ok(data=[{
        "id": record.id, "tax_code": tax_code, "tax_name": tax_name,
        "period": record.period, "tax_amount": record.tax_amount,
        "paid_amount": record.paid_amount,
        "unpaid_amount": tax_record_balance(record.tax_amount, record.paid_amount),
        "due_date": record.due_date, "status": record.status,
        "workflow_status": record.workflow_status,
    } for record, tax_code, tax_name in rows])


# ---------------------------------------------------------------------------
# AR/AP 写入端点:草稿 → 财务审核 → 人工结算(不产生任何凭证分录)
# ---------------------------------------------------------------------------

@router.post("/ar-ap/orders", response_model=ApiResponse)
async def create_ar_ap_order_endpoint(
    body: ArApOrderInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建 AR/AP 草稿单据;强制同账簿校验,不自动生成凭证。"""
    try:
        order = await create_ar_ap_order(
            db,
            book_id=body.book_id,
            order_type=body.order_type,
            order_no=body.order_no,
            order_date=body.order_date,
            counterparty_id=body.counterparty_id,
            counterparty_name=body.counterparty_name,
            total_amount=body.total_amount,
            operator_id=_actor_id(current_user),
            remark=body.remark,
            lines=[line.model_dump() for line in body.lines],
        )
    except CrossBookViolationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _add_audit_log(
        db, book_id=body.book_id, action="create_ar_ap_order",
        operator_id=_actor_id(current_user),
        detail=f"创建{body.order_type}单据 {body.order_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=await _ar_ap_order_detail_data(db, order, body.order_type), message="AR/AP 草稿已创建")


@router.post("/ar-ap/orders/{order_id}/review", response_model=ApiResponse)
async def review_ar_ap_order_endpoint(
    order_id: int,
    order_type: Literal["receivable", "payable"] = Query(),
    current_user: SysUser = Depends(require_mumaren_voucher_review),
    db: AsyncSession = Depends(get_db),
):
    """财务审核 AR/AP 草稿;仅 draft → reviewed,不产生凭证分录。"""
    try:
        order = await review_ar_ap_order(
            db, order_id=order_id, order_type=order_type, operator_id=_actor_id(current_user),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidOrderTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _add_audit_log(
        db, book_id=order.book_id, action="review_ar_ap_order",
        operator_id=_actor_id(current_user),
        detail=f"审核AR/AP单据 {order_id}",
    )
    await db.flush()
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 单据已审核")


@router.post("/ar-ap/orders/{order_id}/settle", response_model=ApiResponse)
async def settle_ar_ap_order_endpoint(
    order_id: int,
    body: ArApSettleInput,
    order_type: Literal["receivable", "payable"] = Query(),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """人工结算 AR/AP 单据;防超额,不产生凭证分录。"""
    try:
        order = await settle_ar_ap_order(
            db, order_id=order_id, order_type=order_type,
            settlement_date=body.settlement_date, amount=body.amount,
            operator_id=_actor_id(current_user), remark=body.remark,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidOrderTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _add_audit_log(
        db, book_id=order.book_id, action="settle_ar_ap_order",
        operator_id=_actor_id(current_user),
        detail=f"结算AR/AP单据 {order_id} 金额 {body.amount}",
    )
    await db.flush()
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 单据已结算")


async def _review_ar_ap_with_fallback(db: AsyncSession, *, order_id: int, operator_id: int):
    """按 order_id 尝试 receivable/payable 两种模型审核。"""
    for order_type in ("receivable", "payable"):
        try:
            return await review_ar_ap_order(db, order_id=order_id, order_type=order_type, operator_id=operator_id)
        except LookupError:
            continue
    raise LookupError(f"AR/AP 单据 {order_id} 不存在")


async def _settle_ar_ap_with_fallback(db: AsyncSession, *, order_id: int, settlement_date: date, amount, operator_id: int, remark: str | None = None):
    """按 order_id 尝试 receivable/payable 两种模型结算。"""
    for order_type in ("receivable", "payable"):
        try:
            return await settle_ar_ap_order(
                db, order_id=order_id, order_type=order_type,
                settlement_date=settlement_date, amount=amount,
                operator_id=operator_id, remark=remark,
            )
        except LookupError:
            continue
    raise LookupError(f"AR/AP 单据 {order_id} 不存在")


# ---------------------------------------------------------------------------
# 税务写入端点:草稿 → 财务审核 → 人工缴税(不产生任何凭证分录)
# ---------------------------------------------------------------------------

@router.post("/tax/records", response_model=ApiResponse)
async def create_tax_record_endpoint(
    body: TaxRecordInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建税务草稿单据;强制同账簿校验,不自动生成凭证。"""
    try:
        record = await create_tax_record(
            db,
            book_id=body.book_id,
            tax_type_id=body.tax_type_id,
            period=body.period,
            tax_amount=body.tax_amount,
            operator_id=_actor_id(current_user),
            due_date=body.due_date,
            remark=body.remark,
        )
    except CrossBookTaxViolationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _add_audit_log(
        db, book_id=body.book_id, action="create_tax_record",
        operator_id=_actor_id(current_user),
        detail=f"创建税务记录 期间 {body.period}",
    )
    await db.flush()
    return ApiResponse.ok(data=_tax_record_data(record), message="税务草稿已创建")


@router.post("/tax/records/{record_id}/review", response_model=ApiResponse)
async def review_tax_record_endpoint(
    record_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_review),
    db: AsyncSession = Depends(get_db),
):
    """财务审核税务草稿;仅 draft → reviewed,不产生凭证分录。"""
    try:
        record = await review_tax_record(db, record_id=record_id, operator_id=_actor_id(current_user))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidTaxTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _add_audit_log(
        db, book_id=record.book_id, action="review_tax_record",
        operator_id=_actor_id(current_user),
        detail=f"审核税务记录 {record_id}",
    )
    await db.flush()
    return ApiResponse.ok(data=_tax_record_data(record), message="税务单据已审核")


@router.post("/tax/records/{record_id}/pay", response_model=ApiResponse)
async def pay_tax_record_endpoint(
    record_id: int,
    body: TaxPayInput,
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """人工缴税;防超额,不产生凭证分录。"""
    try:
        record = await pay_tax_record(
            db, record_id=record_id, payment_date=body.payment_date,
            amount=body.amount, operator_id=_actor_id(current_user), remark=body.remark,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidTaxTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    _add_audit_log(
        db, book_id=record.book_id, action="pay_tax_record",
        operator_id=_actor_id(current_user),
        detail=f"缴税 {record_id} 金额 {body.amount}",
    )
    await db.flush()
    return ApiResponse.ok(data=_tax_record_data(record), message="税务单据已缴税")


# ===========================================================================
# 通用审计日志写入助手:确保与主操作在同一事务内 flush
# ===========================================================================

def _add_audit_log(
    db: AsyncSession,
    *,
    book_id: int | None,
    action: str,
    operator_id: int,
    detail: str | None = None,
    voucher_id: int | None = None,
) -> None:
    db.add(FinanceCenterMumarenAuditLog(
        book_id=book_id,
        voucher_id=voucher_id,
        action=action,
        operator_id=operator_id,
        detail=detail,
    ))


def _period_code_from_date(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


# ===========================================================================
# Task 2: 固定资产 CRUD(复用 finance_center_mumaren_fixed_assets)
# ===========================================================================

class FixedAssetInput(BaseModel):
    book_id: int = Field(ge=1)
    asset_code: str = Field(min_length=1, max_length=64)
    asset_name: str = Field(min_length=1, max_length=255)
    asset_category: str | None = Field(default=None, max_length=64)
    purchase_date: date
    original_value: Decimal = Field(ge=0)
    residual_value: Decimal = Field(default=Decimal("0"), ge=0)
    useful_life_months: int = Field(ge=1)


class FixedAssetUpdate(BaseModel):
    book_id: int = Field(ge=1)
    asset_name: str | None = None
    asset_category: str | None = None
    purchase_date: date | None = None
    original_value: Decimal | None = Field(default=None, ge=0)
    residual_value: Decimal | None = Field(default=None, ge=0)
    useful_life_months: int | None = Field(default=None, ge=1)
    status: Literal["disposed"] | None = None


def _fixed_asset_data(asset: FinanceCenterMumarenFixedAsset) -> dict:
    return {
        "id": asset.id,
        "book_id": asset.book_id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "asset_category": asset.asset_category,
        "purchase_date": asset.purchase_date,
        "original_value": asset.original_value,
        "residual_value": asset.residual_value,
        "useful_life_months": asset.useful_life_months,
        "accumulated_depreciation": asset.accumulated_depreciation,
        "status": asset.status,
    }


@router.get("/fixed-assets", response_model=ApiResponse)
async def list_fixed_assets(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出固定资产,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenFixedAsset)
        .where(FinanceCenterMumarenFixedAsset.book_id == book_id)
        .order_by(FinanceCenterMumarenFixedAsset.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_fixed_asset_data(row) for row in rows])


@router.post("/fixed-assets", response_model=ApiResponse)
async def create_fixed_asset(
    body: FixedAssetInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建固定资产(初始 draft);不自动审核、不自动过账。"""
    asset = FinanceCenterMumarenFixedAsset(
        book_id=body.book_id,
        asset_code=body.asset_code,
        asset_name=body.asset_name,
        asset_category=body.asset_category,
        purchase_date=body.purchase_date,
        original_value=body.original_value,
        residual_value=body.residual_value,
        useful_life_months=body.useful_life_months,
        accumulated_depreciation=Decimal("0"),
        status="draft",
    )
    db.add(asset)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_fixed_asset",
        operator_id=_actor_id(current_user),
        detail=f"创建固定资产 {body.asset_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fixed_asset_data(asset), message="固定资产已创建")


@router.put("/fixed-assets/{asset_id}", response_model=ApiResponse)
async def update_fixed_asset(
    asset_id: int,
    body: FixedAssetUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新固定资产(仅 draft 或 active 状态可改);强制同账簿校验。"""
    asset = await db.get(FinanceCenterMumarenFixedAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"固定资产 {asset_id} 不存在")
    if asset.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if asset.status not in ("draft", "active"):
        raise HTTPException(status_code=409, detail=f"当前状态 {asset.status},不可修改")
    for field in ("asset_name", "asset_category", "purchase_date", "original_value", "residual_value", "useful_life_months"):
        value = getattr(body, field)
        if value is not None:
            setattr(asset, field, value)
    if body.status is not None:
        asset.status = body.status
    await db.flush()
    _add_audit_log(
        db, book_id=asset.book_id, action="update_fixed_asset",
        operator_id=_actor_id(current_user),
        detail=f"更新固定资产 {asset.asset_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fixed_asset_data(asset), message="固定资产已更新")


@router.delete("/fixed-assets/{asset_id}", response_model=ApiResponse)
async def delete_fixed_asset(
    asset_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除固定资产(仅 draft 可删);强制同账簿校验。"""
    asset = await db.get(FinanceCenterMumarenFixedAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"固定资产 {asset_id} 不存在")
    if asset.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if asset.status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {asset.status},仅 draft 可删除")
    asset_code = asset.asset_code
    await db.delete(asset)
    _add_audit_log(
        db, book_id=book_id, action="delete_fixed_asset",
        operator_id=_actor_id(current_user),
        detail=f"删除固定资产 {asset_code}",
    )
    await db.flush()
    return ApiResponse.ok(message="固定资产已删除")


@router.post("/fixed-assets/{asset_id}/depreciate", response_model=ApiResponse)
async def depreciate_fixed_asset(
    asset_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """月折旧计提:accumulated_depreciation += (原值-残值)/使用月数,封顶在可折旧额。"""
    asset = await db.get(FinanceCenterMumarenFixedAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"固定资产 {asset_id} 不存在")
    if asset.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿操作")
    try:
        monthly = depreciation_for_period(
            original_value=asset.original_value,
            residual_value=asset.residual_value,
            useful_life_months=asset.useful_life_months,
            already_depreciated=asset.accumulated_depreciation,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    asset.accumulated_depreciation = Decimal(asset.accumulated_depreciation) + monthly
    await db.flush()
    _add_audit_log(
        db, book_id=asset.book_id, action="depreciate_fixed_asset",
        operator_id=_actor_id(current_user),
        detail=f"计提折旧 {asset.asset_code} 本次 {monthly}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fixed_asset_data(asset), message="折旧已计提")


# ===========================================================================
# Task 3: 发票 CRUD(复用 finance_center_mumaren_invoices)
# ===========================================================================

class InvoiceInput(BaseModel):
    book_id: int = Field(ge=1)
    invoice_no: str = Field(min_length=1, max_length=64)
    invoice_type: str = Field(min_length=1, max_length=32)
    invoice_date: date
    counterparty_name: str | None = Field(default=None, max_length=128)
    amount: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)


class InvoiceUpdate(BaseModel):
    book_id: int = Field(ge=1)
    invoice_type: str | None = None
    invoice_date: date | None = None
    counterparty_name: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)


def _invoice_data(invoice: FinanceCenterMumarenInvoice) -> dict:
    return {
        "id": invoice.id,
        "book_id": invoice.book_id,
        "invoice_no": invoice.invoice_no,
        "invoice_type": invoice.invoice_type,
        "invoice_date": invoice.invoice_date,
        "counterparty_name": invoice.counterparty_name,
        "amount": invoice.amount,
        "tax_amount": invoice.tax_amount,
        "verification_status": invoice.verification_status,
        "workflow_status": invoice.workflow_status,
    }


@router.get("/invoices", response_model=ApiResponse)
async def list_invoices(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出发票,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenInvoice)
        .where(FinanceCenterMumarenInvoice.book_id == book_id)
        .order_by(FinanceCenterMumarenInvoice.invoice_date.desc(), FinanceCenterMumarenInvoice.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_invoice_data(row) for row in rows])


@router.post("/invoices", response_model=ApiResponse)
async def create_invoice(
    body: InvoiceInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建发票草稿;不自动核验、不自动过账。"""
    invoice = FinanceCenterMumarenInvoice(
        book_id=body.book_id,
        invoice_no=body.invoice_no,
        invoice_type=body.invoice_type,
        invoice_date=body.invoice_date,
        counterparty_name=body.counterparty_name,
        amount=body.amount,
        tax_amount=body.tax_amount,
        verification_status="draft",
        workflow_status="draft",
    )
    db.add(invoice)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_invoice",
        operator_id=_actor_id(current_user),
        detail=f"创建发票 {body.invoice_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_invoice_data(invoice), message="发票已创建")


@router.put("/invoices/{invoice_id}", response_model=ApiResponse)
async def update_invoice(
    invoice_id: int,
    body: InvoiceUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新发票(仅 draft 可改);强制同账簿校验。"""
    invoice = await db.get(FinanceCenterMumarenInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"发票 {invoice_id} 不存在")
    if invoice.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if invoice.verification_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前核验状态 {invoice.verification_status},不可修改")
    for field in ("invoice_type", "invoice_date", "counterparty_name", "amount", "tax_amount"):
        value = getattr(body, field)
        if value is not None:
            setattr(invoice, field, value)
    await db.flush()
    _add_audit_log(
        db, book_id=invoice.book_id, action="update_invoice",
        operator_id=_actor_id(current_user),
        detail=f"更新发票 {invoice.invoice_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_invoice_data(invoice), message="发票已更新")


@router.delete("/invoices/{invoice_id}", response_model=ApiResponse)
async def delete_invoice(
    invoice_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除发票(仅 draft 可删);强制同账簿校验。"""
    invoice = await db.get(FinanceCenterMumarenInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"发票 {invoice_id} 不存在")
    if invoice.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if invoice.verification_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前核验状态 {invoice.verification_status},仅 draft 可删除")
    invoice_no = invoice.invoice_no
    await db.delete(invoice)
    _add_audit_log(
        db, book_id=book_id, action="delete_invoice",
        operator_id=_actor_id(current_user),
        detail=f"删除发票 {invoice_no}",
    )
    await db.flush()
    return ApiResponse.ok(message="发票已删除")


@router.post("/invoices/{invoice_id}/verify", response_model=ApiResponse)
async def verify_invoice(
    invoice_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """发票核验:draft → verified;不自动过账。"""
    invoice = await db.get(FinanceCenterMumarenInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"发票 {invoice_id} 不存在")
    if invoice.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿操作")
    if invoice.verification_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前核验状态 {invoice.verification_status},无法核验")
    invoice.verification_status = "verified"
    await db.flush()
    _add_audit_log(
        db, book_id=invoice.book_id, action="verify_invoice",
        operator_id=_actor_id(current_user),
        detail=f"核验发票 {invoice.invoice_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_invoice_data(invoice), message="发票已核验")


# ===========================================================================
# Task 4: 出纳账户与流水(复用 cash_accounts + cash_flows)
# ===========================================================================

class CashAccountInput(BaseModel):
    book_id: int = Field(ge=1)
    account_code: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=128)
    account_type: str = Field(default="bank", pattern=r"^(bank|cash)$")
    currency: str = Field(default="CNY", max_length=8)


class CashAccountUpdate(BaseModel):
    book_id: int = Field(ge=1)
    account_name: str | None = None
    account_type: str | None = Field(default=None, pattern=r"^(bank|cash)$")
    currency: str | None = None


class CashFlowInput(BaseModel):
    book_id: int = Field(ge=1)
    cash_account_id: int = Field(ge=1)
    flow_date: date
    direction: str = Field(pattern=r"^(in|out)$")
    amount: Decimal = Field(gt=0)
    category: str | None = Field(default=None, max_length=64)
    counterparty_name: str | None = Field(default=None, max_length=128)


def _cash_account_data(account: FinanceCenterMumarenCashAccount) -> dict:
    return {
        "id": account.id,
        "book_id": account.book_id,
        "account_code": account.account_code,
        "account_name": account.account_name,
        "account_type": account.account_type,
        "currency": account.currency,
        "is_active": account.is_active,
    }


def _cash_flow_data(flow: FinanceCenterMumarenCashFlow) -> dict:
    return {
        "id": flow.id,
        "book_id": flow.book_id,
        "cash_account_id": flow.cash_account_id,
        "flow_date": flow.flow_date,
        "direction": flow.direction,
        "amount": flow.amount,
        "category": flow.category,
        "counterparty_name": flow.counterparty_name,
        "workflow_status": flow.workflow_status,
    }


@router.get("/cash-accounts", response_model=ApiResponse)
async def list_cash_accounts(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出出纳账户,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenCashAccount)
        .where(FinanceCenterMumarenCashAccount.book_id == book_id)
        .order_by(FinanceCenterMumarenCashAccount.id.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_cash_account_data(row) for row in rows])


@router.post("/cash-accounts", response_model=ApiResponse)
async def create_cash_account(
    body: CashAccountInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建出纳账户;不自动审核、不自动过账。"""
    account = FinanceCenterMumarenCashAccount(
        book_id=body.book_id,
        account_code=body.account_code,
        account_name=body.account_name,
        account_type=body.account_type,
        currency=body.currency,
        is_active=True,
    )
    db.add(account)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_cash_account",
        operator_id=_actor_id(current_user),
        detail=f"创建出纳账户 {body.account_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_cash_account_data(account), message="出纳账户已创建")


@router.put("/cash-accounts/{account_id}", response_model=ApiResponse)
async def update_cash_account(
    account_id: int,
    body: CashAccountUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新出纳账户;强制同账簿校验。"""
    account = await db.get(FinanceCenterMumarenCashAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"出纳账户 {account_id} 不存在")
    if account.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    for field in ("account_name", "account_type", "currency"):
        value = getattr(body, field)
        if value is not None:
            setattr(account, field, value)
    await db.flush()
    _add_audit_log(
        db, book_id=account.book_id, action="update_cash_account",
        operator_id=_actor_id(current_user),
        detail=f"更新出纳账户 {account.account_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_cash_account_data(account), message="出纳账户已更新")


@router.delete("/cash-accounts/{account_id}", response_model=ApiResponse)
async def delete_cash_account(
    account_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除出纳账户:活跃账户软删除置 is_active=false;已停用账户硬删除。"""
    account = await db.get(FinanceCenterMumarenCashAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"出纳账户 {account_id} 不存在")
    if account.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    account_code = account.account_code
    if account.is_active:
        account.is_active = False
        await db.flush()
        _add_audit_log(
            db, book_id=book_id, action="delete_cash_account",
            operator_id=_actor_id(current_user),
            detail=f"停用出纳账户 {account_code}",
        )
        await db.flush()
        return ApiResponse.ok(data=_cash_account_data(account), message="出纳账户已停用")
    await db.delete(account)
    _add_audit_log(
        db, book_id=book_id, action="delete_cash_account",
        operator_id=_actor_id(current_user),
        detail=f"删除出纳账户 {account_code}",
    )
    await db.flush()
    return ApiResponse.ok(message="出纳账户已删除")


@router.get("/cash-flows", response_model=ApiResponse)
async def list_cash_flows(
    book_id: int = Query(ge=1),
    cash_account_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出资金流水,支持 book_id 与 cash_account_id 过滤,默认 limit 100,最大 500。"""
    stmt = select(FinanceCenterMumarenCashFlow).where(FinanceCenterMumarenCashFlow.book_id == book_id)
    if cash_account_id is not None:
        stmt = stmt.where(FinanceCenterMumarenCashFlow.cash_account_id == cash_account_id)
    stmt = stmt.order_by(FinanceCenterMumarenCashFlow.flow_date.desc(), FinanceCenterMumarenCashFlow.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_cash_flow_data(row) for row in rows])


@router.post("/cash-flows", response_model=ApiResponse)
async def create_cash_flow(
    body: CashFlowInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建资金流水草稿;强制同账簿校验,不自动过账。"""
    account = await db.get(FinanceCenterMumarenCashAccount, body.cash_account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"出纳账户 {body.cash_account_id} 不存在")
    if account.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="出纳账户与目标账簿不一致,禁止跨账簿写入")
    flow = FinanceCenterMumarenCashFlow(
        book_id=body.book_id,
        cash_account_id=body.cash_account_id,
        flow_date=body.flow_date,
        direction=body.direction,
        amount=body.amount,
        category=body.category,
        counterparty_name=body.counterparty_name,
        workflow_status="draft",
    )
    db.add(flow)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_cash_flow",
        operator_id=_actor_id(current_user),
        detail=f"创建资金流水 {body.direction} {body.amount} 账户 {body.cash_account_id}",
    )
    await db.flush()
    return ApiResponse.ok(data=_cash_flow_data(flow), message="资金流水已创建")


# ===========================================================================
# Task 5: 工资 CRUD(复用 payrolls)
# ===========================================================================

class PayrollInput(BaseModel):
    book_id: int = Field(ge=1)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    employee_no: str = Field(min_length=1, max_length=64)
    employee_name: str = Field(min_length=1, max_length=128)
    gross_amount: Decimal = Field(ge=0)
    deduction_amount: Decimal = Field(default=Decimal("0"), ge=0)
    net_amount: Decimal = Field(ge=0)


class PayrollUpdate(BaseModel):
    book_id: int = Field(ge=1)
    employee_name: str | None = None
    gross_amount: Decimal | None = Field(default=None, ge=0)
    deduction_amount: Decimal | None = Field(default=None, ge=0)
    net_amount: Decimal | None = Field(default=None, ge=0)


def _payroll_data(payroll: FinanceCenterMumarenPayroll) -> dict:
    return {
        "id": payroll.id,
        "book_id": payroll.book_id,
        "period": payroll.period,
        "employee_no": payroll.employee_no,
        "employee_name": payroll.employee_name,
        "gross_amount": payroll.gross_amount,
        "deduction_amount": payroll.deduction_amount,
        "net_amount": payroll.net_amount,
        "workflow_status": payroll.workflow_status,
        "voucher_id": payroll.voucher_id,
    }


@router.get("/payrolls", response_model=ApiResponse)
async def list_payrolls(
    book_id: int = Query(ge=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出工资,支持 book_id 与 period 过滤,默认 limit 100,最大 500。"""
    stmt = select(FinanceCenterMumarenPayroll).where(FinanceCenterMumarenPayroll.book_id == book_id)
    if period is not None:
        stmt = stmt.where(FinanceCenterMumarenPayroll.period == period)
    stmt = stmt.order_by(FinanceCenterMumarenPayroll.period.desc(), FinanceCenterMumarenPayroll.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_payroll_data(row) for row in rows])


@router.post("/payrolls", response_model=ApiResponse)
async def create_payroll(
    body: PayrollInput,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """创建工资草稿;不自动发放、不自动过账。"""
    payroll = FinanceCenterMumarenPayroll(
        book_id=body.book_id,
        period=body.period,
        employee_no=body.employee_no,
        employee_name=body.employee_name,
        gross_amount=body.gross_amount,
        deduction_amount=body.deduction_amount,
        net_amount=body.net_amount,
        workflow_status="draft",
    )
    db.add(payroll)
    await db.flush()
    _add_audit_log(
        db, book_id=body.book_id, action="create_payroll",
        operator_id=_actor_id(current_user),
        detail=f"创建工资 {body.period} {body.employee_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_payroll_data(payroll), message="工资已创建")


@router.put("/payrolls/{payroll_id}", response_model=ApiResponse)
async def update_payroll(
    payroll_id: int,
    body: PayrollUpdate,
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """更新工资(仅 draft 可改);强制同账簿校验。"""
    payroll = await db.get(FinanceCenterMumarenPayroll, payroll_id)
    if payroll is None:
        raise HTTPException(status_code=404, detail=f"工资 {payroll_id} 不存在")
    if payroll.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if payroll.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {payroll.workflow_status},不可修改")
    for field in ("employee_name", "gross_amount", "deduction_amount", "net_amount"):
        value = getattr(body, field)
        if value is not None:
            setattr(payroll, field, value)
    await db.flush()
    _add_audit_log(
        db, book_id=payroll.book_id, action="update_payroll",
        operator_id=_actor_id(current_user),
        detail=f"更新工资 {payroll.period} {payroll.employee_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_payroll_data(payroll), message="工资已更新")


@router.delete("/payrolls/{payroll_id}", response_model=ApiResponse)
async def delete_payroll(
    payroll_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除工资(仅 draft 可删);强制同账簿校验。"""
    payroll = await db.get(FinanceCenterMumarenPayroll, payroll_id)
    if payroll is None:
        raise HTTPException(status_code=404, detail=f"工资 {payroll_id} 不存在")
    if payroll.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if payroll.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {payroll.workflow_status},仅 draft 可删除")
    desc = f"{payroll.period} {payroll.employee_no}"
    await db.delete(payroll)
    _add_audit_log(
        db, book_id=book_id, action="delete_payroll",
        operator_id=_actor_id(current_user),
        detail=f"删除工资 {desc}",
    )
    await db.flush()
    return ApiResponse.ok(message="工资已删除")


@router.post("/payrolls/{payroll_id}/pay", response_model=ApiResponse)
async def pay_payroll(
    payroll_id: int,
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """工资发放:draft → paid(workflow_status);不自动过账。"""
    payroll = await db.get(FinanceCenterMumarenPayroll, payroll_id)
    if payroll is None:
        raise HTTPException(status_code=404, detail=f"工资 {payroll_id} 不存在")
    if payroll.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿操作")
    if payroll.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {payroll.workflow_status},无法发放")
    payroll.workflow_status = "paid"
    await db.flush()
    _add_audit_log(
        db, book_id=payroll.book_id, action="pay_payroll",
        operator_id=_actor_id(current_user),
        detail=f"发放工资 {payroll.period} {payroll.employee_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_payroll_data(payroll), message="工资已发放")


# ===========================================================================
# Task 6: 结账(复用 fiscal_periods)
# ===========================================================================

def _fiscal_period_data(period: FinanceCenterMumarenFiscalPeriod) -> dict:
    return {
        "id": period.id,
        "book_id": period.book_id,
        "period_code": period.period_code,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "status": period.status,
        "closed_by": period.closed_by,
        "closed_at": period.closed_at,
    }


def _period_bounds(period_code: str) -> tuple[date, date]:
    """Return inclusive calendar-month bounds for a validated YYYY-MM period."""
    year, month = (int(value) for value in period_code.split("-"))
    if not 1 <= year <= 9998:
        raise HTTPException(status_code=422, detail="会计期间年份必须在 0001 至 9998 之间")
    start = date(year, month, 1)
    next_start = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, next_start.fromordinal(next_start.toordinal() - 1)


async def _period_close_precheck(db: AsyncSession, period: FinanceCenterMumarenFiscalPeriod) -> dict:
    """Expose the same blockers enforced by close, without changing accounting data."""
    not_posted_count = int((await db.execute(
        select(func.count(FinanceCenterMumarenVoucher.id)).where(
            FinanceCenterMumarenVoucher.book_id == period.book_id,
            FinanceCenterMumarenVoucher.voucher_date >= period.start_date,
            FinanceCenterMumarenVoucher.voucher_date <= period.end_date,
            FinanceCenterMumarenVoucher.status != "posted",
        )
    )).scalar_one())
    totals = (await db.execute(
        select(
            func.coalesce(func.sum(FinanceCenterMumarenVoucher.total_debit), 0),
            func.coalesce(func.sum(FinanceCenterMumarenVoucher.total_credit), 0),
        ).where(
            FinanceCenterMumarenVoucher.book_id == period.book_id,
            FinanceCenterMumarenVoucher.voucher_date >= period.start_date,
            FinanceCenterMumarenVoucher.voucher_date <= period.end_date,
        )
    )).one()
    total_debit, total_credit = Decimal(totals[0]), Decimal(totals[1])
    checks = [
        {
            "key": "not_posted", "title": "未过账凭证", "count": not_posted_count,
            "passed": not_posted_count == 0,
            "message": "本期没有未过账凭证" if not_posted_count == 0 else f"本期存在 {not_posted_count} 张未过账凭证",
        },
        {
            "key": "trial_balance", "title": "试算平衡", "count": 0 if total_debit == total_credit else 1,
            "passed": total_debit == total_credit,
            "message": "借贷平衡" if total_debit == total_credit else f"借方 {total_debit} 与贷方 {total_credit} 不平衡",
        },
    ]
    blocking_count = sum(1 for check in checks if not check["passed"])
    return {
        "period": period.period_code,
        "can_close": blocking_count == 0,
        "blocking_count": blocking_count,
        "checks": checks,
    }


@router.post("/periods/initialize", response_model=ApiResponse)
async def initialize_fiscal_period(
    book_id: int = Query(ge=1),
    period: str = Query(pattern=r"^\d{4}-\d{2}$"),
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """Initialize one writable book's calendar-month period; repeated calls are idempotent."""
    await _require_writable_operating_book(db, book_id)
    start_date, end_date = _period_bounds(period)
    existing = (await db.execute(
        select(FinanceCenterMumarenFiscalPeriod).where(
            FinanceCenterMumarenFiscalPeriod.book_id == book_id,
            FinanceCenterMumarenFiscalPeriod.period_code == period,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return ApiResponse.ok(data=_fiscal_period_data(existing), message="会计期间已存在")
    row = FinanceCenterMumarenFiscalPeriod(
        book_id=book_id, period_code=period, start_date=start_date, end_date=end_date, status="open",
    )
    db.add(row)
    await db.flush()
    _add_audit_log(
        db, book_id=book_id, action="initialize_period", operator_id=_actor_id(current_user),
        detail=f"初始化会计期间 {period}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fiscal_period_data(row), message="会计期间已初始化")


@router.post("/periods/pre-check", response_model=ApiResponse)
async def precheck_fiscal_period_close(
    book_id: int = Query(ge=1),
    period: str = Query(pattern=r"^\d{4}-\d{2}$"),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """Read-only close precheck. It never creates vouchers or changes period state."""
    row = (await db.execute(
        select(FinanceCenterMumarenFiscalPeriod).where(
            FinanceCenterMumarenFiscalPeriod.book_id == book_id,
            FinanceCenterMumarenFiscalPeriod.period_code == period,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"会计期间 {period} 不存在")
    return ApiResponse.ok(data=await _period_close_precheck(db, row))


@router.get("/periods", response_model=ApiResponse)
async def list_fiscal_periods(
    book_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出会计期间,支持 book_id 过滤,默认 limit 100,最大 500。"""
    rows = list((await db.execute(
        select(FinanceCenterMumarenFiscalPeriod)
        .where(FinanceCenterMumarenFiscalPeriod.book_id == book_id)
        .order_by(FinanceCenterMumarenFiscalPeriod.period_code.desc())
        .limit(limit)
    )).scalars())
    return ApiResponse.ok(data=[_fiscal_period_data(row) for row in rows])


@router.post("/periods/{period_id}/close", response_model=ApiResponse)
async def close_fiscal_period(
    period_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """结账:open → closed,记录 closed_by/closed_at。

    预检:本期所有凭证必须 posted、试算平衡、无未审核记录。
    """
    period = await db.get(FinanceCenterMumarenFiscalPeriod, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail=f"会计期间 {period_id} 不存在")
    if period.status != "open":
        raise HTTPException(status_code=409, detail=f"当前状态 {period.status},无法结账")
    await _require_writable_operating_book(db, period.book_id)
    precheck = await _period_close_precheck(db, period)
    if not precheck["can_close"]:
        raise HTTPException(status_code=409, detail="；".join(
            check["message"] for check in precheck["checks"] if not check["passed"]
        ))

    period.status = "closed"
    period.closed_by = _actor_id(current_user)
    period.closed_at = datetime.now(timezone.utc)
    await db.flush()
    _add_audit_log(
        db, book_id=period.book_id, action="close_period",
        operator_id=_actor_id(current_user),
        detail=f"结账期间 {period.period_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fiscal_period_data(period), message="会计期间已结账")


@router.post("/periods/{period_id}/reopen", response_model=ApiResponse)
async def reopen_fiscal_period(
    period_id: int,
    current_user: SysUser = Depends(require_mumaren_voucher_post),
    db: AsyncSession = Depends(get_db),
):
    """反结账:closed → open(需 admin 权限)。"""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="反结账需要管理员权限")
    period = await db.get(FinanceCenterMumarenFiscalPeriod, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail=f"会计期间 {period_id} 不存在")
    if period.status != "closed":
        raise HTTPException(status_code=409, detail=f"当前状态 {period.status},仅 closed 可反结账")
    await _require_writable_operating_book(db, period.book_id)
    period.status = "open"
    period.closed_by = None
    period.closed_at = None
    await db.flush()
    _add_audit_log(
        db, book_id=period.book_id, action="reopen_period",
        operator_id=_actor_id(current_user),
        detail=f"反结账期间 {period.period_code}",
    )
    await db.flush()
    return ApiResponse.ok(data=_fiscal_period_data(period), message="会计期间已反结账")


# ===========================================================================
# Task 7: 应收应付补充(复用 receivable_orders + payable_orders)
# ===========================================================================

class ArApOrderUpdate(BaseModel):
    book_id: int = Field(ge=1)
    order_date: date | None = None
    counterparty_name: str | None = None
    total_amount: Decimal | None = Field(default=None, ge=0)
    remark: str | None = Field(default=None, max_length=500)


_AR_AP_MODELS = {
    "receivable": FinanceCenterMumarenReceivableOrder,
    "payable": FinanceCenterMumarenPayableOrder,
}


def _ar_ap_filter_conditions(
    model,
    *,
    book_id: int,
    period: str | None,
    status: str | None,
    counterparty_name: str | None = None,
):
    conditions = [model.book_id == book_id]
    if period:
        conditions.append(model.period == period)
    if counterparty_name and counterparty_name.strip():
        conditions.append(model.counterparty_name.ilike(f"%{counterparty_name.strip()}%"))
    if status == "draft":
        conditions.append(model.workflow_status == "draft")
    elif status == "open":
        conditions.extend((model.workflow_status.in_(("reviewed", "posted")), model.settlement_status == "open"))
    elif status:
        conditions.append(model.settlement_status == status)
    return conditions


@router.get("/ar-ap/orders", response_model=ApiResponse)
async def list_ar_ap_orders(
    book_id: int = Query(ge=1),
    order_type: str = Query(default="receivable", pattern=r"^(receivable|payable)$"),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    status: str | None = Query(default=None, pattern=r"^(draft|open|partial|settled)$"),
    counterparty_name: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """列出租收应付单据,支持 book_id 与 order_type 过滤,默认 limit 100,最大 500。"""
    model = _AR_AP_MODELS[order_type]
    conditions = _ar_ap_filter_conditions(
        model, book_id=book_id, period=period, status=status, counterparty_name=counterparty_name,
    )
    rows = list((await db.execute(select(model).where(*conditions).order_by(model.order_date.desc(), model.id.desc()).limit(limit))).scalars())
    line_model = _AR_AP_LINE_MODELS[order_type]
    order_ids = [row.id for row in rows]
    detail_order_ids = set()
    if order_ids:
        detail_order_ids = set((await db.execute(
            select(line_model.order_id).where(line_model.order_id.in_(order_ids))
        )).scalars())
    return ApiResponse.ok(data=[_order_data(row, has_details=row.id in detail_order_ids) for row in rows])


@router.get("/ar-ap/orders/summary", response_model=ApiResponse)
async def summarize_ar_ap_orders(
    book_id: int = Query(ge=1),
    order_type: str = Query(default="receivable", pattern=r"^(receivable|payable)$"),
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    status: str | None = Query(default=None, pattern=r"^(draft|open|partial|settled)$"),
    counterparty_name: str | None = Query(default=None, max_length=128),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """汇总整个账簿的 AR/AP，不受列表明细上限影响。"""
    model = _AR_AP_MODELS[order_type]
    conditions = _ar_ap_filter_conditions(
        model, book_id=book_id, period=period, status=status, counterparty_name=counterparty_name,
    )
    row = (await db.execute(select(
        func.count(model.id),
        func.coalesce(func.sum(model.total_amount), 0),
        func.coalesce(func.sum(model.settled_amount), 0),
        func.count(model.id).filter(model.total_amount > model.settled_amount),
    ).where(*conditions))).one()
    total_amount, settled_amount = Decimal(row[1]), Decimal(row[2])
    return ApiResponse.ok(data={
        "total_count": int(row[0]),
        "total_amount": total_amount,
        "settled_amount": settled_amount,
        "outstanding_amount": total_amount - settled_amount,
        "open_count": int(row[3]),
    })


@router.get("/ar-ap/orders/{order_id}", response_model=ApiResponse)
async def get_ar_ap_order_detail(
    order_id: int,
    book_id: int = Query(ge=1),
    order_type: Literal["receivable", "payable"] = Query(),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """查询一张独立 AR/AP 单据及其明细行、人工结算流水。"""
    model = _AR_AP_MODELS[order_type]
    order = await db.get(model, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"{order_type} 单据 {order_id} 不存在")
    if order.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿查询")
    return ApiResponse.ok(data=await _ar_ap_order_detail_data(db, order, order_type))


@router.put("/ar-ap/orders/{order_id}", response_model=ApiResponse)
async def update_ar_ap_order(
    order_id: int,
    body: ArApOrderUpdate,
    order_type: str = Query(pattern=r"^(receivable|payable)$"),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """编辑 AR/AP 单据(仅 draft 可改);强制同账簿校验。"""
    model = _AR_AP_MODELS[order_type]
    order = await db.get(model, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"{order_type} 单据 {order_id} 不存在")
    if order.book_id != body.book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿修改")
    if order.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {order.workflow_status},仅 draft 可修改")
    if body.total_amount is not None and Decimal(body.total_amount) < Decimal(order.settled_amount or 0):
        raise HTTPException(status_code=400, detail="总金额不能小于已结算金额")
    if body.order_date is not None:
        order.order_date = body.order_date
        order.period = _period_code_from_date(body.order_date)
    if body.counterparty_name is not None:
        order.counterparty_name = body.counterparty_name
    if body.total_amount is not None:
        order.total_amount = body.total_amount
    if body.remark is not None:
        order.remark = body.remark
    await db.flush()
    action = f"update_{order_type}_order"
    _add_audit_log(
        db, book_id=order.book_id, action=action,
        operator_id=_actor_id(current_user),
        detail=f"编辑 {order_type} 单据 {order.order_no}",
    )
    await db.flush()
    return ApiResponse.ok(data=_order_data(order), message="AR/AP 单据已更新")


@router.delete("/ar-ap/orders/{order_id}", response_model=ApiResponse)
async def delete_ar_ap_order(
    order_id: int,
    order_type: str = Query(pattern=r"^(receivable|payable)$"),
    book_id: int = Query(ge=1),
    current_user: SysUser = Depends(require_mumaren_voucher_write),
    db: AsyncSession = Depends(get_db),
):
    """删除 AR/AP 单据(仅 draft 可删);强制同账簿校验。"""
    model = _AR_AP_MODELS[order_type]
    order = await db.get(model, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"{order_type} 单据 {order_id} 不存在")
    if order.book_id != book_id:
        raise HTTPException(status_code=400, detail="账簿不一致,禁止跨账簿删除")
    if order.workflow_status != "draft":
        raise HTTPException(status_code=409, detail=f"当前状态 {order.workflow_status},仅 draft 可删除")
    order_no = order.order_no
    await db.delete(order)
    action = f"delete_{order_type}_order"
    _add_audit_log(
        db, book_id=book_id, action=action,
        operator_id=_actor_id(current_user),
        detail=f"删除 {order_type} 单据 {order_no}",
    )
    await db.flush()
    return ApiResponse.ok(message="AR/AP 单据已删除")


# ===========================================================================
# Task 8: 操作日志查询(复用 audit_logs)
# ===========================================================================

def _audit_log_data(log: FinanceCenterMumarenAuditLog) -> dict:
    return {
        "id": log.id,
        "book_id": log.book_id,
        "voucher_id": log.voucher_id,
        "action": log.action,
        "operator_id": log.operator_id,
        "detail": log.detail,
        "created_at": log.created_at,
    }


@router.get("/audit-logs", response_model=ApiResponse)
async def list_audit_logs(
    book_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None, max_length=64),
    operator_id: int | None = Query(default=None, ge=1),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: SysUser = Depends(require_mumaren_finance_access),
    db: AsyncSession = Depends(get_db),
):
    """查询审计日志,支持 book_id/action/operator_id/日期范围过滤,按 created_at DESC 排序。"""
    conditions = []
    if book_id is not None:
        conditions.append(FinanceCenterMumarenAuditLog.book_id == book_id)
    if action is not None:
        conditions.append(FinanceCenterMumarenAuditLog.action == action)
    if operator_id is not None:
        conditions.append(FinanceCenterMumarenAuditLog.operator_id == operator_id)
    if start_date is not None:
        conditions.append(FinanceCenterMumarenAuditLog.created_at >= start_date)
    if end_date is not None:
        conditions.append(FinanceCenterMumarenAuditLog.created_at < end_date)
    stmt = select(FinanceCenterMumarenAuditLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(FinanceCenterMumarenAuditLog.created_at.desc(), FinanceCenterMumarenAuditLog.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars())
    return ApiResponse.ok(data=[_audit_log_data(row) for row in rows])
