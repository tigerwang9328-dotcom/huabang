import request from "./request";

export const taskApi = {
  getList: (params?: any) => request.get("/task/list", { params }),
  getDetail: (id: number) => request.get(`/task/${id}`),
  create: (data: any) => request.post("/task/create", data),
  confirm: (id: number, data: any = {}) => request.post(`/task/${id}/confirm`, data),
  retryNotification: (id: number) => request.post(`/task/${id}/retry-notification`),
  feedback: (id: number, data: any) => request.post(`/task/${id}/feedback`, {
    ...data,
    request_id: data.request_id || crypto.randomUUID(),
  }),
  review: (id: number, data: any) => request.post(`/task/${id}/review`, {
    ...data,
    request_id: data.request_id || crypto.randomUUID(),
  }),
  close: (id: number) => request.post(`/task/${id}/close`),
};
