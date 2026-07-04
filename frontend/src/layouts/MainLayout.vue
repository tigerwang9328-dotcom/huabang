<template>
  <div class="hb-layout">
    <!-- ====== 侧边栏 ====== -->
    <aside class="hb-sidebar">
      <!-- Logo 区域 -->
      <div class="sidebar-brand">
        <div class="sidebar-logo-icon">HB</div>
        <div class="sidebar-brand-text">
          <span class="sidebar-brand-name">华邦AI中台</span>
          <span class="sidebar-brand-sub">经营智能操作系统</span>
        </div>
      </div>

      <!-- 菜单（路径全部位于 /app 之下） -->
      <nav class="sidebar-nav">
        <div class="nav-group" v-for="group in visibleMenuGroups" :key="group.label">
          <button
            type="button"
            class="nav-item nav-parent nav-group-parent"
            :class="{ active: isGroupActive(group), expanded: expandedMenus.has(groupKey(group)) }"
            @click="toggleMenu(groupKey(group))"
          >
            <el-icon v-if="group.icon"><component :is="group.icon" /></el-icon>
            <span>{{ group.label }}</span>
            <el-icon class="nav-arrow"><ArrowRight /></el-icon>
          </button>
          <transition name="submenu">
            <div v-show="expandedMenus.has(groupKey(group))" class="submenu-list">
              <template v-for="item in group.items" :key="menuKey(item)">
                <div v-if="item.children?.length" class="nav-submenu">
                  <button
                    type="button"
                    class="nav-item nav-sub nav-parent-2"
                    :class="{ active: isAnyChildActive(item.children), expanded: expandedMenus.has(menuKey(item)) }"
                    @click.stop="toggleMenu(menuKey(item))"
                  >
                    <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
                    <span>{{ item.label }}</span>
                    <el-icon class="nav-arrow"><ArrowRight /></el-icon>
                  </button>
                  <transition name="submenu">
                    <div v-show="expandedMenus.has(menuKey(item))" class="submenu-list submenu-list-2">
                      <router-link
                        v-for="leaf in item.children"
                        :key="leaf.path"
                        :to="leaf.path || '/app/dashboard'"
                        class="nav-item nav-sub nav-sub-2"
                        :class="{ active: isActive(leaf.path || '') }"
                      >
                        <span>{{ leaf.label }}</span>
                      </router-link>
                    </div>
                  </transition>
                </div>
                <router-link
                  v-else
                  :to="item.path || '/app/dashboard'"
                  class="nav-item nav-sub"
                  :class="{ active: isActive(item.path || '') }"
                >
                  <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
                  <span>{{ item.label }}</span>
                </router-link>
              </template>
            </div>
          </transition>
        </div>
      </nav>

      <div class="sidebar-footer">v1.0.0 · 华邦服装</div>
    </aside>

    <!-- ====== 主体区 ====== -->
    <div class="hb-main-wrap">
      <header class="hb-header">
        <div class="header-left">
          <span class="header-page-title">{{ currentTitle }}</span>
        </div>
        <div class="header-right">
          <div class="header-user">
            <div class="user-avatar">{{ userInitial }}</div>
            <span class="user-name">{{ authStore.userInfo?.real_name || authStore.userInfo?.username }}</span>
          </div>
          <button class="logout-btn" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出
          </button>
        </div>
      </header>

      <main class="hb-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ElMessageBox } from "element-plus";
import {
  ArrowRight,
  Avatar,
  Bell,
  Box,
  ChatDotRound,
  DataLine,
  GoodsFilled,
  House,
  Key,
  List,
  Money,
  Refresh,
  Shop,
  TrendCharts,
  User,
  UserFilled,
  Warning,
} from "@element-plus/icons-vue";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const currentTitle = computed(() => (route.meta.title as string) || "华邦AI中台");
const EXPANDED_MENUS_KEY = "hb_sidebar_expanded_menus";
const loadExpandedMenus = () => {
  try {
    const raw = window.localStorage.getItem(EXPANDED_MENUS_KEY);
    const values = raw ? JSON.parse(raw) : [];
    return new Set<string>(Array.isArray(values) ? values : []);
  } catch (_) {
    return new Set<string>();
  }
};
const saveExpandedMenus = (menus: Set<string>) => {
  window.localStorage.setItem(EXPANDED_MENUS_KEY, JSON.stringify([...menus]));
};
const expandedMenus = ref(loadExpandedMenus());

type MenuRole = "admin" | "finance";
interface MenuItem {
  path?: string;
  label: string;
  icon?: unknown;
  key?: string;
  role?: MenuRole;
  children?: MenuItem[];
}
interface MenuGroup {
  label: string;
  icon?: unknown;
  items: MenuItem[];
}

const financeRoles = ["boss", "shareholder", "ceo", "finance_manager", "super_admin"];

const canShow = (item: MenuItem) => {
  if (item.role === "admin") return authStore.isAdmin || authStore.hasRole("super_admin");
  if (item.role === "finance") return authStore.hasAnyRole(...financeRoles);
  return true;
};

const menuGroups = computed<MenuGroup[]>(() => [
  {
    label: "经营",
    icon: DataLine,
    items: [
      { path: "/app/dashboard", icon: DataLine, label: "经营概览" },
      { path: "/app/boss", icon: House, label: "经营日报" },
      {
        icon: Shop,
        label: "门店经营",
        key: "store",
        children: [
          { path: "/app/store", label: "门店分析" },
        ],
      },
      {
        icon: GoodsFilled,
        label: "商品中心",
        key: "product",
        children: [
          { path: "/app/product", label: "商品分析" },
          { path: "/app/product/products", label: "商品主档" },
          { path: "/app/product/skus", label: "SKU档案" },
        ],
      },
      { path: "/app/finance", icon: TrendCharts, label: "利润分析", role: "finance" },
    ],
  },
  {
    label: "风控",
    icon: Warning,
    items: [
      {
        icon: Box,
        label: "库存管理",
        key: "inventory",
        children: [
          { path: "/app/inventory", label: "库存预警" },
          { path: "/app/inventory/balance", label: "库存余额" },
          { path: "/app/inventory/warehouses", label: "仓库档案" },
        ],
      },
      { path: "/app/warning", icon: Warning, label: "异常稽核" },
    ],
  },
  {
    label: "协调",
    icon: List,
    items: [
      { path: "/app/member", icon: User, label: "会员运营" },
      { path: "/app/task", icon: List, label: "任务管理" },
      { path: "/app/ai", icon: ChatDotRound, label: "AI助手" },
      { path: "/app/dingtalk", icon: Bell, label: "钉钉通知" },
      {
        icon: Avatar,
        label: "其他",
        key: "other",
        role: "admin",
        children: [
          { path: "/app/system/users", icon: Avatar, label: "用户管理" },
          { path: "/app/system/roles", icon: Key, label: "角色权限" },
          { path: "/app/system/sync", icon: Refresh, label: "数据同步" },
          { path: "/app/system/baison-api", icon: Refresh, label: "百胜API管理" },
        ],
      },
    ],
  },
  {
    label: "财务",
    icon: Money,
    items: [
      {
        icon: Money,
        label: "财务中心",
        key: "fin",
        role: "finance",
        children: [
          { path: "/app/fin/overview", label: "财务首页" },
          { path: "/app/fin/reimbursements", label: "报销管理" },
          { path: "/app/fin/payments", label: "付款申请" },
          { path: "/app/fin/expense-analysis", label: "费用分析" },
        ],
      },
    ],
  },
  {
    label: "人事",
    icon: UserFilled,
    items: [
      {
        icon: UserFilled,
        label: "人事管理",
        key: "hr",
        children: [
          { path: "/app/hr/overview", label: "人事首页" },
          { path: "/app/hr/employees", label: "员工档案" },
          { path: "/app/hr/attendance", label: "考勤管理" },
          { path: "/app/hr/leaves", label: "请假外出" },
        ],
      },
    ],
  },
]);

const visibleMenuGroups = computed(() => {
  const filterItems = (items: MenuItem[]): MenuItem[] =>
    items
      .filter(canShow)
      .map((item) => ({
        ...item,
        children: item.children ? filterItems(item.children) : undefined,
      }))
      .filter((item) => !item.children || item.children.length > 0);

  return menuGroups.value
    .map((group) => ({ ...group, items: filterItems(group.items) }))
    .filter((group) => group.items.length > 0);
});

const menuKey = (item: MenuItem) => item.key || item.path || item.label;
const groupKey = (group: MenuGroup) => `group:${group.label}`;

const toggleMenu = (key: string) => {
  const next = new Set(expandedMenus.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedMenus.value = next;
  saveExpandedMenus(next);
};

const isActive = (path: string) => {
  if (!path) return false;
  if (path === "/app/task") return route.path === path || route.path.startsWith(`${path}/`);
  return route.path === path;
};

const isAnyChildActive = (children: MenuItem[]): boolean =>
  children.some((item) => (item.path ? isActive(item.path) : false) || (item.children ? isAnyChildActive(item.children) : false));

const isGroupActive = (group: MenuGroup): boolean =>
  group.items.some((item) => (item.path ? isActive(item.path) : false) || (item.children ? isAnyChildActive(item.children) : false));

const userInitial = computed(() => {
  const name = authStore.userInfo?.real_name || authStore.userInfo?.username || "用";
  return name.slice(-1);
});

const handleLogout = async () => {
  await ElMessageBox.confirm("确认退出登录？", "退出确认", {
    type: "warning",
    confirmButtonText: "确认退出",
    cancelButtonText: "取消",
  });
  await authStore.logout();
  router.push("/login");
};
</script>

<style scoped>
.hb-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

/* ====== 侧边栏 ====== */
.hb-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: #071A2F;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 18px 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  flex-shrink: 0;
}
.sidebar-logo-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #C8A45D, #D6B66A);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 800;
  color: #fff;
  flex-shrink: 0;
}
.sidebar-brand-text { display: flex; flex-direction: column; }
.sidebar-brand-name {
  font-size: 14px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.2;
}
.sidebar-brand-sub {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  margin-top: 3px;
  letter-spacing: 0.04em;
}

.sidebar-nav {
  flex: 1;
  padding: 14px 10px;
  overflow-y: auto;
}
.nav-group + .nav-group { margin-top: 16px; }
.nav-group-label {
  font-size: 10px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.25);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 0 10px;
  margin-bottom: 4px;
}
.nav-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 13.5px;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
  margin-bottom: 2px;
  cursor: pointer;
  border: 0;
  background: transparent;
  font-family: inherit;
  text-align: left;
}
.nav-item:hover {
  background: rgba(255, 255, 255, 0.07);
  color: rgba(255, 255, 255, 0.9);
}
.nav-item.active {
  background: rgba(30, 94, 255, 0.18);
  color: #FFFFFF;
  font-weight: 600;
}
.nav-item.active .el-icon { color: #4D8EFF; }
.nav-item .el-icon { font-size: 15px; flex-shrink: 0; }
.nav-item span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nav-parent .nav-arrow {
  margin-left: auto;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.32);
  transition: transform 0.16s ease, color 0.16s ease;
}
.nav-parent.expanded .nav-arrow,
.nav-parent-2.expanded .nav-arrow {
  transform: rotate(90deg);
  color: rgba(255, 255, 255, 0.75);
}
.submenu-list {
  padding: 2px 0 4px;
}
.submenu-list-2 {
  padding-left: 8px;
}
.nav-sub {
  padding-left: 38px;
  font-size: 13px;
}
.nav-parent-2 {
  padding-left: 38px;
}
.nav-sub-2 {
  padding-left: 50px;
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.5);
}
.submenu-enter-active,
.submenu-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}
.submenu-enter-from,
.submenu-leave-to {
  opacity: 0;
  transform: translateY(-2px);
}

.sidebar-footer {
  padding: 12px 18px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.2);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

/* ====== 主体区 ====== */
.hb-main-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.hb-header {
  height: 56px;
  background: #FFFFFF;
  border-bottom: 1px solid #E5E7EB;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
  z-index: 10;
}
.header-page-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-avatar {
  width: 30px;
  height: 30px;
  background: linear-gradient(135deg, #1E5EFF, #1648CC);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}
.user-name {
  font-size: 13px;
  color: #374151;
  font-weight: 500;
}
.logout-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: #9CA3AF;
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 6px;
  transition: color 0.15s, background 0.15s;
}
.logout-btn:hover { color: #DC2626; background: #FEF2F2; }

.hb-content {
  flex: 1;
  overflow-y: auto;
  background: #F5F7FA;
  padding: 24px;
}
</style>
