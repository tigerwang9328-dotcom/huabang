import request from "./request";

export interface LoginParams { username: string; password: string; }
export interface RegisterApplyParams {
  username: string;
  password: string;
  confirm_password: string;
  real_name: string;
  phone: string;
  apply_role: string;
  department?: string;
  store_code?: string;
  remark?: string;
}
export interface LoginResult {
  access_token: string; refresh_token: string;
  user_id: number; username: string; real_name: string;
  roles: string[]; permissions: string[]; data_scope: string; is_admin: boolean;
}

export const authApi = {
  login: (params: LoginParams) => request.post<any, any>("/auth/login", params),
  logout: () => request.post("/auth/logout"),
  changePassword: (data: { old_password: string; new_password: string; confirm_password: string }) => request.post("/auth/change-password", data),
  registerApply: (params: RegisterApplyParams) => request.post("/auth/register-apply", params),
};
