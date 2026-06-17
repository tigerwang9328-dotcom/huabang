import axios from "axios";
import type { AxiosResponse } from "axios";
import { ElMessage } from "element-plus";

export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
  success: boolean;
}

const request = axios.create({
  baseURL: "/api/v1",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// 请求拦截：注入JWT Token
request.interceptors.request.use((config) => {
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
      localStorage.removeItem("access_token");
      window.location.href = "/login";
      return Promise.reject(new Error("登录已过期，请重新登录"));
    }
    if (!data.success && data.code !== 200) {
      ElMessage.error(data.message || "操作失败");
      return Promise.reject(new Error(data.message));
    }
    return response;
  },
  (error) => {
    const msg = error.response?.data?.message || error.message || "网络错误";
    ElMessage.error(msg);
    return Promise.reject(error);
  }
);

export default request;
