import request from "./request";

export const storeApi = {
  // 标准门店维(dim_store)分页查询
  listStores: (params?: any) => request.get("/store/list", { params }),
  // 独立门店销售数据
  getSalesAnalysis: (params?: any) => request.get("/store/sales-analysis", { params }),
};
