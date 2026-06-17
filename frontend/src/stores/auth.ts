import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { authApi } from "@/api/auth";
import { ElMessage } from "element-plus";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string>(localStorage.getItem("access_token") || "");
  const userInfo = ref<any>(JSON.parse(localStorage.getItem("user_info") || "null"));

  const isLoggedIn = computed(() => !!token.value);
  const roles = computed<string[]>(() => userInfo.value?.roles || []);
  const isAdmin = computed(() => userInfo.value?.is_admin || false);

  const hasRole = (role: string) => roles.value.includes(role) || isAdmin.value;
  const hasAnyRole = (...roleList: string[]) => roleList.some(r => hasRole(r));

  const login = async (username: string, password: string) => {
    const res = await authApi.login({ username, password });
    const data = res.data.data;
    token.value = data.access_token;
    userInfo.value = data;
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("user_info", JSON.stringify(data));
    return data;
  };

  const logout = async () => {
    try { await authApi.logout(); } catch {}
    token.value = "";
    userInfo.value = null;
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_info");
  };

  return { token, userInfo, isLoggedIn, roles, isAdmin, hasRole, hasAnyRole, login, logout };
});
