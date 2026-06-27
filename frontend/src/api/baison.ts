import request from "./request";

export const baisonApi = {
  // 门店档案分页查询
  listShops: (params?: any) =>
    request.get("/integrations/baison/shops", { params }),
  // 门店详情（含 raw_data）
  getShopDetail: (shopCode: string) =>
    request.get(`/integrations/baison/shops/${encodeURIComponent(shopCode)}`),
  // 同步门店档案（全量分页）
  syncShops: (payload?: any) =>
    request.post("/integrations/baison/sync/shops", payload || { full_sync: true, page_size: 20 }),
};
