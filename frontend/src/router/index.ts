import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const routes = [
  {
    path: "/login",
    name: "Login",
    component: () => import("@/views/Login.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    component: () => import("@/layouts/BasicLayout.vue"),
    meta: { requireAuth: true },
    children: [
      { path: "", redirect: "/dashboard" },
      { path: "dashboard", name: "Dashboard", component: () => import("@/views/dashboard/Index.vue"), meta: { title: "经营驾驶舱" } },
      { path: "boss", name: "Boss", component: () => import("@/views/boss/Index.vue"), meta: { title: "老板经营中心" } },
      { path: "store", name: "Store", component: () => import("@/views/store/Index.vue"), meta: { title: "门店运营中心" } },
      { path: "product", name: "Product", component: () => import("@/views/product/Index.vue"), meta: { title: "商品经营中心" } },
      { path: "inventory", name: "Inventory", component: () => import("@/views/inventory/Index.vue"), meta: { title: "库存预警中心" } },
      { path: "member", name: "Member", component: () => import("@/views/member/Index.vue"), meta: { title: "会员运营中心" } },
      { path: "finance", name: "Finance", component: () => import("@/views/finance/Index.vue"), meta: { title: "财务利润中心" } },
      { path: "task", name: "Task", component: () => import("@/views/task/Index.vue"), meta: { title: "AI任务中心" } },
      { path: "task/:id", name: "TaskDetail", component: () => import("@/views/task/Detail.vue"), meta: { title: "任务详情" } },
      { path: "warning", name: "Warning", component: () => import("@/views/warning/Index.vue"), meta: { title: "异常稽核中心" } },
      { path: "ai", name: "AI", component: () => import("@/views/ai/Index.vue"), meta: { title: "AI助手" } },
      { path: "dingtalk", name: "DingTalk", component: () => import("@/views/dingtalk/Index.vue"), meta: { title: "钉钉协同" } },
      {
        path: "system",
        name: "System",
        redirect: "/system/users",
        meta: { title: "系统管理" },
        children: [
          { path: "users", component: () => import("@/views/system/Users.vue"), meta: { title: "用户管理" } },
          { path: "roles", component: () => import("@/views/system/Roles.vue"), meta: { title: "角色管理" } },
          { path: "sync", component: () => import("@/views/system/Sync.vue"), meta: { title: "数据同步" } },
        ],
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, _, next) => {
  const authStore = useAuthStore();
  if (to.meta.public) return next();
  if (!authStore.isLoggedIn) return next("/login");
  next();
});

export default router;
