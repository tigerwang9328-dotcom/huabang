import request from "./request";

export const productApi = {
  // 标准商品维(dim_product)分页查询
  listProducts: (params?: any) => request.get("/product/list", { params }),
  // 商品/SKU 数据质量汇总
  getQualitySummary: () => request.get("/product/quality-summary"),
  // 同步百胜商品主档（全量 116 页约 50s，单独放长超时）
  syncProducts: (payload?: any) =>
    request.post("/sync/baison/products", payload || { full_sync: true, page_size: 20 }, { timeout: 600000 }),
  // SKU 档案
  listSkus: (params?: any) => request.get("/product/sku-list", { params }),
  // 同步 SKU（全量后台执行，立即返回）
  syncSkus: (payload?: any) =>
    request.post("/sync/baison/skus", payload || { full_sync: true, page_size: 20 }, { timeout: 120000 }),
};
