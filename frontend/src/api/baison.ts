import request from "./request";

export const baisonApi = {
  // 百胜接口目录
  getCatalog: () =>
    request.get("/integrations/baison/catalog"),
  // 通用接口联调（不落库）
  testApi: (payload: {
    method: string;
    params?: Record<string, any>;
    timeout?: number;
    include_raw_response?: boolean;
  }) =>
    request.post("/integrations/baison/api-test", {
      params: {},
      timeout: 30,
      include_raw_response: true,
      ...payload,
    }),
  // 按业务模块同步落库
  syncModule: (moduleKey: string, payload?: any) =>
    request.post(`/integrations/baison/sync/module/${encodeURIComponent(moduleKey)}`, payload || { full_sync: true, page_size: 20 }),
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
