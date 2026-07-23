"""
财务中心 - 模型层
========================================
目录结构：
  compass.py     数据罗盘（原有5张表，经营分析）
  accounting.py  会计核算底座（账套/科目/凭证/分录/总账/期间）
  business.py    业务台账（应收/应付/客户/供应商/出纳/工资/资产/发票/债务）
  settings.py    设置与日志（辅助核算/审计日志/报表快照/AI报告/账套权限）
  tax.py         税务（税种配置/税务台账）
"""
# 数据罗盘（原有，经营分析型）
from app.models.finance.compass import (
    FinanceReceipt, FinanceFee,
    FinDailySummary, FinRiskAlert, FinCostConfig,
)

# 会计核算底座
from app.models.finance.accounting import (
    FinBook, FinAccount, FinVoucher, FinVoucherLine, FinLedgerBalance, FinPeriod,
    FinVoucherTemplate,
)

# 业务台账
from app.models.finance.business import (
    FinCustomer, FinSupplier, FinReceivable, FinPayable,
    FinCashAccount, FinCashFlow, FinPayrollRecord,
    FinDebtRecord, FinFixedAsset, FinInvoice,
    FinRecvOrder, FinRecvOrderLine, FinPayableOrder, FinPayableOrderLine,
)

# 设置与日志
from app.models.finance.settings import (
    FinAuxCategory, FinAuxItem, FinAuditLog,
    FinStatementSnapshot, FinAiReport, FinBookPermission,
)

# 税务
from app.models.finance.tax import FinTaxType, FinTaxRecord

# 销售月报
from app.models.finance.sales_monthly_report import (
    FinSalesMonthlyStoreOwnership, FinSalesMonthlyReportBatch,
    FinSalesMonthlyImportFile, FinSalesMonthlyShopReport,
    FinSalesMonthlyOrderDetail, FinSalesMonthlyImportSheet,
)

# 历史数据存档（旧表映射 + 企业数据资产中心独立表）
from app.models.finance.history_archive import (
    FinHistoryArchiveFile,
    DataArchiveCategory,
    DataArchiveFile,
    DataArchiveLog,
)

__all__ = [
    # 数据罗盘
    'FinanceReceipt', 'FinanceFee', 'FinDailySummary', 'FinRiskAlert', 'FinCostConfig',
    # 会计核算
    'FinBook', 'FinAccount', 'FinVoucher', 'FinVoucherLine', 'FinLedgerBalance', 'FinPeriod',
    'FinVoucherTemplate',
    # 业务台账
    'FinCustomer', 'FinSupplier', 'FinReceivable', 'FinPayable',
    'FinCashAccount', 'FinCashFlow', 'FinPayrollRecord',
    'FinDebtRecord', 'FinFixedAsset', 'FinInvoice',
    'FinRecvOrder', 'FinRecvOrderLine', 'FinPayableOrder', 'FinPayableOrderLine',
    # 设置
    'FinAuxCategory', 'FinAuxItem', 'FinAuditLog',
    'FinStatementSnapshot', 'FinAiReport', 'FinBookPermission',
    # 税务
    'FinTaxType', 'FinTaxRecord',
    # 销售月报
    'FinSalesMonthlyStoreOwnership', 'FinSalesMonthlyReportBatch',
    'FinSalesMonthlyImportFile', 'FinSalesMonthlyShopReport',
    'FinSalesMonthlyOrderDetail', 'FinSalesMonthlyImportSheet',
    # 历史数据存档
    'FinHistoryArchiveFile', 'DataArchiveCategory', 'DataArchiveFile', 'DataArchiveLog',
]
