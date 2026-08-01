<!-- agentmap:generated:start -->
# huabang-ai-center — 项目级 AGENTS.md

<!-- agentmap metadata
schema_version: 1
module_id: __root__
Do not edit inside the managed block by hand; put durable human notes below it.
-->

## 项目定位

华邦 AI 中台：以百胜 E3ERP、钉钉和金蝶历史财务为权威来源，沉淀经营分析、正式财务账簿、任务闭环和管理看板。

## 上下文加载规则

- 处理某个文件或子模块时，先调用 `hierarchical-agents` Skill 的 `context` 路由器，再按 `read_files_in_order` 读取本文件、祖先和目标叶子 `AGENTS.md`。
- 默认只加载“项目 → 一级模块 → 目标叶子模块”这条路径；不要预读无关兄弟模块。
- 只有当改动触及 API、数据模型、任务协议、数据库迁移或跨模块流程时，才扩展读取关系模块的 `AGENTS.md`。
- 冲突优先级：用户当前指令 > 更深层 `AGENTS.md` > 上级 `AGENTS.md`。全局安全与业务不变量不得被静默覆盖。

## 全局业务与架构不变量

- 生产服务器通过 SSH 免密连接 xiaohu@100.94.89.49，生产路径为 /srv/huabang-ai-center；未获明确授权不得重启生产服务。
- 百胜负责销售、商品、库存、会员和采购入库口径；钉钉负责人员、考勤和审批口径；金蝶历史财务只作为财务账簿和历史凭证来源。
- 销售和收款仅统计 7 个销售门店；库存展示统计 7 个销售门店加 GZ001、GZ002、GYNG 三个仓库，gz002 必须按 GZ002 兼容。
- 金蝶源快照和导入证据必须保留；不得写回金蝶、不得伪造科目映射，未确认三表映射时状态保持 pending_mapping。
- 历史金蝶正式数据已导入正式财务账簿：3 个正式账套、339 张凭证、4596 条分录、416 个科目；重复导入必须幂等。
- 正式财务中心复现牧马人结构时，复现交互、权限和会计结构，不复制牧马人专属经营数据或硬编码口径。

## 一级模块索引

| 子模块 | 路径 | 作用 | 代码情况 | 主要关联 |
|---|---|---|---|---|
| [后端服务](backend/AGENTS.md) | `backend` | 提供 FastAPI 接口、ETL/同步、数据仓库模型、权限校验和财务中心写入能力。 | 含子树 307 文件 / 约 56,000 行；生命周期 `active`；波动 `high` | serves→前端应用；deployed-by→部署与运维 |
| [部署与运维](deploy/AGENTS.md) | `deploy` | 维护生产发布、服务器检查、备份和上线辅助脚本。 | 含子树 0 文件 / 0 行；生命周期 `active`；波动 `medium` | deploys→后端服务；deploys→前端应用 |
| [项目文档](docs/AGENTS.md) | `docs` | 保存项目骨架、字段对照、运维说明、提示词、技能和数据补采/验收文档。 | 含子树 0 文件 / 0 行；生命周期 `active`；波动 `medium` | 见子模块文件 |
| [前端应用](frontend/AGENTS.md) | `frontend` | 提供 Vue 3 + Element Plus 单页应用、登录后导航、业务看板和财务中心页面。 | 含子树 114 文件 / 约 24,000 行；生命周期 `active`；波动 `high` | consumes-from→后端服务；deploys←部署与运维 |
| [根脚本](scripts/AGENTS.md) | `scripts` | 存放仓库级辅助脚本，通常用于检查、生成、迁移准备或跨目录维护。 | 含子树 0 文件 / 0 行；生命周期 `active`；波动 `medium` | 见子模块文件 |

## 跨模块修改原则

- 先确认数据和控制流的权威归属，再修改调用方；不得在多个模块或运行时重复实现同一业务口径。
- 公共接口、路由、数据结构、锁语义或任务状态机变化时，必须检查所有生产者、消费者、兼容层和测试。
- 上级文件只保留子模块摘要；实现细节、关键文件和局部约束写入最近的子模块 `AGENTS.md`。
- 代码改动完成后，刷新直接受影响叶子模块；仅在职责、公共边界、生命周期或关系发生变化时更新祖先摘要。

## 项目级验证

- `cd backend && pytest`
- `cd frontend && npm run type-check && npm run build`
<!-- agentmap:generated:end -->

## 人工维护区

- 在此记录不能安全自动生成的业务原因、风险例外、兼容窗口和迁移约束；不得写入凭据或生产敏感数据。
