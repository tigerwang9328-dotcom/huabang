"""
财务中心 - API 路由聚合
包含：
  compass  → 数据罗盘（经营分析）
  books    → 账套/科目/辅助核算/日志
  vouchers → 凭证管理
  reports  → 报表/账簿/结账
  business → 出纳/资产/发票/工资
  tax      → 税务管理
"""
from fastapi import APIRouter
from .compass import router as compass_router
from .books import router as books_router
from .vouchers import router as vouchers_router
from .reports import router as reports_router
from .business import router as business_router
from .tax import router as tax_router
from .ar_ap import router as ar_ap_router
from .auto_entry import router as auto_entry_router
from .reports_extra import router as reports_extra_router
from .daily_report import router as daily_report_router
from .daily_ad_costs import router as daily_ad_costs_router
from .sales_monthly_report import router as smr_router
from .store_report_groups import router as srg_router
from .daily_import import router as di_router
from .return_stats import router as rs_router
from .history_archive import router as history_archive_router

# 聚合路由
router = APIRouter()
router.include_router(compass_router, tags=["财务-数据罗盘"])
router.include_router(books_router, tags=["财务-账套与科目"])
router.include_router(vouchers_router, tags=["财务-凭证管理"])
router.include_router(reports_router, tags=["财务-报表与账簿"])
router.include_router(business_router, tags=["财务-业务台账"])
router.include_router(tax_router, tags=["财务-税务管理"])
router.include_router(ar_ap_router, tags=["财务-应收应付"])
router.include_router(auto_entry_router, tags=["财务-自动凭证"])
router.include_router(reports_extra_router, tags=["财务-扩展报表"])
router.include_router(daily_report_router,   tags=["财务-日报"])
router.include_router(daily_ad_costs_router, tags=["财务-每日广告费"])
router.include_router(smr_router,            tags=["财务-销售月报"])
router.include_router(srg_router,            tags=["财务-店铺组"])
router.include_router(di_router,             tags=["财务-日报统一导入"])
router.include_router(rs_router,             tags=["财务-退货统计"])
router.include_router(history_archive_router, tags=["财务-历史数据存档"])
