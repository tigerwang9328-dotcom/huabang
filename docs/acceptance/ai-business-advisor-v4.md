# 华邦大模型经营顾问生产验收

验收时间：2026-07-15（北京时间）  
验收业务日：2026-07-14  
生产提交：`24d9b34e2da5bd25f76bed0efe8da5cc9b26c4e6`

## 生产结果

- 公司加七家销售门店、九个模块共 72 个分析单元，全部生成快照。
- 36 个单元通过模型合同校验，36 个单元使用安全模板；失败单元为零。
- 生产模型为 `deepseek-v4-pro`，72 个快照统一使用 `business-advice-v3`。
- 模板回退原因：31 个 `ValueError`、2 个 `JSONDecodeError`、3 个无就绪事实且未调用模型。
- 每日任务已安装为 UTC `22:45`，即北京时间 `06:45`，使用独立 `flock`。

## 事实与安全门禁

| 验收项 | 结果 |
| --- | --- |
| 批次前后确定性日报摘要 | 均为 `1d2c45fee2eceb71a349ec9b4515ff59` |
| 正式任务数 | 批次前后均为 634 |
| 费用不完整上下文中的经营利润字段 | 0 |
| 费用不完整时的确定性盈亏结论 | 0 |
| 非 `deepseek-v4-pro` 模型快照 | 0 |
| 非草稿或无需人工确认的候选行动 | 0 |
| 数据状态 | 65 个 ready，7 个 pending_data |

模型只生成核心摘要、关键发现、候选建议和限制。销售、实收、退货、毛利、库存、会员等确定性值仍由服务端生成，模型文本不得自行写金额、比例、件数或单数。

## 缓存幂等

完成 v3 重建后连续执行两次相同批次：

- 两次均为 72 个 `cached=true`、0 个未缓存单元。
- `log.log_ai_call` 计数两次均保持 162。
- 快照指纹两次均保持 `c636fb47a4423a5120eaa4366df8ce6b`。
- 正式任务数两次均保持 634。

`rules` 和 `tasks` 在进入模板、模型和输入哈希前统一规范排序，数据库返回顺序变化不会触发重复调用；只有人工刷新接口使用 `force=true` 重调。

## 降级与运行状态

- 短暂关闭 `AI_BUSINESS_ADVICE_ENABLED` 后，后端健康检查正常，`/app/report` 与 `/app/ai-diagnosis` 均返回 HTTP 200。
- 验收后已恢复 `AI_BUSINESS_ADVICE_ENABLED=true`。
- 当前 Alembic head 为 `266f6a7b8c9f`，后端健康状态为 database/redis connected。
- 后端全量回归：567 passed，1 skipped。
- 前端回归：136 passed；TypeScript 检查通过；生产构建通过，2,363 modules transformed。
- Skill 回归：12 passed；内部和系统 `quick_validate.py` 均通过。

## 发布与回退资产

- 数据库备份：`/srv/backups/pg/huabang_ai_20260715_101858.sql.gz`
- 前端备份：`/srv/backups/frontend/huabang_frontend_before_ai_20260715_101907`
- 关闭 `AI_BUSINESS_ADVICE_ENABLED` 可立即回到确定性模板，不回滚销售、库存、利润或任务数据。

## 仍需业务补数

- P0：八类费用与现金、员工工号/岗位/门店映射、任务反馈复查、库存 SKU/条码映射、完整入库/盘点/改单历史、LifeData 经营组 403。
- P1：客流与试穿、线上订单级来源、供应商交期和在途采购、预算与应收应付、促销/改价原因、导购排班与订单归属。
- P2：会员触达及同意记录、营销对照实验、竞品价格、天气和区域活动。

外部资料只用于方法与基准，经营结论仍以华邦事实快照为准。DeepSeek 调用使用官方 JSON Output 合同，并在空响应、结构错误或超时时最多重试一次。
