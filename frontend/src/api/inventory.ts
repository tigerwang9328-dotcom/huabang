import request from "./request";

export const inventoryApi = {
  // 库存管理顶部汇总（百胜库存 + SKU成本）
  getSummary: () => request.get("/inventory/summary"),
  // 库存总览：按 7 个销售门店 + 3 个仓库汇总
  getOverview: () => request.get("/inventory/overview"),
  // 标准仓库维(dim_warehouse)分页查询
  listWarehouses: (params?: any) => request.get("/inventory/warehouses", { params }),
  // 同步百胜仓库档案（59条/3页，直接返回）
  syncWarehouses: (payload?: any) =>
    request.post("/sync/baison/warehouses", payload || { full_sync: true, page_size: 20 }, { timeout: 120000 }),
  // 库存余额
  listInventory: (params) => request.get("/inventory/balance", { params }),
  // 同步库存余额（逐店全量后台执行，立即返回）
  syncInventory: (payload) =>
    request.post("/sync/baison/inventory", payload || { full_sync: true, page_size: 20 }, { timeout: 120000 }),
  listWarnings: (params?: any) => request.get("/inventory/warnings", { params }),
  createWarningTask: (warningId: number) => request.post(`/inventory/warnings/${warningId}/task-draft`),
};
