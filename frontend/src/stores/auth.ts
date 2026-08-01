import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { authApi } from "@/api/auth";
import { ElMessage } from "element-plus";

function isJwtUsable(value: string): boolean {
  if (!value) return false;
  try {
    const payload = value.split(".")[1];
    if (!payload) return false;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const decoded = JSON.parse(atob(padded));
    return typeof decoded.exp === "number" && decoded.exp * 1000 > Date.now() + 5000;
  } catch {
    return false;
  }
}

function readUserInfo(tokenIsValid: boolean): any {
  if (!tokenIsValid) return null;
  try {
    return JSON.parse(localStorage.getItem("user_info") || "null");
  } catch {
    localStorage.removeItem("user_info");
    return null;
  }
}

export const useAuthStore = defineStore("auth", () => {
  const persistedToken = localStorage.getItem("access_token") || "";
  const tokenIsValid = isJwtUsable(persistedToken);
  if (!tokenIsValid) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_info");
  }

  const token = ref<string>(tokenIsValid ? persistedToken : "");
  const userInfo = ref<any>(readUserInfo(tokenIsValid));

  const isLoggedIn = computed(() => isJwtUsable(token.value));
  const roles = computed<string[]>(() => userInfo.value?.roles || []);
  const isAdmin = computed(() => userInfo.value?.is_admin || false);
  const permissions = computed<string[]>(() => userInfo.value?.permissions || []);
  const dataScope = computed<string>(() => userInfo.value?.data_scope || "self");

  const hasRole = (role: string) => roles.value.includes(role) || isAdmin.value;
  const hasAnyRole = (...roleList: string[]) => roleList.some(r => hasRole(r));
  const hasPermission = (permission: string) => isAdmin.value || permissions.value.includes("*") || permissions.value.includes(permission);
  const hasAnyPermission = (...permissionList: string[]) => permissionList.some(p => hasPermission(p));

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

  return { token, userInfo, isLoggedIn, roles, permissions, dataScope, isAdmin, hasRole, hasAnyRole, hasPermission, hasAnyPermission, login, logout };
});
