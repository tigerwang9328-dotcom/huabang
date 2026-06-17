import request from "./request";

export const taskApi = {
  getList: (params?: any) => request.get("/task/list", { params }),
  getDetail: (id: number) => request.get(`/task/${id}`),
  create: (data: any) => request.post("/task/create", data),
  confirm: (id: number) => request.post(`/task/${id}/confirm`),
  feedback: (id: number, data: any) => request.post(`/task/${id}/feedback`, data),
  review: (id: number, data: any) => request.post(`/task/${id}/review`, data),
  close: (id: number) => request.post(`/task/${id}/close`),
};
