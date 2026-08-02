import { createRouter, createWebHistory } from "vue-router";
import { financeCenterModules } from "@/config/financeCenterModules";
import { useAuthStore } from "@/stores/auth";
import { cancelRouteRequests } from "@/api/request";

const routes = [
  // ====== 公开品牌官网（单页，无需登录） ======
  {
    path: "/",
    name: "PublicHome",
    component: () => import("@/views/public/Home.vue"),
    meta: { public: true, title: "华邦公司 · 莱勒 REARE" },
  },

  // ====== 登录（无需登录，沿用现有全屏登录页） ======
  {
    path: "/login",
    component: () => import("@/layouts/AuthLayout.vue"),
    meta: { public: true },
    children: [
      { path: "", name: "Login", component: () => import("@/views/Login.vue"), meta: { public: true } },
    ],
  },

  // ====== 内部经营数据中台（必须登录，全部位于 /app 之下） ======
  {
    path: "/app",
    component: () => import("@/layouts/MainLayout.vue"),
    meta: { requireAuth: true },
    children: [
      { path: "", redirect: "/app/dashboard" },
      { path: "dashboard", name: "Dashboard", component: () => import("@/views/dashboard/Index.vue"), meta: { title: "经营总览" } },
      { path: "marketing/investment", name: "InvestmentOptimization", component: () => import("@/views/marketing/InvestmentOptimization.vue"), meta: { title: "投流优化" } },
      { path: "online-sales/douyin-analysis", name: "OnlineSalesDouyinAnalysis", component: () => import("@/views/douyinColorAnalytics/Admin.vue"), meta: { title: "抖音视频分析" } },
      { path: "online-sales/douyin-analysis/videos", name: "DouyinColorVideoList", component: () => import("@/views/douyinColorAnalytics/VideoList.vue"), meta: { title: "抖音视频列表" } },
      { path: "online-sales/douyin-analysis/videos/:videoId/annotate", name: "DouyinColorAnnotation", component: () => import("@/views/douyinColorAnalytics/Annotate.vue"), meta: { title: "视频标注" } },
      { path: "online-sales/douyin-analysis/styles", name: "DouyinColorStyles", component: () => import("@/views/douyinColorAnalytics/Styles.vue"), meta: { title: "款式颜色" } },
      { path: "online-sales/douyin-analysis/report", name: "DouyinColorReport", component: () => import("@/views/douyinColorAnalytics/Report.vue"), meta: { title: "颜色分析报告" } },
      { path: "report", name: "BusinessReport", component: () => import("@/views/report/Index.vue"), meta: { title: "经营日报" } },
      { path: "boss", name: "Boss", component: () => import("@/views/boss/Index.vue"), meta: { title: "经营日报" } },
      { path: "ai-diagnosis", name: "AiDiagnosis", redirect: "/app/ai-diagnosis/overview", meta: { title: "AI经营诊断" } },
      { path: "ai-diagnosis/overview", name: "AiDiagnosisOverview", component: () => import("@/views/diagnosis/Index.vue"), meta: { title: "AI经营诊断" } },
      { path: "ai-diagnosis/:module", name: "AiDiagnosisModule", component: () => import("@/views/diagnosis/Index.vue"), meta: { title: "AI经营诊断" } },
      { path: "store", name: "Store", component: () => import("@/views/store/Index.vue"), meta: { title: "门店分析" } },
      { path: "store/overview", redirect: "/app/store" },
      { path: "product", name: "Product", component: () => import("@/views/product/Index.vue"), meta: { title: "商品分析" } },
      { path: "product/products", name: "ProductMaster", component: () => import("@/views/product/ProductMaster.vue"), meta: { title: "商品主档" } },
      { path: "product/skus", name: "SkuArchive", component: () => import("@/views/product/SkuArchive.vue"), meta: { title: "SKU档案" } },
      { path: "product/size-wall", name: "SizeWall", component: () => import("@/views/product/SizeWall.vue"), meta: { title: "断码尺码墙" } },
      { path: "inventory", name: "Inventory", component: () => import("@/views/inventory/Index.vue"), meta: { title: "库存预警" } },
      { path: "inventory/warehouses", name: "Warehouses", component: () => import("@/views/inventory/Warehouses.vue"), meta: { title: "仓库档案" } },
      { path: "inventory/balance", name: "InventoryBalance", component: () => import("@/views/inventory/InventoryBalance.vue"), meta: { title: "库存余额" } },
      { path: "member", name: "Member", component: () => import("@/views/member/Index.vue"), meta: { title: "会员运营" } },
      { path: "finance", name: "Finance", component: () => import("@/views/finance/Index.vue"), meta: { title: "利润分析" } },
      { path: "task", name: "Task", component: () => import("@/views/task/Index.vue"), meta: { title: "任务管理" } },
      { path: "task/:id", name: "TaskDetail", component: () => import("@/views/task/Detail.vue"), meta: { title: "任务详情" } },
      { path: "warning", name: "Warning", component: () => import("@/views/warning/Index.vue"), meta: { title: "异常稽核" } },
      { path: "ai", name: "AI", component: () => import("@/views/ai/Index.vue"), meta: { title: "AI助手" } },
      { path: "dingtalk", name: "DingTalk", component: () => import("@/views/dingtalk/Index.vue"), meta: { title: "钉钉通知" } },
      { path: "baison/shops", name: "BaisonShops", component: () => import("@/views/baison/Shops.vue"), meta: { title: "百胜门店档案" } },
      { path: "fin", redirect: "/app/fin/overview" },
      { path: "fin/overview", name: "FinanceOverview", component: () => import("@/views/finance/FinanceOverview.vue"), meta: { title: "财务首页" } },
      { path: "fin/reimbursements", name: "Reimbursements", component: () => import("@/views/finance/Reimbursements.vue"), meta: { title: "报销管理" } },
      { path: "fin/payments", name: "Payments", component: () => import("@/views/finance/Payments.vue"), meta: { title: "付款申请" } },
      { path: "fin/expense-analysis", name: "ExpenseAnalysis", component: () => import("@/views/finance/ExpenseAnalysis.vue"), meta: { title: "费用分析" } },
      { path: "fin/formal-ledger", name: "FormalLedger", component: () => import("@/views/finance/FormalLedger.vue"), meta: { title: "正式账簿" } },
      {
        path: "finance-center/mumaren",
        component: () => import("@/views/mumaren-finance-center/MumarenFinanceCenterShell.vue"),
        meta: { title: "财务中心" },
        children: [
          { path: "", redirect: "/app/finance-center/mumaren/history" },
          // 数据罗盘
          { path: "compass", name: "MumarenFinanceCompass", component: () => import("@/views/mumaren-finance-center/MumarenFinanceCompass.vue"), meta: { title: "数据罗盘" } },
          // 历史数据存档
          { path: "history", name: "MumarenFinanceHistory", component: () => import("@/views/mumaren-finance-center/MumarenFinanceHistory.vue"), meta: { title: "历史数据存档" } },
          // 凭证(5 子项)
          { path: "vouchers", redirect: "/app/finance-center/mumaren/vouchers/list" },
          { path: "vouchers/create", name: "MumarenFinanceVoucherCreate", component: () => import("@/views/mumaren-finance-center/MumarenFinanceVoucherCreate.vue"), meta: { title: "录凭证" } },
          { path: "vouchers/list", name: "MumarenFinanceVoucherList", component: () => import("@/views/mumaren-finance-center/MumarenFinanceVoucherList.vue"), meta: { title: "查凭证" } },
          { path: "vouchers/summary", name: "MumarenFinanceVoucherSummary", component: () => import("@/views/mumaren-finance-center/MumarenFinanceVoucherSummary.vue"), meta: { title: "凭证汇总" } },
          { path: "vouchers/template", name: "MumarenFinanceVoucherTemplate", component: () => import("@/views/mumaren-finance-center/MumarenFinanceVoucherTemplate.vue"), meta: { title: "凭证模板" } },
          { path: "vouchers/auto", name: "MumarenFinanceVoucherAuto", component: () => import("@/views/mumaren-finance-center/MumarenFinanceVoucherAuto.vue"), meta: { title: "自动凭证" } },
          // 账簿(3 子项)
          { path: "ledgers", redirect: "/app/finance-center/mumaren/ledgers/general" },
          { path: "ledgers/general", name: "MumarenFinanceGeneralLedger", component: () => import("@/views/mumaren-finance-center/MumarenFinanceLedgers.vue"), meta: { title: "总账" } },
          { path: "ledgers/trial-balance", name: "MumarenFinanceTrialBalance", component: () => import("@/views/mumaren-finance-center/MumarenFinanceReportTrialBalance.vue"), meta: { title: "科目余额表" } },
          { path: "ledgers/detail", name: "MumarenFinanceLedgerDetail", component: () => import("@/views/mumaren-finance-center/MumarenFinanceLedgerDetail.vue"), meta: { title: "明细账" } },
          // 报表(8 子项)
          { path: "reports", redirect: "/app/finance-center/mumaren/reports/profit-statement" },
          { path: "reports/balance-sheet", name: "MumarenFinanceBalanceSheet", component: () => import("@/views/mumaren-finance-center/MumarenFinanceReportBalanceSheet.vue"), meta: { title: "资产负债表" } },
          { path: "reports/profit-statement", name: "MumarenFinanceProfitStatement", component: () => import("@/views/mumaren-finance-center/MumarenFinanceReportProfit.vue"), meta: { title: "利润表" } },
          { path: "reports/cash-flow-statement", name: "MumarenFinanceCashFlowStatement", component: () => import("@/views/mumaren-finance-center/MumarenFinanceReportCashFlow.vue"), meta: { title: "现金流量表" } },
          { path: "reports/receivable-detail", name: "MumarenFinanceReceivableDetail", component: () => import("@/views/mumaren-finance-center/MumarenFinanceReportReceivable.vue"), meta: { title: "应收明细" } },
          { path: "reports/payable-detail", name: "MumarenFinancePayableDetail", component: () => import("@/views/mumaren-finance-center/MumarenFinanceReportPayable.vue"), meta: { title: "应付明细" } },
          { path: "reports/expense-detail", name: "MumarenFinanceExpenseDetail", component: () => import("@/views/mumaren-finance-center/MumarenFinanceReportExpense.vue"), meta: { title: "费用明细表" } },
          { path: "reports/tax-detail", name: "MumarenFinanceTaxDetail", component: () => import("@/views/mumaren-finance-center/MumarenFinanceTaxRecords.vue"), meta: { title: "税金明细表" } },
          { path: "reports/sales-monthly", name: "MumarenFinanceSalesMonthly", component: () => import("@/views/mumaren-finance-center/MumarenFinanceReportSalesMonthly.vue"), meta: { title: "销售月报表" } },
          // 应收应付
          { path: "ar-ap", name: "MumarenFinanceArAp", redirect: "/app/finance-center/mumaren/ar-ap/receivable" },
          { path: "ar-ap/receivable", name: "MumarenFinanceReceivableLedger", component: () => import("@/views/mumaren-finance-center/MumarenFinanceArAp.vue"), props: { fixedOrderType: "receivable" }, meta: { title: "应收单台账" } },
          { path: "ar-ap/payable", name: "MumarenFinancePayableLedger", component: () => import("@/views/mumaren-finance-center/MumarenFinanceArAp.vue"), props: { fixedOrderType: "payable" }, meta: { title: "应付单台账" } },
          { path: "ar-ap/aging", name: "MumarenFinanceArApAging", component: () => import("@/views/mumaren-finance-center/MumarenFinanceArApAging.vue"), meta: { title: "账龄分析" } },
          // 结账
          { path: "closing", name: "MumarenFinanceClosing", component: () => import("@/views/mumaren-finance-center/MumarenFinanceClosing.vue"), meta: { title: "结账" } },
          // 资产
          { path: "assets", name: "MumarenFinanceAssets", component: () => import("@/views/mumaren-finance-center/MumarenFinanceAssets.vue"), meta: { title: "资产" } },
          // 发票
            { path: "invoices", name: "MumarenFinanceInvoices", component: () => import("@/views/mumaren-finance-center/MumarenFinanceInvoices.vue"), meta: { title: "发票" } },
            { path: "payments", name: "MumarenFinancePayments", component: () => import("@/views/mumaren-finance-center/MumarenFinancePayments.vue"), meta: { title: "付款" } },
          // 出纳(2 子项)
          { path: "cashier", redirect: "/app/finance-center/mumaren/cashier/accounts" },
          { path: "cashier/accounts", name: "MumarenFinanceCashierAccounts", component: () => import("@/views/mumaren-finance-center/MumarenFinanceCashierAccounts.vue"), meta: { title: "账户与流水" } },
          { path: "cashier/reconciliation", name: "MumarenFinanceCashierReconciliation", component: () => import("@/views/mumaren-finance-center/MumarenFinanceCashierReconciliation.vue"), meta: { title: "银行余额调节表" } },
          // 工资
          { path: "payroll", name: "MumarenFinancePayroll", component: () => import("@/views/mumaren-finance-center/MumarenFinancePayroll.vue"), meta: { title: "工资" } },
          // 税务
          { path: "tax", name: "MumarenFinanceTax", component: () => import("@/views/mumaren-finance-center/MumarenFinanceTax.vue"), meta: { title: "税务" } },
          // 设置(6 子项)
          { path: "settings", redirect: "/app/finance-center/mumaren/settings/accounts" },
          { path: "settings/accounts", name: "MumarenFinanceSettingsAccounts", component: () => import("@/views/mumaren-finance-center/MumarenFinanceAccounts.vue"), meta: { title: "科目管理" } },
          { path: "settings/books", name: "MumarenFinanceSettingsBooks", component: () => import("@/views/mumaren-finance-center/MumarenFinanceBooks.vue"), meta: { title: "账套管理" } },
          { path: "settings/auxiliary", name: "MumarenFinanceSettingsAuxiliary", component: () => import("@/views/mumaren-finance-center/MumarenFinanceSettingsAuxiliary.vue"), meta: { title: "辅助核算" } },
          { path: "settings/audit-logs", name: "MumarenFinanceSettingsAuditLogs", component: () => import("@/views/mumaren-finance-center/MumarenFinanceSettingsAuditLogs.vue"), meta: { title: "操作日志" } },
        ],
      },
      { path: "finance-center", redirect: "/app/finance-center/core-workspace" },
      ...financeCenterModules.map((item) => ({
        path: `finance-center/${item.key}`,
        name: `FinanceCenter${item.key.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join("")}`,
        component: item.key === "core-workspace"
          ? () => import("@/views/finance-center/V2CoreWorkspace.vue")
          : () => import("@/views/finance/FinanceCenterModule.vue"),
        meta: { title: item.label, financeModuleKey: item.key },
      })),
      { path: "fin/history/account-sets", name: "FinanceAccountSets", component: () => import("@/views/finance/HistoricalFinance.vue"), meta: { title: "历史账套", financeTab: "account-sets" } },
      { path: "fin/history/statements", name: "FinanceStatements", component: () => import("@/views/finance/HistoricalFinance.vue"), meta: { title: "财务报表", financeTab: "statements" } },
      { path: "fin/history/account-balances", name: "FinanceAccountBalances", component: () => import("@/views/finance/HistoricalFinance.vue"), meta: { title: "科目余额", financeTab: "account-balances" } },
      { path: "fin/history/vouchers", name: "FinanceVouchers", component: () => import("@/views/finance/HistoricalFinance.vue"), meta: { title: "凭证查询", financeTab: "vouchers" } },
      { path: "fin/history/data-quality", name: "FinanceDataQuality", component: () => import("@/views/finance/HistoricalFinance.vue"), meta: { title: "数据质量", financeTab: "data-quality" } },
      { path: "hr", redirect: "/app/hr/overview" },
      { path: "hr/overview", name: "HrOverview", component: () => import("@/views/hr/HrOverview.vue"), meta: { title: "人事首页" } },
      { path: "hr/employees", name: "HrEmployees", component: () => import("@/views/hr/Employees.vue"), meta: { title: "员工档案" } },
      { path: "hr/attendance", name: "HrAttendance", component: () => import("@/views/hr/Attendance.vue"), meta: { title: "考勤管理" } },
      { path: "hr/leaves", name: "HrLeaves", component: () => import("@/views/hr/Leaves.vue"), meta: { title: "请假外出" } },
      {
        path: "system",
        name: "System",
        redirect: "/app/system/users",
        meta: { title: "系统管理" },
        children: [
          { path: "admin", component: () => import("@/views/system/AdminDashboard.vue"), meta: { title: "管理后台", permission: "system:dashboard:view" } },
          { path: "register-audit", component: () => import("@/views/system/RegisterAudit.vue"), meta: { title: "注册审核", permission: "system:register:review" } },
          { path: "module-permissions", component: () => import("@/views/system/ModulePermissions.vue"), meta: { title: "岗位权限矩阵", permission: "system:permission:view" } },
          { path: "data-permissions", component: () => import("@/views/system/DataPermissions.vue"), meta: { title: "数据权限", permission: "system:data-scope:update" } },
          { path: "field-permissions", component: () => import("@/views/system/FieldPermissions.vue"), meta: { title: "字段权限", permission: "system:field-permission:update" } },
          { path: "security", component: () => import("@/views/system/Security.vue"), meta: { title: "安全设置", permission: "system:security:update" } },
          { path: "users", component: () => import("@/views/system/Users.vue"), meta: { title: "用户管理", permission: "system:user:view" } },
          { path: "roles", component: () => import("@/views/system/Roles.vue"), meta: { title: "角色权限", permission: "system:role:view" } },
          { path: "sync", component: () => import("@/views/system/Sync.vue"), meta: { title: "数据同步", permission: "system:sync:view" } },
          { path: "baison-api", component: () => import("@/views/system/BaisonApi.vue"), meta: { title: "百胜API管理", permission: "system:baison-api:view" } },
          { path: "operation-logs", component: () => import("@/views/system/OperationLogs.vue"), meta: { title: "操作日志", permission: "system:operation-log:view" } },
        ],
      },
    ],
  },

  // ====== 旧内部路径兼容重定向 ======
  { path: "/dashboard", redirect: "/app/dashboard" },

  // 未匹配 -> 公开官网首页
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 };
  },
});


const routePermissionRules: Array<[string, string]> = [
  ["/app/dashboard", "dashboard:overview:view"],
  ["/app/report", "dashboard:overview:view"],
  ["/app/ai-diagnosis", "diagnosis:overall:view"],
  ["/app/store", "sales:store:view"],
  ["/app/member", "sales:store:view"],
  ["/app/warning", "sales:warning:view"],
  ["/app/product/products", "product:master:view"],
  ["/app/product/skus", "product:sku:view"],
  ["/app/product/size-wall", "product:overview:view"],
  ["/app/product", "product:overview:view"],
  ["/app/inventory/warehouses", "inventory:warehouse:view"],
  ["/app/inventory/balance", "inventory:balance:view"],
  ["/app/inventory", "inventory:overview:view"],
  ["/app/finance", "finance:profit:view"],
  ["/app/task", "task:view"],
  ["/app/fin/overview", "finance:overview:view"],
  ["/app/fin/reimbursements", "finance:reimbursement:view"],
  ["/app/fin/payments", "finance:payment:view"],
  ["/app/fin/expense-analysis", "finance:expense:view"],
  ["/app/fin/formal-ledger", "finance:voucher:write"],
  ["/app/fin/history", "finance:profit:view"],
  ["/app/finance-center", "finance:center:view"],
  ["/app/finance-center/mumaren", "mumaren_finance_center:access"],
  ["/app/hr/overview", "hr:overview:view"],
  ["/app/hr/employees", "hr:employee:view"],
  ["/app/hr/attendance", "hr:attendance:view"],
  ["/app/hr/leaves", "hr:leave:view"],
  ["/app/ai", "knowledge:ai:view"],
  ["/app/system/admin", "system:dashboard:view"],
  ["/app/system/register-audit", "system:register:review"],
  ["/app/system/module-permissions", "system:permission:view"],
  ["/app/system/data-permissions", "system:data-scope:update"],
  ["/app/system/field-permissions", "system:field-permission:update"],
  ["/app/system/security", "system:security:update"],
  ["/app/system/users", "system:user:view"],
  ["/app/system/roles", "system:role:view"],
  ["/app/system/sync", "system:sync:view"],
  ["/app/system/baison-api", "system:baison-api:view"],
  ["/app/system/operation-logs", "system:operation-log:view"],
  ["/app/dingtalk", "system:dingtalk:view"],
];

const getRoutePermission = (path: string) => {
  const matched = routePermissionRules
    .filter(([prefix]) => path === prefix || path.startsWith(`${prefix}/`))
    .sort((a, b) => b[0].length - a[0].length)[0];
  return matched?.[1] || "";
};


const getPermissionHomePath = (authStore: ReturnType<typeof useAuthStore>) => {
  const candidates: Array<[string, string]> = [
    ["/app/dashboard", "dashboard:overview:view"],
    ["/app/ai-diagnosis", "diagnosis:overall:view"],
    ["/app/store", "sales:store:view"],
    ["/app/product", "product:overview:view"],
    ["/app/inventory", "inventory:overview:view"],
    ["/app/fin/overview", "finance:overview:view"],
    ["/app/finance-center/core-workspace", "finance:center:view"],
    ["/app/finance-center/mumaren", "mumaren_finance_center:access"],
    ["/app/hr/overview", "hr:overview:view"],
    ["/app/ai", "knowledge:ai:view"],
    ["/app/system/admin", "system:dashboard:view"],
  ];
  return candidates.find(([, permission]) => authStore.hasPermission(permission))?.[0] || "/login";
};

router.beforeEach((to, _, next) => {
  const authStore = useAuthStore();
  const needAuth = to.matched.some((r) => r.meta.requireAuth);

  if (to.path === "/login" && authStore.isLoggedIn) {
    return next(getPermissionHomePath(authStore));
  }
  if (needAuth && !authStore.isLoggedIn) {
    return next("/login");
  }
  const requiredPermission = (to.meta.permission as string) || getRoutePermission(to.path);
  if (needAuth && requiredPermission && !authStore.hasPermission(requiredPermission)) {
    return next(getPermissionHomePath(authStore));
  }
  next();
});

router.afterEach((to, from, failure) => {
  if (!failure && to.path !== from.path) cancelRouteRequests();
});

export default router;
