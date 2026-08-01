<template>
  <div class="hb-layout">
    <button v-if="mobileSidebarOpen" class="sidebar-scrim" aria-label="关闭导航" @click="mobileSidebarOpen = false"></button>
    <!-- ====== 侧边栏 ====== -->
    <aside class="hb-sidebar" :class="{ 'mobile-open': mobileSidebarOpen }">
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
          <router-link
            v-if="group.path"
            :to="group.path"
            class="nav-item nav-parent nav-group-parent nav-group-link"
            :class="{ active: isActive(group.path) }"
          >
            <el-icon v-if="group.icon"><component :is="group.icon" /></el-icon>
            <span>{{ group.label }}</span>
          </router-link>
          <template v-else>
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
                        <template v-for="leaf in item.children" :key="menuKey(leaf)">
                          <!-- 第4级:leaf 有 children,可展开 -->
                          <div v-if="leaf.children?.length" class="nav-submenu nav-submenu-2">
                            <button
                              type="button"
                              class="nav-item nav-sub nav-parent-3"
                              :class="{ active: isAnyChildActive(leaf.children), expanded: expandedMenus.has(menuKey(leaf)) }"
                              @click.stop="toggleMenu(menuKey(leaf))"
                            >
                              <span>{{ leaf.label }}</span>
                              <em v-if="leaf.badge" class="nav-badge">{{ leaf.badge }}</em>
                              <el-icon class="nav-arrow"><ArrowRight /></el-icon>
                            </button>
                            <transition name="submenu">
                              <div v-show="expandedMenus.has(menuKey(leaf))" class="submenu-list submenu-list-3">
                                <template v-for="leaf2 in leaf.children" :key="menuKey(leaf2)">
                                  <button
                                    v-if="leaf2.disabled"
                                    type="button"
                                    class="nav-item nav-sub nav-sub-3 nav-disabled"
                                    disabled
                                  >
                                    <span>{{ leaf2.label }}</span>
                                    <em v-if="leaf2.badge" class="nav-badge">{{ leaf2.badge }}</em>
                                  </button>
                                  <router-link
                                    v-else
                                    :to="leaf2.path || '/app/dashboard'"
                                    class="nav-item nav-sub nav-sub-3"
                                    :class="{ active: isActive(leaf2.path || '') }"
                                  >
                                    <span>{{ leaf2.label }}</span>
                                    <em v-if="leaf2.badge" class="nav-badge">{{ leaf2.badge }}</em>
                                  </router-link>
                                </template>
                              </div>
                            </transition>
                          </div>
                          <!-- 第3级叶子 -->
                          <button
                            v-else-if="leaf.disabled"
                            type="button"
                            class="nav-item nav-sub nav-sub-2 nav-disabled"
                            disabled
                          >
                            <span>{{ leaf.label }}</span>
                            <em v-if="leaf.badge" class="nav-badge">{{ leaf.badge }}</em>
                          </button>
                          <router-link
                            v-else
                            :to="leaf.path || '/app/dashboard'"
                            class="nav-item nav-sub nav-sub-2"
                            :class="{ active: isActive(leaf.path || '') }"
                          >
                            <span>{{ leaf.label }}</span>
                            <em v-if="leaf.badge" class="nav-badge">{{ leaf.badge }}</em>
                          </router-link>
                        </template>
                      </div>
                    </transition>
                  </div>
                  <button
                    v-else-if="item.disabled"
                    type="button"
                    class="nav-item nav-sub nav-disabled"
                    disabled
                  >
                    <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
                    <span>{{ item.label }}</span>
                    <em v-if="item.badge" class="nav-badge">{{ item.badge }}</em>
                  </button>
                  <router-link
                    v-else
                    :to="item.path || '/app/dashboard'"
                    class="nav-item nav-sub"
                    :class="{ active: isActive(item.path || '') }"
                  >
                    <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
                    <span>{{ item.label }}</span>
                    <em v-if="item.badge" class="nav-badge">{{ item.badge }}</em>
                  </router-link>
                </template>
              </div>
            </transition>
          </template>
        </div>
      </nav>

      <div class="sidebar-footer">v1.0.0 · 华邦服装</div>
    </aside>

    <!-- ====== 主体区 ====== -->
    <div class="hb-main-wrap">
      <header class="hb-header">
        <div class="header-left">
          <button class="mobile-nav-button" aria-label="打开导航" @click="mobileSidebarOpen = true">
            <el-icon><Menu /></el-icon>
          </button>
          <span class="header-page-title">{{ currentTitle }}</span>
        </div>
        <div class="header-right">
          <el-dropdown trigger="click" @command="handleUserCommand">
            <div class="header-user header-user-clickable">
              <div class="user-avatar">{{ userInitial }}</div>
              <span class="user-name">{{ authStore.userInfo?.real_name || authStore.userInfo?.username }}</span>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="change-password">修改密码</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <button class="logout-btn" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出
          </button>
        </div>
      </header>

      <main class="hb-content">
        <router-view />
      </main>

      <el-dialog v-model="passwordDialogVisible" title="修改密码" width="460px" append-to-body>
        <el-form :model="passwordForm" label-width="96px">
          <el-form-item label="原密码" required>
            <el-input v-model="passwordForm.old_password" type="password" show-password autocomplete="current-password" />
          </el-form-item>
          <el-form-item label="新密码" required>
            <el-input v-model="passwordForm.new_password" type="password" show-password autocomplete="new-password" placeholder="至少8位，建议包含字母和数字" />
          </el-form-item>
          <el-form-item label="确认密码" required>
            <el-input v-model="passwordForm.confirm_password" type="password" show-password autocomplete="new-password" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="passwordDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="passwordSubmitting" @click="submitChangePassword">确认修改</el-button>
        </template>
      </el-dialog>

      <BossAiFloatingAssistant />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import BossAiFloatingAssistant from "@/components/ai/BossAiFloatingAssistant.vue";
import { financeProfitNavigation } from "@/config/financeCenterModules";
import { mumarenFinanceCenterMenuItem } from "@/config/mumarenFinanceCenter";
import { ElMessage, ElMessageBox } from "element-plus";
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
  Menu,
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
const mobileSidebarOpen = ref(false);

watch(() => route.fullPath, () => { mobileSidebarOpen.value = false; });

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

interface MenuItem {
  path?: string;
  label: string;
  icon?: unknown;
  key?: string;
  permission?: string;
  disabled?: boolean;
  badge?: string;
  children?: MenuItem[];
}
interface MenuGroup {
  path?: string;
  label: string;
  icon?: unknown;
  items?: MenuItem[];
  permission?: string;
}

const canShow = (item: MenuItem) => {
  if (item.permission) return authStore.hasPermission(item.permission);
  return true;
};
const canShowGroup = (group: MenuGroup) => {
  if (group.permission) return authStore.hasPermission(group.permission);
  return true;
};

const menuGroups = computed<MenuGroup[]>(() => [
  {
    path: "/app/dashboard",
    label: "经营总览",
    icon: DataLine,
    permission: "dashboard:overview:view",
  },
  {
    label: "AI经营诊断",
    icon: ChatDotRound,
    permission: "diagnosis:overall:view",
    items: [
      { path: "/app/ai-diagnosis/overview", icon: ChatDotRound, label: "总体经营诊断" },
      { path: "/app/ai-diagnosis/sales", icon: TrendCharts, label: "销售诊断" },
      { path: "/app/ai-diagnosis/products", icon: GoodsFilled, label: "商品诊断" },
      { path: "/app/ai-diagnosis/inventory", icon: Box, label: "库存诊断" },
      { path: "/app/ai-diagnosis/hr", icon: UserFilled, label: "人力诊断" },
      { path: "/app/ai-diagnosis/finance", icon: Money, label: "财务诊断" },
      { path: "/app/ai-diagnosis/members", icon: User, label: "会员诊断" },
      { path: "/app/ai-diagnosis/audit", icon: Warning, label: "异常稽核" },
      { path: "/app/ai-diagnosis/actions", icon: List, label: "行动闭环" },
    ],
  },
  {
    label: "销售中心",
    icon: TrendCharts,
    permission: "sales:overview:view",
    items: [
      {
        icon: Shop,
        label: "线下销售",
        key: "sales-offline",
        children: [
          { path: "/app/store", label: "单店分析" },
          { path: "/app/member", label: "会员运营" },
          { label: "导购销售", disabled: true, badge: "规划中" },
        ],
      },
      {
        icon: DataLine,
        label: "线上销售",
        key: "sales-online",
        children: [
          { path: "/app/marketing/investment", label: "投流优化" },
          { path: "/app/report", label: "经营日报", permission: "dashboard:overview:view" },
          { label: "线上总览", disabled: true, badge: "规划中" },
          { label: "平台销售", disabled: true, badge: "规划中" },
          { label: "退款售后", disabled: true, badge: "规划中" },
        ],
      },
      { path: "/app/warning", icon: Warning, label: "销售异常" },
    ],
  },
  {
    label: "商品经营",
    icon: GoodsFilled,
    permission: "product:overview:view",
    items: [
      { path: "/app/product", icon: GoodsFilled, label: "商品总览" },
      { path: "/app/product/products", icon: GoodsFilled, label: "商品主档" },
      { path: "/app/product/skus", icon: Box, label: "SKU档案" },
      { path: "/app/product/size-wall", icon: Box, label: "断码尺码墙" },
      { label: "动销分析", icon: TrendCharts, disabled: true, badge: "规划中" },
      { label: "爆款补货", icon: DataLine, disabled: true, badge: "规划中" },
      { label: "滞销清仓", icon: Warning, disabled: true, badge: "规划中" },
    ],
  },
  {
    label: "采购协同",
    icon: List,
    permission: "purchase:overview:view",
    items: [
      { label: "采购总览", icon: List, disabled: true, badge: "规划中" },
      { label: "采购订单", icon: List, disabled: true, badge: "规划中" },
      { label: "供应商管理", icon: User, disabled: true, badge: "规划中" },
      { label: "到货跟踪", icon: Refresh, disabled: true, badge: "规划中" },
    ],
  },
  {
    label: "库存风控",
    icon: Box,
    permission: "inventory:overview:view",
    items: [
      { path: "/app/inventory", icon: Warning, label: "库存总览" },
      { path: "/app/inventory/balance", icon: Box, label: "库存余额" },
      { path: "/app/inventory/warehouses", icon: House, label: "仓库档案" },
      { label: "库龄分析", icon: DataLine, disabled: true, badge: "规划中" },
      { label: "调拨建议", icon: Refresh, disabled: true, badge: "规划中" },
      { path: "/app/warning", icon: Warning, label: "异常库存" },
    ],
  },
  {
    label: "财务利润",
    icon: Money,
    items: [mumarenFinanceCenterMenuItem, ...financeProfitNavigation],
  },
  {
    label: "人力资源",
    icon: UserFilled,
    permission: "hr:overview:view",
    items: [
      { path: "/app/hr/overview", icon: UserFilled, label: "人事首页" },
      { path: "/app/task", icon: Bell, label: "任务管理", permission: "task:view" },
      { path: "/app/hr/employees", icon: Avatar, label: "员工档案" },
      { path: "/app/hr/attendance", icon: List, label: "考勤管理" },
      { path: "/app/hr/leaves", icon: Bell, label: "请假外出" },
      { label: "人效分析", icon: DataLine, disabled: true, badge: "规划中" },
    ],
  },
  {
    label: "知识中枢",
    icon: ChatDotRound,
    permission: "knowledge:ai:view",
    items: [
      { path: "/app/ai", icon: ChatDotRound, label: "AI助手" },
      { label: "经营知识库", icon: List, disabled: true, badge: "规划中" },
      { label: "制度文档", icon: Key, disabled: true, badge: "规划中" },
      { label: "AI问答记录", icon: Refresh, disabled: true, badge: "规划中" },
    ],
  },
  {
    label: "系统设置",
    icon: Key,
    permission: "system:dashboard:view",
    items: [
      { path: "/app/system/admin", icon: DataLine, label: "管理后台", permission: "system:dashboard:view" },
      { path: "/app/system/register-audit", icon: List, label: "注册审核", permission: "system:register:review" },
      { path: "/app/system/module-permissions", icon: Key, label: "岗位权限矩阵", permission: "system:permission:view" },
      { path: "/app/system/data-permissions", icon: Box, label: "数据权限", permission: "system:data-scope:update" },
      { path: "/app/system/field-permissions", icon: List, label: "字段权限", permission: "system:field-permission:update" },
      { path: "/app/system/security", icon: Warning, label: "安全设置", permission: "system:security:update" },
      { path: "/app/system/users", icon: Avatar, label: "用户管理", permission: "system:user:view" },
      { path: "/app/system/roles", icon: Key, label: "角色权限", permission: "system:role:view" },
      { path: "/app/system/sync", icon: Refresh, label: "数据同步", permission: "system:sync:view" },
      { path: "/app/system/baison-api", icon: Refresh, label: "百胜API管理", permission: "system:baison-api:view" },
      { path: "/app/system/operation-logs", icon: List, label: "操作日志", permission: "system:operation-log:view" },
      { path: "/app/dingtalk", icon: Bell, label: "钉钉配置", permission: "system:dingtalk:view" },
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
    .filter(canShowGroup)
    .map((group) => ({ ...group, items: group.items ? filterItems(group.items) : undefined }))
    .filter((group) => Boolean(group.path) || Boolean(group.items?.length));
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
  Boolean(group.path && isActive(group.path)) ||
  Boolean(group.items?.some((item) => (item.path ? isActive(item.path) : false) || (item.children ? isAnyChildActive(item.children) : false)));

const expandActiveMenuPath = () => {
  const next = new Set(expandedMenus.value);
  let changed = false;
  menuGroups.value.forEach((group) => {
    if (!group.items?.length || !isGroupActive(group)) return;
    const groupMenuKey = groupKey(group);
    if (!next.has(groupMenuKey)) {
      next.add(groupKey(group));
      changed = true;
    }
    group.items.forEach((item) => {
      if (!item.children?.length || !isAnyChildActive(item.children)) return;
      const childMenuKey = menuKey(item);
      if (!next.has(childMenuKey)) {
        next.add(menuKey(item));
        changed = true;
      }
      // 展开第3级中包含活跃路由的节点(支持4级菜单)
      item.children.forEach((leaf) => {
        if (!leaf.children?.length || !isAnyChildActive(leaf.children)) return;
        const leafMenuKey = menuKey(leaf);
        if (!next.has(leafMenuKey)) {
          next.add(leafMenuKey);
          changed = true;
        }
      });
    });
  });
  if (!changed) return;
  expandedMenus.value = next;
  saveExpandedMenus(next);
};

watch(() => route.path, expandActiveMenuPath, { immediate: true });


const passwordDialogVisible = ref(false);
const passwordSubmitting = ref(false);
const passwordForm = reactive({ old_password: "", new_password: "", confirm_password: "" });

const resetPasswordForm = () => {
  passwordForm.old_password = "";
  passwordForm.new_password = "";
  passwordForm.confirm_password = "";
};

const handleUserCommand = (command: string) => {
  if (command === "change-password") {
    resetPasswordForm();
    passwordDialogVisible.value = true;
  }
};

const submitChangePassword = async () => {
  if (!passwordForm.old_password || !passwordForm.new_password || !passwordForm.confirm_password) {
    ElMessage.warning("请完整填写原密码、新密码和确认密码");
    return;
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning("两次输入的新密码不一致");
    return;
  }
  passwordSubmitting.value = true;
  try {
    await authApi.changePassword({ ...passwordForm });
    ElMessage.success("密码修改成功，请重新登录");
    passwordDialogVisible.value = false;
    await authStore.logout();
    router.push("/login");
  } finally {
    passwordSubmitting.value = false;
  }
};

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
.nav-group-link {
  padding-left: 12px;
}
.nav-disabled {
  cursor: not-allowed;
  opacity: 0.46;
}
.nav-disabled:hover {
  background: transparent;
  color: rgba(255, 255, 255, 0.6);
}
.nav-badge {
  flex-shrink: 0;
  font-style: normal;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.46);
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 999px;
  padding: 1px 6px;
}
.nav-parent .nav-arrow {
  margin-left: auto;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.32);
  transition: transform 0.16s ease, color 0.16s ease;
}
.nav-parent.expanded .nav-arrow,
.nav-parent-2.expanded .nav-arrow,
.nav-parent-3.expanded .nav-arrow {
  transform: rotate(90deg);
  color: rgba(255, 255, 255, 0.75);
}
.submenu-list {
  padding: 2px 0 4px;
}
.submenu-list-2 {
  padding-left: 8px;
}
.submenu-list-3 {
  padding-left: 8px;
}
.nav-sub {
  padding-left: 38px;
  font-size: 13px;
}
.nav-parent-2 {
  padding-left: 38px;
}
.nav-parent-3 {
  padding-left: 50px;
  font-size: 12.5px;
}
.nav-sub-2 {
  padding-left: 50px;
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.5);
}
.nav-sub-3 {
  padding-left: 62px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
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
.sidebar-scrim { display: none; }
.mobile-nav-button { display: none; }

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

@media (max-width: 760px) {
  .hb-sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 120;
    transform: translateX(-100%);
    transition: transform .2s ease;
    box-shadow: 12px 0 32px rgba(2, 18, 37, .24);
  }
  .hb-sidebar.mobile-open { transform: translateX(0); }
  .sidebar-scrim {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 110;
    border: 0;
    background: rgba(15, 23, 42, .42);
  }
  .hb-main-wrap { width: 100%; }
  .hb-header { height: 52px; padding: 0 12px; }
  .header-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .mobile-nav-button {
    display: grid;
    width: 34px;
    height: 34px;
    place-items: center;
    flex: 0 0 auto;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    background: #fff;
    color: #334155;
  }
  .header-page-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .header-right { gap: 6px; }
  .user-name, .logout-btn { font-size: 0; }
  .logout-btn { width: 34px; height: 34px; padding: 0; justify-content: center; }
  .logout-btn .el-icon { font-size: 16px; }
  .hb-content { padding: 12px; }
}
</style>

<style scoped>
.header-user-clickable { cursor: pointer; }
.header-user-clickable:hover .user-name { color: #1e5eff; }
</style>
