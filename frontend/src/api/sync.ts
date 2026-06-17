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
};
