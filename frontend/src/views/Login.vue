<template>
  <div class="login-page">
    <div class="login-box">
      <div class="login-header">
        <h1>华邦AI中台</h1>
        <p>华邦服装公司经营智能平台</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" @keyup.enter="handleLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" size="large" prefix-icon="User" clearable />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" size="large" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-button type="primary" size="large" :loading="loading" @click="handleLogin" style="width:100%; margin-top:8px">
          登 录
        </el-button>
      </el-form>
      <div class="login-footer">
        <span>华邦服装 AI中台 v1.0.0</span>
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

const handleLogin = async () => {
  await formRef.value.validate();
  loading.value = true;
  try {
    await authStore.login(form.username, form.password);
    ElMessage.success("登录成功");
    router.push("/");
  } catch (e: any) {
    ElMessage.error(e.message || "登录失败");
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.login-page {
  min-height: 100vh; background: linear-gradient(135deg, #001529 0%, #003366 100%);
  display: flex; align-items: center; justify-content: center;
}
.login-box {
  width: 400px; background: #fff; border-radius: 8px;
  padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}
.login-header { text-align: center; margin-bottom: 32px; }
.login-header h1 { font-size: 24px; color: #001529; margin-bottom: 8px; }
.login-header p { color: #999; font-size: 14px; }
.login-footer { text-align: center; margin-top: 24px; color: #ccc; font-size: 12px; }
</style>
