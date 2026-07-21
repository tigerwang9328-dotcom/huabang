# 华邦 AI 中台 — Agent 上下文(根)

> 本文件由 `.agentmap.toml` 驱动,管理块在 `<!-- agentmap:generated:* -->` 之间。手动追加内容请放在管理块之外。

<!-- agentmap:generated:start -->
## 项目目的

华邦服装公司 **AI 经营中台**:聚合百胜 E3ERP(销售/库存/会员/商品)、钉钉(审批/考勤/HR/财务)、金蝶 K/3 WISE(历史财务)三类外部数据,经 ETL 管线 `ODS → DWD → DWS → DM` 落 PostgreSQL,向老板与门店提供:

- 经营日报、经营概览、门店/商品/会员/库存诊断
- 老板指挥台(异常健康检查 + 待办任务)
- 投流决策(历史与 DeepSeek 增强)
- 正式可写财务账簿(金蝶历史只读 + fin.* 正式账簿写入)
- AI 经营顾问与老板聊天助手(只读事实层)

## 权威数据/控制流

```
百胜 E3ERP API ──┐
钉钉 OpenAPI/Stream ──┤── integrations/baison · modules/dingtalk ──→ ods.*(原始落档)
金蝶 .bak 还原 ──┘                                            │
                                                              ▼
                                                    services/etl: ods_to_dwd
                                                              ▼
                                              dwd.*(明细,含 lx 退货取负)
                                                              ▼
                                                    services/etl: dwd_to_dws
                                                              ▼
                                    dws.*(日汇总,按门店/仓库白名单过滤)
                                                              ▼
                                                    services/etl: dws_to_dm
                                                              ▼
                          dm.*(老板看板/诊断/预警) + ai.*(建议快照,LLM 只读事实)
                                                              ▼
                              services/* 组装 → api/v1/* → /api/v1/* → Nginx → 前端
```

- **入站触发**:APScheduler(jobs/scheduler.py,FastAPI lifespan 启动)+ crontab(scripts/,UTC)+ 钉钉 Stream(独立 systemd 进程)。
- **出站**:前端 Vue3 dist 由 Nginx 静态提供,`/api/` 反代到 `127.0.0.1:8000`。
- **财务双轨**:金蝶历史(kingdee_finance.*)只读;正式账簿(fin.*)经 `/api/v1/finance-center` 写入,不写回金蝶服务器与原始快照。

## 全局不变量(违反即 bug)

1. **门店/仓库白名单**(core/store_whitelist.py):
   - 销售/收款只看 7 个销售门店:`134681/285204/285702/185805/185808/285101/285102`。
   - 库存获取/展示看 7 门店 + 3 仓库:`GZ001`(总仓)/`GZ002`(残次仓,API 可能显示 `gz002`,按 `GZ002` 匹配)/`GYNG`(内购)。
   - 维度表保留全量以供审计,事实/汇总层必须过滤。
2. **退货取负**:dwd_pos_ticket 中 `lx='lt'`(零售退货)的 `sales_amount/sales_qty/standard_amount/gross_profit_source_amount` 必须为负;`ls` 为正常销售正数。ETL 与同步服务必须按 `lx` 处理,遗漏导致销售额虚高。
3. **实收口径**(core/store_whitelist.ACTUAL_PAY_CODES):实收 = 现金(000)+ 收钱吧(666/971)+ 五月前储值(003)+ VIP 卡消费(004)+ 线上支付(011)− 退款;排除礼券(001)/会员积分(005)。VIP 卡消费进销售额也进实收,但不进充值。
4. **金蝶历史只读**:kingdee_finance.* 表由迁移脚本写入,任何业务代码不得写;正式财务走 fin.* 表。
5. **密钥安全**:AppSecret/JWT 密钥/DB 密码/钉钉 Secret 由 pydantic-settings 从 `.env` 注入,绝不进日志、不进请求参数、不进 Git(.env 在 .gitignore)。
6. **Alembic 单一 head**:迁移不可回灌生产,变更必须 `alembic upgrade head` 且保持单一 head。
7. **时区**:服务器 UTC,APScheduler/crontab 按各自时区表达;百胜 timestamp 必须北京时间(Asia/Shanghai)。

## 顶层模块摘要

| 模块 | 路径 | 职责 |
| --- | --- | --- |
| backend | `backend/` | FastAPI 后端:API/服务/ETL/集成/调度/ORM,uvicorn 127.0.0.1:8000 |
| frontend | `frontend/` | Vue3 + Element Plus + Pinia + ECharts,Nginx 静态部署 |
| scripts | `scripts/` | crontab shell 脚本:同步/备份/快照/健康检查 |

## 跨模块变更规则

- 改 `store_whitelist.py` → 必须同步审查 `pos_ticket_service` / `pos_sale_goods_service` / `inventory_service` / `business_overview_service` / `inventory_analysis_service` / ETL 的 `dwd_to_dws`,并重建受影响日期的 dws/dm。
- 改 `dwd_pos_ticket` 的 lx 处理 → 必须回填历史退货记录并重建 dws/dm。
- 改金蝶正式账簿 schema → 必须配 Alembic 迁移 + 同步 ods/dwd/fin 三层校验。
- 改钉钉 Stream 凭证 → 必须重启 `huabang-dingtalk-stream.service`(单实例)。
- 改前端路由/菜单 → 必须同步 `router/index.ts` 与后端 `seed_module_permissions.py` 权限种子。

## 项目级校验

```bash
# 后端测试 + 迁移 head
cd /srv/huabang-ai-center/backend && .venv/bin/python -m pytest -q && .venv/bin/alembic heads

# 前端类型检查 + 构建
cd /srv/huabang-ai-center/frontend && npm run type-check && npm run build

# 服务健康
curl -s http://127.0.0.1:8000/health
systemctl status huabang-dingtalk-stream.service --no-pager
```

## 运行环境

- 服务器:`100.94.89.49`(Tailscale),Ubuntu 24.04,UTC 时区
- 部署根:`/srv/huabang-ai-center/`
- Python:`backend/.venv`(3.12),Node:`frontend/node_modules`(v22)
- PostgreSQL 16(本地),Redis(本地)
- Nginx:`/etc/nginx/sites-enabled/huabang`,反代 `/api/` → `127.0.0.1:8000`,静态 `frontend/dist`
- 后端 uvicorn 手动启停(非 systemd);钉钉 Stream 走 systemd `huabang-dingtalk-stream.service`
- crontab(用户 xiaohu):数据同步/备份/快照,UTC 时区,北京时间 = UTC + 8
<!-- agentmap:generated:end -->

## 手动备注区

本地开发工作区 `d:\huabang` 含 baison SDK 原型与大量临时补丁文件,与生产项目结构不同;生产以服务器 `/srv/huabang-ai-center/` 为准。SSH 免密调用:`ssh -o BatchMode=yes xiaohu@100.94.89.49 "<cmd>"`。
