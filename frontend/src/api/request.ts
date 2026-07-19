import axios from "axios";
import type { AxiosResponse } from "axios";
import { ElMessage } from "element-plus";
import {
  isRouteRequestCanceled,
  RouteRequestLifecycle,
  shouldScopeRouteRequest,
} from "./routeRequestLifecycle";

export { isRouteRequestCanceled } from "./routeRequestLifecycle";

declare module "axios" {
  interface AxiosRequestConfig {
    silentError?: boolean;
    persistAcrossRoutes?: boolean;
    routeScoped?: boolean;
  }
}

export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
  success: boolean;
}

let isSessionRedirecting = false;
const routeRequests = new RouteRequestLifecycle();

export const cancelRouteRequests = () => {
  routeRequests.cancel();
};

const isLoginRequest = (url?: string) => url?.includes("/auth/login") === true;

const redirectExpiredSession = () => {
  localStorage.removeItem("access_token");
  localStorage.removeItem("user_info");

  if (isSessionRedirecting || window.location.pathname === "/login") return;
  isSessionRedirecting = true;
  window.location.replace("/login?reason=expired");
};

const request = axios.create({
  baseURL: "/api/v1",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// 请求拦截：注入JWT Token
request.interceptors.request.use((config) => {
  if (shouldScopeRouteRequest(
    config.method,
    window.location.pathname,
    config.persistAcrossRoutes,
    Boolean(config.signal),
  )) {
    config.signal = routeRequests.signal;
    config.routeScoped = true;
  }
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截：统一错误处理
request.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    const data = response.data;
    if (data.code === 401) {
      if (isLoginRequest(response.config.url)) {
        ElMessage.error(data.message || "用户名或密码错误");
        return Promise.reject(new Error(data.message || "用户名或密码错误"));
      }
      redirectExpiredSession();
      return Promise.reject(new Error("登录已过期，请重新登录"));
    }
    if (!data.success && data.code !== 200) {
      if (!response.config.silentError) ElMessage.error(data.message || "操作失败");
      return Promise.reject(new Error(data.message));
    }
    return response;
  },
  (error) => {
    if (isRouteRequestCanceled(error)) return Promise.reject(error);
    const status = error.response?.status;
    const code = error.response?.data?.code;
    if (status === 401 || code === 401) {
      if (isLoginRequest(error.config?.url)) {
        const loginMsg = error.response?.data?.message || "用户名或密码错误";
        ElMessage.error(loginMsg);
        return Promise.reject(new Error(loginMsg));
      }
      redirectExpiredSession();
      return Promise.reject(new Error("登录已过期，请重新登录"));
    }
    const msg = error.response?.data?.message || error.message || "网络错误";
    if (!error.config?.silentError) ElMessage.error(msg);
    return Promise.reject(error);
  }
);

export default request;
