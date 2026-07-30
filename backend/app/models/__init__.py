from app.models.sys import (
    SysUser, SysDepartment, SysRole, SysMenu, SysPermission,
    SysUserRole, SysRolePermission, SysFieldPermission,
    SysDingtalkBind, SysDict, SysIntegrationConfig, SysParam
)
from app.models.ods import (
    OdsBaisonStore, OdsBaisonProduct, OdsBaisonSku,
    OdsBaisonSalesOrder, OdsBaisonSalesDetail,
    OdsBaisonReturnOrder, OdsBaisonReturnDetail,
    OdsBaisonInventory, OdsBaisonMember, OdsBaisonEmployee
)
from app.models.dim import DimStore, DimProduct, DimSku, DimMember, DimEmployee, DimDate, DimBaisonShop, DimWarehouse
from app.models.dwd import (
    DwdSalesDetail, DwdReturnDetail, DwdInventorySnapshot,
    DwdFinanceExpense, DwdFinanceCash
)
from app.models.dws import (
    DwsStoreDailySales, DwsCompanyDaily,
    DwsInventoryDaily, DwsProductDaily, DwsFinanceDaily
)
from app.models.dm import (
    DmBossDailyReport, DmStoreDiagnosis, DmInventoryWarning,
    DmExceptionAudit, DmMemberVisitList, DmReplenishmentAdvice,
    DmFinanceProfitDaily
)
from app.models.app import (
    AppActionTask, AppTaskFeedback, AppTaskReview,
    AppManualTarget, AppWarningConfig, AppPushTemplate, AppAiPromptTemplate
)
from app.models.log import (
    LogDataSync, LogDataQuality, LogAiCall, LogDingtalkPush,
    LogUserLogin, LogUserOperation, LogExport, LogError
)
from app.models.ai import (
    AiAssistantConversation,
    AiAssistantMessage,
    AiBusinessAdviceSnapshot,
    AiDiagnosisResult,
    AiRuleMatch,
)
from app.models.dingtalk_event import DingtalkEvent
from app.models.dingtalk_attendance import DingtalkAttendanceRecord
from app.models.dingtalk_hr_finance import (
    DingtalkEmployee, DingtalkDepartment, DingtalkApprovalInstance,
    FinanceExpenseRecord, HrAttendanceDaily,
)
from app.models.baison_ods import (OdsBaisonProductApi, OdsBaisonSkuApi, OdsBaisonWarehouseApi, OdsBaisonInventoryApi, DwdInventoryBalance)
from app.models.life_data import (
    InvestmentDecisionRun,
    InvestmentEnvironmentSummaryDaily,
    InvestmentExecutionRecord,
    InvestmentMetricSnapshot,
    InvestmentOutcomeSnapshot,
    InvestmentRecommendation,
    LifeDataAlertEvent,
    LifeDataCapture,
    LifeDataCollectorState,
    LifeDataVideoSnapshot,
)
from app.models.kingdee_finance import (
    DimFinanceAccount,
    DimFinanceStatementMapping,
    DimLegalEntity,
    DimSourceOrgMapping,
    DmFinanceStatementMonthly,
    DwdGlBalanceMonthly,
    DwdGlVoucher,
    DwdGlVoucherEntry,
    KingdeeAccount,
    KingdeeAuxItem,
    KingdeeBalance,
    KingdeeCurrency,
    KingdeeDepartment,
    KingdeeEmployee,
    KingdeeImportBatch,
    KingdeeSupplier,
    KingdeeVoucher,
    KingdeeVoucherEntry,
)
from app.models.finance_core import (
    FinAccount,
    FinAuxCategory,
    FinAuxItem,
    FinBook,
    FinLedgerBalance,
    FinOperationLog,
    FinPeriod,
    FinSourceLink,
    FinStatementLine,
    FinStatementMapping,
    FinVoucher,
    FinVoucherEntry,
    FinVoucherVersion,
)
from app.models.finance_operations import (
    FinAutoEntryRule,
    FinAutoEntryRun,
    FinBankTransaction,
    FinCashAccount,
    FinDepreciation,
    FinFixedAsset,
    FinInvoice,
    FinPayable,
    FinPayroll,
    FinReceivable,
    FinReconciliation,
    FinSettlement,
    FinTaxRecord,
)
from app.models.finance_v2 import (
    FinanceV2AccountingBook,
    FinanceV2AccountVersion,
    FinanceV2CommandIdempotency,
    FinanceV2DimensionSet,
    FinanceV2DimensionSetItem,
    FinanceV2FiscalPeriod,
    FinanceV2LedgerBalance,
    FinanceV2OperationEvent,
    FinanceV2Voucher,
    FinanceV2VoucherLine,
)
from app.models.finance_v2_history import (
    FinanceV2HistoryBatch,
    FinanceV2HistorySourceLink,
    FinanceV2HistoryStagingVoucher,
    FinanceV2HistoryVoucher,
    FinanceV2HistoryVoucherLine,
)
from app.models.finance_v2_opening import (
    FinanceV2CoverageGap,
    FinanceV2OpeningBalanceApproval,
    FinanceV2OpeningBalanceBatch,
    FinanceV2OpeningBalanceLine,
    FinanceV2OpeningBalanceReconciliationItem,
)
from app.models.finance_v2_period_close import FinanceV2PeriodCloseApproval, FinanceV2PeriodCloseBatch
from app.models.finance_v2_reports import FinanceV2ReportMapping, FinanceV2ReportSnapshot, FinanceV2ReportTemplate
from app.models.finance_v2_sources import (
    FinanceV2MappingException,
    FinanceV2PostingRule,
    FinanceV2PostingRuleVersion,
    FinanceV2PreviewRun,
    FinanceV2SourceDocument,
    FinanceV2SourceDocumentVersion,
    FinanceV2SourceInbox,
)
from app.models.finance_v2_operations import (
    FinanceV2FeatureGate,
    FinanceV2PostingAttempt,
    FinanceV2VoucherNumberCounter,
    FinanceV2VoucherNumberReservation,
)
from app.models.douyin_color_analytics import (
    CalculationJob,
    CollectionBatch,
    CollectionBatchPart,
    CollectionItem,
    CollectorEvent,
    CollectorExpectedSchedule,
    CollectorInstance,
    ColorPerformanceSnapshot,
    DouyinCreatorAccount,
    DouyinUploadToken,
    GarmentColor,
    GarmentSku,
    GarmentStyle,
    MetricSemanticValidation,
    Video,
    VideoAnalysisSnapshot,
    VideoCatalogSnapshot,
    VideoClip,
    VideoColorMetric,
)
