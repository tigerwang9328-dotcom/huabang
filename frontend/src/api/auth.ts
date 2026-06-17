import request from "./request";

export interface LoginParams { username: string; password: string; }
export interface LoginResult {
  access_token: string; refresh_token: string;
  user_id: number; username: string; real_name: string;
  roles: string[]; is_admin: boolean;
}

export const authApi = {
  login: (params: LoginParams) => request.post<any, any>("/auth/login", params),
  logout: () => request.post("/auth/logout"),
};
