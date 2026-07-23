import { createRouter, createWebHistory } from "vue-router";
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
      // 利润分析：已合并到「财务中心 > 数据罗盘」，保留重定向兼容书签
      { path: "finance", redirect: "/app/finance-center/data-cockpit" },
      { path: "task", name: "Task", component: () => import("@/views/task/Index.vue"), meta: { title: "任务管理" } },
      { path: "task/:id", name: "TaskDetail", component: () => import("@/views/task/Detail.vue"), meta: { title: "任务详情" } },
      { path: "warning", name: "Warning", component: () => import("@/views/warning/Index.vue"), meta: { title: "异常稽核" } },
      { path: "ai", name: "AI", component: () => import("@/views/ai/Index.vue"), meta: { title: "AI助手" } },
      { path: "dingtalk", name: "DingTalk", component: () => import("@/views/dingtalk/Index.vue"), meta: { title: "钉钉通知" } },
      { path: "baison/shops", name: "BaisonShops", component: () => import("@/views/baison/Shops.vue"), meta: { title: "百胜门店档案" } },
      // ====== 财务中心（牧马人风格嵌套路由） ======
      {
        path: "finance",
        component: () => import("@/views/finance/layout.vue"),
        meta: { title: "财务中心", permission: "finance" },
        redirect: "/app/finance/compass",
        children: [
          { path: "compass",              component: () => import("@/views/finance/compass/index.vue"),        meta: { title: "数据罗盘",   permission: "finance" } },
          { path: "history-archive",       component: () => import("@/views/finance/history-archive/index.vue"), meta: { title: "历史数据存档", permission: "finance:history-archive:view" } },
          { path: "voucher/list",         component: () => import("@/views/finance/voucher/list.vue"),         meta: { title: "查凭证",     permission: "finance" } },
          { path: "voucher/new",          component: () => import("@/views/finance/voucher/new.vue"),          meta: { title: "录凭证",     permission: "finance" } },
          { path: "voucher/summary",      component: () => import("@/views/finance/voucher/summary.vue"),      meta: { title: "凭证汇总",   permission: "finance" } },
          { path: "voucher/templates",   component: () => import("@/views/finance/voucher/templates.vue"),   meta: { title: "凭证模板",   permission: "finance" } },
          { path: "auto-entry",          component: () => import("@/views/finance/auto-entry/index.vue"),      meta: { title: "自动凭证",   permission: "finance" } },
          { path: "ar/recv-orders",      component: () => import("@/views/finance/ar/recv-orders.vue"),      meta: { title: "应收单据",   permission: "finance" } },
          { path: "ar/payable-orders",   component: () => import("@/views/finance/ar/payable-orders.vue"),   meta: { title: "应付单据",   permission: "finance" } },
          { path: "ar/aging",            component: () => import("@/views/finance/ar/aging.vue"),            meta: { title: "账龄分析",   permission: "finance" } },
          { path: "books/general",        component: () => import("@/views/finance/books/general.vue"),        meta: { title: "总账",       permission: "finance" } },
          { path: "books/balance",        component: () => import("@/views/finance/books/balance.vue"),        meta: { title: "科目余额表", permission: "finance" } },
          { path: "books/detail",          component: () => import("@/views/finance/books/detail.vue"),         meta: { title: "明细账",     permission: "finance" } },
          { path: "reports/balance-sheet", component: () => import("@/views/finance/reports/balance-sheet.vue"),meta: { title: "资产负债表", permission: "finance" } },
          { path: "reports/profit",       component: () => import("@/views/finance/reports/profit.vue"),       meta: { title: "利润表",     permission: "finance" } },
          { path: "reports/cashflow",     component: () => import("@/views/finance/reports/cashflow.vue"),     meta: { title: "现金流量表", permission: "finance" } },
          { path: "reports/receivable-detail", component: () => import("@/views/finance/reports/receivable-detail.vue"), meta: { title: "应收明细",   permission: "finance" } },
          { path: "reports/payable-detail",   component: () => import("@/views/finance/reports/payable-detail.vue"),   meta: { title: "应付明细",   permission: "finance" } },
          { path: "reports/expense-detail",   component: () => import("@/views/finance/reports/expense-detail.vue"),   meta: { title: "费用明细表", permission: "finance" } },
          { path: "reports/tax-detail",       component: () => import("@/views/finance/reports/tax-detail.vue"),       meta: { title: "税金明细表", permission: "finance" } },
          { path: "closing",              component: () => import("@/views/finance/closing/index.vue"),        meta: { title: "结账",       permission: "finance" } },
          { path: "assets",               component: () => import("@/views/finance/assets/index.vue"),         meta: { title: "固定资产",   permission: "finance" } },
          { path: "invoices",             component: () => import("@/views/finance/invoices/index.vue"),       meta: { title: "发票管理",   permission: "finance" } },
          { path: "payments",             component: () => import("@/views/finance/payments/index.vue"),       meta: { title: "出纳",       permission: "finance" } },
          { path: "cashier/accounts",       component: () => import("@/views/finance/cashier/accounts.vue"),       meta: { title: "账户与流水",    permission: "finance" } },
          { path: "cashier/reconciliation", component: () => import("@/views/finance/cashier/reconciliation.vue"), meta: { title: "银行余额调节表", permission: "finance" } },
          { path: "payroll",              component: () => import("@/views/finance/payroll/index.vue"),        meta: { title: "工资管理",   permission: "finance" } },
          { path: "tax",                  component: () => import("@/views/finance/tax/index.vue"),            meta: { title: "税务管理",   permission: "finance" } },
          { path: "settings/subjects",    component: () => import("@/views/finance/settings/subjects.vue"),    meta: { title: "科目管理",   permission: "finance" } },
          { path: "settings/books",       component: () => import("@/views/finance/settings/books.vue"),       meta: { title: "账套管理",   permission: "finance" } },
          { path: "settings/aux",         component: () => import("@/views/finance/settings/aux.vue"),         meta: { title: "辅助核算",   permission: "finance" } },
          { path: "settings/logs",        component: () => import("@/views/finance/settings/logs.vue"),        meta: { title: "操作日志",   permission: "finance" } },
        ],
      },
      // 业务单据（保留钉钉流程入口）
      { path: "fin", redirect: "/app/finance-center/data-cockpit" },
      { path: "fin/overview", redirect: "/app/finance-center/data-cockpit" },
      { path: "fin/formal-ledger", redirect: "/app/finance-center/ledger" },
      // 历史财务 5 Tab 已合并到「财务中心 > 历史数据存档 / 财务报表 / 账簿 / 凭证」，保留重定向兼容书签
      { path: "fin/history", redirect: "/app/finance-center/archive" },
      { path: "fin/history/account-sets", redirect: "/app/finance-center/archive" },
      { path: "fin/history/statements", redirect: "/app/finance-center/reports" },
      { path: "fin/history/account-balances", redirect: "/app/finance-center/ledger" },
      { path: "fin/history/vouchers", redirect: "/app/finance-center/vouchers" },
      { path: "fin/history/data-quality", redirect: "/app/finance-center/archive" },
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
  // 财务中心模块统一权限：查看
  ["/app/finance-center", "finance:profit:view"],
  ["/app/fin/reimbursements", "finance:reimbursement:view"],
  ["/app/fin/payments", "finance:payment:view"],
  ["/app/fin/expense-analysis", "finance:expense:view"],
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
    ["/app/finance-center/data-cockpit", "finance:profit:view"],
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
