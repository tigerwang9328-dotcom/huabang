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
