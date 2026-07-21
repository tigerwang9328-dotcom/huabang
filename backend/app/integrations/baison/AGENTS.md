# backend/app/integrations/baison — 百胜 E3ERP 集成

<!-- agentmap:generated:start -->
## 范围

百胜 E3ERP 开放平台集成:签名/HTTP 客户端/配置 + 15 个业务同步服务。**不负责**:业务汇总逻辑(在 services)、HTTP 路由。

## 关键文件

### 客户端基础设施
- `config.py` — `BaisonConfig`(base_url/app_key/app_secret/page_size 等),`get_baison_config()` 从 settings 注入
- `auth.py` — `generate_sign()`:百胜 v2.0 MD5 签名(参数排序拼接 + AppSecret)
- `client.py` — `BaisonClient`:拼装公共参数 + 签名 + httpx 请求 + 脱敏日志;`BaisonResponse` 保留 raw_response
- `exceptions.py` — `BaisonConfigError`/`BaisonRequestError`/`BaisonAuthError`

### 业务同步服务(services/)
- `pos_ticket_service.py`(744 行)— 小票同步,**`_save_batch` 必须按 lx 处理退货取负**
- `pos_sale_goods_service.py`(467 行)— 销售商品汇总,只过滤 7 个销售门店
- `inventory_service.py`(263 行)— 库存同步,`_list_store_codes` 返回 10 个库存白名单编码
- `member_service.py` / `member_deposit_service.py` — 会员/储值
- `product_service.py` / `sku_service.py` / `product_image_service.py` — 商品/SKU/图片
- `product_inbound_service.py` / `product_transfer_inbound_service.py` — 入库/调拨入库
- `shop_service.py` / `warehouse_service.py` / `store_mapping_service.py` — 门店/仓库/映射
- `store_target_service.py` — 门店目标

## 本地状态与失败行为

- 配置缺失:`BaisonConfigError` 启动即抛
- 网络/5xx:`TRANSPORT_RETRY_DELAYS = (1.0, 2.0)` 重试 2 次
- 业务错误码:不重试,抛 `BaisonRequestError`
- 签名错误:百胜返回 `sign_error`,检查 AppSecret 与时间戳时区

## 公共输入/输出

- 入参:method 名 + 业务参数 dict(分页/时间范围/过滤)
- 出参:`BaisonResponse(status_code, raw_response, data, request_params)`
- 落库:写入 `ods.*` 与部分 `dwd.*`(如 `dwd_pos_ticket`)

## 模块不变量

1. **百胜 v2.0 公共参数**:`method`/`format=json`/`key`/`timestamp`/`v=2.0`/`sign_method=md5`/`data`;业务参数 JSON 紧凑序列化进 `data`,不平铺根参数。
2. **AppSecret 只本地签名**,绝不进请求参数、绝不进日志(`client.py mask_params` 脱敏)。
3. **timestamp 必须北京时间**(Asia/Shanghai),`baison_timestamp()`。
4. **`pos_ticket_service._save_batch` 必须按 `lx` 字段处理**:`lt`=退货取负(`ls`=正常销售正数);遗漏导致销售额虚高。
5. **`inventory_service._list_store_codes` 返回 10 个库存白名单编码**;销售商品/小票汇总只过滤 7 个销售门店。
6. 重试只对网络/5xx,不对业务错误码重试。

## 焦点测试/构建命令

```bash
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest tests/test_baison_auth.py tests/test_baison_client_retry.py tests/test_baison_member_service.py tests/test_baison_member_deposit_service.py tests/test_baison_standard_purchase_price.py tests/test_baison_store_target_service.py tests/test_pos_ticket_sync_completeness.py tests/test_inventory_sync_business_date.py -q
```
<!-- agentmap:generated:end -->

## 手动备注

`pos_ticket_service._save_batch` 的 lx 处理是历史踩坑点(7/15 门店 185805 退货被当销售致虚高 1870 元,后修正并回填 21 条历史退货)。改 lx 逻辑必须回填历史 dwd 并重建 dws/dm。`gz002` 小写需兼容按 `GZ002` 匹配。
