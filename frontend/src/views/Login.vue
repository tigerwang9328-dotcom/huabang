<template>
  <div class="login-root">
    <!-- 左侧品牌面板 -->
    <div class="login-left">
      <div class="left-inner">
        <div class="brand-logo-row">
          <div class="brand-icon">HB</div>
          <div class="brand-name-stack">
            <span class="brand-name">华邦AI中台</span>
            <span class="brand-eng">HUABANG AI CENTER</span>
          </div>
        </div>
        <h2 class="brand-headline">让经营数据<br/>变成每天可执行的管理动作</h2>
        <p class="brand-desc">
          连接百盛ERP、金蝶财务与钉钉协同，沉淀销售、商品、库存、会员、财务与任务闭环，
          帮助老板和管理层快速发现问题、分配责任、追踪结果。
        </p>
        <div class="capability-grid">
          <div class="cap-tag" v-for="cap in capabilities" :key="cap">
            <span class="cap-dot"></span>{{ cap }}
          </div>
        </div>
      </div>
      <div class="left-footer">
        华邦服装股份有限公司 &nbsp;·&nbsp; 内部经营管理系统
      </div>
    </div>

    <!-- 右侧登录面板 -->
    <div class="login-right">
      <div class="login-card">
        <div class="card-top">
          <div class="card-logo">HB</div>
          <h1 class="card-title">华邦AI中台</h1>
          <p class="card-subtitle">服装品牌经营智能平台</p>
        </div>
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          @keyup.enter="handleLogin"
          class="login-form"
        >
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              size="large"
              prefix-icon="User"
              clearable
              class="hb-input"
            />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              prefix-icon="Lock"
              show-password
              class="hb-input"
            />
          </el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
            class="login-btn"
          >
            {{ loading ? "登录中..." : "登 录" }}
          </el-button>
        </el-form>
        <div class="card-footer">
          <span>华邦AI中台 v1.0.0</span>
          <span>&copy; 2026 华邦服装股份有限公司</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ElMessage } from "element-plus";

const router = useRouter();
const authStore = useAuthStore();
const formRef = ref();
const loading = ref(false);

const form = reactive({ username: "", password: "" });
const rules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

const capabilities = [
  "老板经营日报",
  "门店运营诊断",
  "商品动销分析",
  "库存风险预警",
  "AI任务闭环",
  "钉钉协同推送",
];

const handleLogin = async () => {
  await formRef.value.validate();
  loading.value = true;
  try {
    await authStore.login(form.username, form.password);
    ElMessage({ message: "登录成功，欢迎回来", type: "success", duration: 2000 });
    router.push("/");
  } catch (e: any) {
    ElMessage({ message: e.message || "登录失败，请检查用户名和密码", type: "error", duration: 3000 });
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.login-root {
  display: flex;
  min-height: 100vh;
  width: 100%;
}

/* ====== 左侧品牌面板 ====== */
.login-left {
  flex: 0 0 54%;
  background: linear-gradient(145deg, #071A2F 0%, #0B2340 55%, #0D2A4A 100%);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 52px 64px 36px;
  position: relative;
  overflow: hidden;
}

.login-left::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(30, 94, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(30, 94, 255, 0.04) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
}

.login-left::after {
  content: "";
  position: absolute;
  top: -200px;
  right: -150px;
  width: 560px;
  height: 560px;
  background: radial-gradient(circle, rgba(30, 94, 255, 0.1) 0%, transparent 70%);
  pointer-events: none;
}

.left-inner { position: relative; z-index: 1; }

.brand-logo-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 60px;
}
.brand-icon {
  width: 46px;
  height: 46px;
  background: linear-gradient(135deg, #C8A45D, #D6B66A);
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 800;
  color: #fff;
  flex-shrink: 0;
}
.brand-name-stack { display: flex; flex-direction: column; }
.brand-name {
  font-size: 18px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.2;
}
.brand-eng {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  letter-spacing: 0.14em;
  margin-top: 4px;
}

.brand-headline {
  font-size: 30px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.5;
  margin: 0 0 22px;
}

.brand-desc {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.52);
  line-height: 1.9;
  margin: 0 0 44px;
}

.capability-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 20px;
}
.cap-tag {
  display: flex;
  align-items: center;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.72);
  padding: 9px 14px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
}
.cap-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #C8A45D;
  margin-right: 9px;
  flex-shrink: 0;
}

.left-footer {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.22);
  position: relative;
  z-index: 1;
}

/* ====== 右侧登录面板 ====== */
.login-right {
  flex: 1;
  background: #F0F4F9;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 32px;
}

.login-card {
  width: 100%;
  max-width: 400px;
  background: #FFFFFF;
  border-radius: 18px;
  padding: 44px 40px 36px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.09), 0 1px 4px rgba(0, 0, 0, 0.05);
}

.card-top {
  text-align: center;
  margin-bottom: 36px;
}
.card-logo {
  width: 48px;
  height: 48px;
  background: linear-gradient(135deg, #1E5EFF, #1648CC);
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 800;
  color: #fff;
  margin-bottom: 14px;
}
.card-title {
  font-size: 22px;
  font-weight: 700;
  color: #111827;
  margin: 0 0 6px;
}
.card-subtitle {
  font-size: 13px;
  color: #9CA3AF;
  margin: 0;
}

.login-form :deep(.el-form-item) { margin-bottom: 18px; }

.hb-input :deep(.el-input__wrapper) {
  border-radius: 10px;
  border: 1.5px solid #E5E7EB;
  box-shadow: none;
  height: 46px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.hb-input :deep(.el-input__wrapper:hover),
.hb-input :deep(.el-input__wrapper.is-focus) {
  border-color: #1E5EFF;
  box-shadow: 0 0 0 3px rgba(30, 94, 255, 0.1);
}

.login-btn {
  width: 100%;
  height: 48px;
  margin-top: 8px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  background: linear-gradient(135deg, #1E5EFF 0%, #1648CC 100%);
  border: none;
  letter-spacing: 0.04em;
  transition: opacity 0.2s, transform 0.1s;
}
.login-btn:hover { opacity: 0.92; }
.login-btn:active { transform: scale(0.99); }

.card-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid #F3F4F6;
  font-size: 11px;
  color: #D1D5DB;
}

@media (max-width: 860px) {
  .login-left { display: none; }
  .login-right {
    flex: 1;
    padding: 32px 20px;
  }
}
</style>
