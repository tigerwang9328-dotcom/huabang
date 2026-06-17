import request from "./request";

export const syncApi = {
  getStatus: () => request.get("/sync/status"),
  getLogs: (params?: any) => request.get("/sync/logs", { params }),
  importExcel: (dataType: string, file: File) => {
    const formData = new FormData();
    formData.append("data_type", dataType);
    formData.append("file", file);
    return request.post("/sync/baison/import-excel", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  previewExcel: (dataType: string, file: File) => {
    const formData = new FormData();
    formData.append("data_type", dataType);
    formData.append("file", file);
    return request.post("/sync/preview", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  rollbackBatch: (batchNo: string) =>
    request.post(`/sync/rollback/${encodeURIComponent(batchNo)}`),
  runEtl: (statDate?: string) =>
    request.post("/etl/run", null, {
      params: { stat_date: statDate, step: "full" },
    }),
  getEtlLogs: (params?: any) => request.get("/etl/logs", { params }),
  getEtlStatus: () => request.get("/etl/status"),
};
