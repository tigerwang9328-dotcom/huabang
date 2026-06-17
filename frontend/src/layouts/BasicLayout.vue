<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <span class="logo-text">华邦AI中台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#001529"
        text-color="#b0bec5"
        active-text-color="#409eff"
        :collapse="false"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon>
          <span>经营驾驶舱</span>
        </el-menu-item>
        <el-menu-item index="/boss">
          <el-icon><House /></el-icon>
          <span>老板经营中心</span>
        </el-menu-item>
        <el-menu-item index="/store">
          <el-icon><Shop /></el-icon>
          <span>门店运营中心</span>
        </el-menu-item>
        <el-menu-item index="/product">
          <el-icon><GoodsFilled /></el-icon>
          <span>商品经营中心</span>
        </el-menu-item>
        <el-menu-item index="/inventory">
          <el-icon><Box /></el-icon>
          <span>库存预警中心</span>
        </el-menu-item>
        <el-menu-item index="/member">
          <el-icon><User /></el-icon>
          <span>会员运营中心</span>
        </el-menu-item>
        <el-menu-item index="/finance" v-if="authStore.hasAnyRole(boss,shareholder,ceo,finance_manager,super_admin)">
          <el-icon><Money /></el-icon>
          <span>财务利润中心</span>
        </el-menu-item>
        <el-menu-item index="/task">
          <el-icon><List /></el-icon>
          <span>AI任务中心</span>
        </el-menu-item>
        <el-menu-item index="/warning">
          <el-icon><Warning /></el-icon>
          <span>异常稽核中心</span>
        </el-menu-item>
        <el-menu-item index="/ai">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI助手</span>
        </el-menu-item>
        <el-menu-item index="/dingtalk">
          <el-icon><Bell /></el-icon>
          <span>钉钉协同</span>
        </el-menu-item>
        <el-sub-menu index="/system" v-if="authStore.isAdmin || authStore.hasRole(super_admin)">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/system/users">用户管理</el-menu-item>
          <el-menu-item index="/system/roles">角色管理</el-menu-item>
          <el-menu-item index="/system/sync">数据同步</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="breadcrumb">
          <span class="page-title">{{ currentTitle }}</span>
        </div>
        <div class="user-info">
          <span class="username">{{ authStore.userInfo?.real_name || authStore.userInfo?.username }}</span>
          <el-button type="text" @click="handleLogout" style="margin-left: 12px; color: #666;">
            退出
          </el-button>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
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
const currentTitle = computed(() => route.meta.title as string || "华邦AI中台");

const handleLogout = async () => {
  await ElMessageBox.confirm("确认退出登录？", "提示", { type: "warning" });
  await authStore.logout();
  router.push("/login");
};
</script>

<style scoped>
.layout-container { height: 100vh; }
.sidebar { background: #001529; overflow-y: auto; }
.logo { padding: 20px 16px; border-bottom: 1px solid #002140; }
.logo-text { color: #fff; font-size: 16px; font-weight: 600; }
.header {
  background: #fff; border-bottom: 1px solid #e8e8e8;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px;
}
.page-title { font-size: 16px; font-weight: 500; color: #333; }
.user-info { display: flex; align-items: center; }
.username { color: #333; font-size: 14px; }
.main-content { background: #f5f5f5; padding: 20px; overflow-y: auto; }
</style>
