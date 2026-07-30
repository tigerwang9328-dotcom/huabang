# 华邦财务中心 V2.0 接口契约

> 状态：本地实现契约，2026-07-30 更新。生产当前仍以已部署版本和 Gate 状态为准；本文不构成生产开写授权。

## 路由与权限

- V2 后端唯一前缀：`/api/v1/finance-center/v2`。
- V2 前端唯一前缀：`/app/finance-center`。
- 只读查询需要中台权限 `finance:center:view`；人工操作需要 `finance:center:operate`。首版仅由财务角色与超级管理员获得这两个权限。
- 路由必须使用受限的 Finance V2 数据库会话，不能回退到通用业务会话或直接访问金蝶源表。

## 只读验收阶段

| 类别 | V2 路径 | 写入语义 |
| --- | --- | --- |
| 账簿、期间、科目、余额与监控 | `GET /books`、`GET /books/{id}/periods`、`GET /books/{id}/accounts`、`GET /books/{id}/periods/{period}/trial-balance`、`GET /monitoring/summary` | 只读 |
| 当前账凭证 | `GET /vouchers`、`GET /vouchers/{id}` | 只读 |
| 已发布历史金蝶 | `GET /history/vouchers`、`GET /history/vouchers/{id}/lines` | 只读 `fin_read` 视图，必须显示历史标记 |
| 写入 readiness | `GET /books/{id}/write-readiness` | 只返回 Gate 与期初边界结论，不能开启 Gate |
| 期初核对 | `GET /books/{id}/opening-balances` | 只读批次状态 |

旧 `/api/v1/finance/*` 与 `/api/v1/finance-center/*` 在只读验收期仍是旧系统的正式制单、审核、过账路径；V2 不关闭、不替代且不双写这些路径。

## 期初余额命令

| 路径 | 前置 | 效果 |
| --- | --- | --- |
| `POST /books/{id}/opening-balances` | `finance:center:operate` | 创建预演或最终期初草稿，记录幂等键和审计事件；不改变启用日 |
| `POST /books/{id}/opening-balances/{batch}/validate` | `finance:center:operate`，草稿版本匹配 | 校验借贷与来源，状态转为 `validated` |
| `POST /books/{id}/opening-balances/{batch}/lock` | `finance:center:operate`、`cutover_enabled`、已验证批次版本匹配 | 锁定期初并写审批/审计；不自动开启制单、审核、过账 |

所有命令请求包含不可复用的 `command_id` 与 `expected_version`（创建除外）；重复请求仅在请求哈希相同的情况下返回原结果。并发冲突返回 HTTP 409，业务不变量不满足返回 HTTP 400，未获权限或 Gate 未开返回 HTTP 403。

## 当前账命令与 Gate

| 命令 | API | 必须 Gate |
| --- | --- | --- |
| 草稿创建/编辑/提交/撤回/取消 | `POST/PUT /vouchers`、凭证命令 | `draft_enabled` + 最终锁定期初 |
| 领取审核/批准/驳回 | 凭证命令 | `review_enabled` + 最终锁定期初 |
| 人工过账/冲销 | 凭证命令 | `post_enabled` + 最终锁定期初 |
| 结账/反结账 | 期间命令 | `period_close_enabled` + 最终锁定期初 |
| 最终期初锁定 | 期初锁定命令 | `cutover_enabled`，不等同普通写入 Gate |

全局紧急停止优先于任何以上 Gate。最终切换完成后，旧制单可转接 V2 或返回 410；旧审核和过账永久返回 410。实际弃用日期必须写入最终切换证据，未切换前不得提前关闭旧入口。
