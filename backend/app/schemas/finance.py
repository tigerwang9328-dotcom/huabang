"""
财务中心 - Schema 层（请求/响应模型）
"""
from typing import Optional, List
from datetime import date
from pydantic import BaseModel


# ── 回�� ──
class ReceiptCreate(BaseModel):
    receipt_date: date
    platform: Optional[str] = None
    store_name: Optional[str] = None
    store_id: Optional[int] = None
    amount: float = 0
    remark: Optional[str] = None


class ReceiptOut(BaseModel):
    id: int
    receipt_date: str
    platform: str
    store_name: str
    amount: float
    remark: Optional[str] = None


# ── 费用 ──
class FeeCreate(BaseModel):
    fee_date: date
    fee_type: str = "other"       # ad/logistics/commission/labor/packing/other
    description: Optional[str] = None
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    amount: float = 0
    remark: Optional[str] = None


class FeeOut(BaseModel):
    id: int
    fee_date: str
    fee_type: str
    description: Optional[str] = None
    store_name: str
    amount: float
    remark: Optional[str] = None


# ── 固定费用配置 ──
class CostConfigCreate(BaseModel):
    month: str                    # YYYY-MM
    cost_type: str                # labor/rent/packing/other
    amount: float = 0
    remark: Optional[str] = None


class CostConfigOut(BaseModel):
    id: int
    month: str
    cost_type: str
    amount: float
    remark: Optional[str] = None


# ── 总览 ──
class OverviewKPI(BaseModel):
    """财务总览 11项 KPI"""
    period: str                   # YYYY-MM
    total_sales: float = 0
    total_receipt: float = 0
    total_refund: float = 0
    total_settlement: float = 0   # 平台结算 ≈ total_receipt
    total_ad_cost: float = 0
    total_logistics: float = 0
    total_pack_cost: float = 0
    total_labor_cost: float = 0
    gross_profit: float = 0
    net_profit: float = 0
    cashflow_net: float = 0
    profit_rate: float = 0        # 净利率
    store_count: int = 0


# ── 趋势 ──
class TrendPoint(BaseModel):
    period: str
    sales: float = 0
    cost: float = 0
    profit: float = 0


# ── 店铺排行 ──
class StoreRankingItem(BaseModel):
    store_id: int
    store_name: str
    platform: str
    sales: float = 0
    refund: float = 0
    cogs: float = 0
    ad_cost: float = 0
    gross_profit: float = 0
    profit_rate: float = 0


# ── 风险预警 ──
class RiskAlertOut(BaseModel):
    id: int
    biz_date: str
    alert_type: str
    alert_level: str
    store_name: Optional[str] = None
    metric_name: Optional[str] = None
    threshold: Optional[float] = None
    actual_value: Optional[float] = None
    message: Optional[str] = None
    is_read: bool = False


# ── 现金流日报 ──
class CashflowDailyItem(BaseModel):
    biz_date: str
    total_receipt: float = 0
    total_expense: float = 0
    cashflow_net: float = 0
    store_count: int = 0
