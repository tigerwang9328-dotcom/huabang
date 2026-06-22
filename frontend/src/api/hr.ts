import request from "./request";

export const hrApi = {
  getOverview: () => request.get("/hr/overview"),
  getEmployees: (params?: { page?: number; page_size?: number }) => request.get("/hr/employees", { params }),
  getAttendance: (params?: { page?: number; page_size?: number }) => request.get("/hr/attendance", { params }),
  getLeaves: (params?: { page?: number; page_size?: number }) => request.get("/hr/leaves", { params }),
};
