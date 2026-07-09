import request from "./request";

export const systemApi = {
  getUsers: (params?: any) => request.get("/system/users", { params }),
  createUser: (data: any) => request.post("/system/users", data),
  updateUser: (id: number, data: any) => request.put(`/system/users/${id}`, data),
  deleteUser: (id: number) => request.delete(`/system/users/${id}`),
  getRoles: () => request.get("/system/roles"),
  getParams: () => request.get("/system/params"),
  getModulePermissionMatrix: () => request.get("/system/permissions/module-matrix"),
  getRegisterApplications: (params?: any) => request.get("/system/register-applications", { params }),
  approveRegisterApplication: (id: string) => request.post(`/system/register-applications/${id}/approve`),
  rejectRegisterApplication: (id: string, data: any) => request.post(`/system/register-applications/${id}/reject`, data),
};
