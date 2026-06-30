import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

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
      { path: "dashboard", name: "Dashboard", component: () => import("@/views/dashboard/Index.vue"), meta: { title: "经营概览" } },
      { path: "boss", name: "Boss", component: () => import("@/views/boss/Index.vue"), meta: { title: "经营日报" } },
      { path: "store", name: "Store", component: () => import("@/views/store/Index.vue"), meta: { title: "门店分析" } },
      { path: "store/overview", name: "StoreOverview", component: () => import("@/views/store/StoreOverview.vue"), meta: { title: "门店总览" } },
      { path: "product", name: "Product", component: () => import("@/views/product/Index.vue"), meta: { title: "商品分析" } },
      { path: "product/products", name: "ProductMaster", component: () => import("@/views/product/ProductMaster.vue"), meta: { title: "商品主档" } },
      { path: "product/skus", name: "SkuArchive", component: () => import("@/views/product/SkuArchive.vue"), meta: { title: "SKU档案" } },
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
          { path: "users", component: () => import("@/views/system/Users.vue"), meta: { title: "用户管理" } },
          { path: "roles", component: () => import("@/views/system/Roles.vue"), meta: { title: "角色权限" } },
          { path: "sync", component: () => import("@/views/system/Sync.vue"), meta: { title: "数据同步" } },
          { path: "baison-api", component: () => import("@/views/system/BaisonApi.vue"), meta: { title: "百胜API管理" } },
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

router.beforeEach((to, _, next) => {
  const authStore = useAuthStore();
  const needAuth = to.matched.some((r) => r.meta.requireAuth);

  if (to.path === "/login" && authStore.isLoggedIn) {
    return next("/app/dashboard");
  }
  if (needAuth && !authStore.isLoggedIn) {
    return next("/login");
  }
  next();
});

export default router;
