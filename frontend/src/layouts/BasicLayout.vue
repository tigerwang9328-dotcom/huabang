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

      <!-- 菜单 -->
      <nav class="sidebar-nav">
        <div class="nav-group-label">经营分析</div>
        <router-link to="/dashboard" class="nav-item" :class="{ active: activeMenu === '/dashboard' }">
          <el-icon><DataLine /></el-icon><span>经营概览</span>
        </router-link>
        <router-link to="/boss" class="nav-item" :class="{ active: activeMenu === '/boss' }">
          <el-icon><House /></el-icon><span>经营日报</span>
        </router-link>
        <router-link to="/store" class="nav-item" :class="{ active: activeMenu === '/store' }">
          <el-icon><Shop /></el-icon><span>门店分析</span>
        </router-link>
        <router-link to="/product" class="nav-item" :class="{ active: activeMenu === '/product' }">
          <el-icon><GoodsFilled /></el-icon><span>商品分析</span>
        </router-link>

        <div class="nav-group-label" style="margin-top:16px">风险管理</div>
        <router-link to="/inventory" class="nav-item" :class="{ active: activeMenu === '/inventory' }">
          <el-icon><Box /></el-icon><span>库存预警</span>
        </router-link>
        <router-link to="/warning" class="nav-item" :class="{ active: activeMenu === '/warning' }">
          <el-icon><Warning /></el-icon><span>异常稽核</span>
        </router-link>
        <router-link
          v-if="authStore.hasAnyRole('boss', 'shareholder', 'ceo', 'finance_manager', 'super_admin')"
          to="/finance"
          class="nav-item"
          :class="{ active: activeMenu === '/finance' }"
        >
          <el-icon><Money /></el-icon><span>利润分析</span>
        </router-link>

        <div class="nav-group-label" style="margin-top:16px">运营管理</div>
        <router-link to="/member" class="nav-item" :class="{ active: activeMenu === '/member' }">
          <el-icon><User /></el-icon><span>会员运营</span>
        </router-link>
        <router-link to="/task" class="nav-item" :class="{ active: activeMenu.startsWith('/task') }">
          <el-icon><List /></el-icon><span>任务管理</span>
        </router-link>
        <router-link to="/ai" class="nav-item" :class="{ active: activeMenu === '/ai' }">
          <el-icon><ChatDotRound /></el-icon><span>AI助手</span>
        </router-link>
        <router-link to="/dingtalk" class="nav-item" :class="{ active: activeMenu === '/dingtalk' }">
          <el-icon><Bell /></el-icon><span>钉钉通知</span>
        </router-link>

        <template v-if="authStore.isAdmin || authStore.hasRole('super_admin')">
          <div class="nav-group-label" style="margin-top:16px">系统管理</div>
          <router-link to="/system/users" class="nav-item" :class="{ active: activeMenu === '/system/users' }">
            <el-icon><Avatar /></el-icon><span>用户管理</span>
          </router-link>
          <router-link to="/system/roles" class="nav-item" :class="{ active: activeMenu === '/system/roles' }">
            <el-icon><Key /></el-icon><span>角色权限</span>
          </router-link>
          <router-link to="/system/sync" class="nav-item" :class="{ active: activeMenu === '/system/sync' }">
            <el-icon><Refresh /></el-icon><span>数据同步</span>
          </router-link>
        </template>
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
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ElMessageBox } from "element-plus";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const activeMenu = computed(() => route.path);
const currentTitle = computed(() => (route.meta.title as string) || "华邦AI中台");

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
