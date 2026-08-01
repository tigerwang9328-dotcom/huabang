import request from "./request";

export interface AttendanceParams {
  page?: number;
  page_size?: number;
  work_date?: string;
  date_from?: string;
  date_to?: string;
  department?: string;
  status?: string;
  keyword?: string;
}

export const hrApi = {
  getOverview: () => request.get("/hr/overview"),
  getEmployees: (params?: { page?: number; page_size?: number }) => request.get("/hr/employees", { params }),
  getAttendance: (params?: AttendanceParams) => request.get("/hr/attendance", { params }),
  getAttendanceSummary: (params?: { work_date?: string }) => request.get("/hr/attendance/summary", { params }),
  getAttendanceDepartments: (params?: { work_date?: string }) => request.get("/hr/attendance/departments", { params }),
  getDepartments: () => request.get("/hr/departments"),
  getApprovals: (params?: { category?: string; page?: number; page_size?: number }) => request.get("/hr/approvals", { params }),
  syncDingtalk: (data: { scope: "employees" | "attendance" | "approvals" | "all"; days?: number; dry_run?: boolean }) =>
    request.post("/hr/sync-dingtalk", data, { timeout: 180000 }),
  getLeaves: (params?: { page?: number; page_size?: number }) => request.get("/hr/leaves", { params }),
};
