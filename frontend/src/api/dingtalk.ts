import request from "./request";

export const dingtalkApi = {
  /** 经营概览 - 钉钉协同数据统计 */
  getDingtalkOverview: () => request.get("/dingtalk/overview"),
};
