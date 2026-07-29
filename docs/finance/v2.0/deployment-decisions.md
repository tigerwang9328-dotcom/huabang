# 华邦财务中心 V2.0：已授权的实施决策

> 决策日期：2026-07-29（北京时间）  
> 决策状态：**实施基线已确定；尚未在生产执行。**

本文件仅记录用户在本会话明确授予实施方的决策权，不把本地代码、备份清单或设计结论描述为已生产验证。

## 1. 数据库角色与最小权限

采用以下 PostgreSQL 拓扑；角色密码、数据库名和连接串不入库，必须由已批准的秘密管理通道单独注入。

| 角色 | 登录 | 用途 | 可访问范围 | 明确禁止 |
| --- | --- | --- | --- | --- |
| `fin_schema_owner` | 否 | V2 schema/对象唯一 owner | `fin_current`、`fin_history`、`fin_read` 的 owner | 业务登录、应用运行 |
| `fin_migrator` | 是 | 一次性 Alembic 发布账户；通过 `SET ROLE fin_schema_owner` 运行 | 仅发布窗口内的 DDL | 业务 API、长期服务、超级权限 |
| `fin_app` | 是 | 华邦后端运行账户 | `fin_current` DML、`fin_read` SELECT | `fin_history` 任意表写、schema owner、DDL、BYPASSRLS |
| `fin_history_importer` | 是 | 一次性金蝶历史导入账户 | `fin_history` 受导入状态机/不可变触发器约束的 DML、`fin_read` SELECT | `fin_current` DML、schema owner、DDL、BYPASSRLS |
| `fin_readonly_auditor` | 是 | 审计/核对只读账户 | `fin_read` SELECT | 两个事实 schema 的写、DDL、BYPASSRLS |

执行资产：`backend/scripts/bootstrap_finance_database_roles.sql`。它必须由 PostgreSQL 数据库管理员在已确认备份后执行；脚本不含密码、不会修改 `.env`、不会自动切换生产服务账号。完成后以 `backend/scripts/verify_finance_database_roles.py` 做只读 Go/No-Go 验证。

## 2. 历史金蝶数据

确定的候选源为本地只读迁移快照：

`D:\huabang\invest_kingdee\results\K3MIG_20260717_172928`

该目录含 `manifest.json`、账套备份和逐表压缩导出及 SHA-256。使用顺序固定为：复制到受控导入工作区 → 清单/哈希校验 → 仅加载 `fin_history.staging_voucher` → 校验 → 发布 → 通过 `fin_read` 只读呈现。不得恢复到生产业务库，不得写回金蝶 ODS/DWD，不得用 `ON CONFLICT DO UPDATE` 覆盖历史事实。

## 3. 会计政策签字例外

用户已明确要求忽略“财务负责人会计政策签字”。该授权仅解除**形式签字**这一技术发布前置项；它不构成对法人、账套、币种、期间、科目、期初、报表映射或法定报表的事实确认。

因此，V2 可继续完成技术实现、历史数据校验与只读发布准备；任何缺少可核对事实依据的科目映射、期初余额、正式报表和当前账开写仍保持 No-Go，不能以本例外替代数据证据。

## 4. 期边切换窗口与旧系统冻结责任

默认采用**期边切换**，不采用月中迁移：在旧系统完成当期结账、最终增量已导出并经逐凭证/逐余额核对后，于下一会计期间首日北京时间 00:30–04:30 执行。服务器使用 UTC，执行记录必须同时写明 UTC 时刻（前一日 16:30–20:30）。

| 责任角色 | 默认负责人 | 不可委托的动作 |
| --- | --- | --- |
| 切换总指挥 | 华邦超级管理员 | 宣布开始/中止、记录 Go/No-Go、批准恢复旧系统写入 |
| 旧系统冻结执行人 | 华邦超级管理员 | 关闭旧制单、审核、过账入口；保留只读查询 |
| 财务操作人 | 财务人员或超级管理员 | 最终余额核对、V2 首张草稿、审核、人工过账 |
| 数据库发布执行人 | 受控 `fin_migrator` 账户的持有人 | 迁移、角色校验、备份/恢复探针；不做业务审核或过账 |

**硬性中止条件：** 旧系统仍有写入口、最终增量未完整、任一余额/凭证核对差异未解释、角色校验非 ready、备份恢复演练未通过、V2 Gate 状态不符合阶段要求、任一责任角色未在线。发生任一条件，保持 V2 写 Gate 关闭并恢复旧系统写入；不得双写或重叠记账。
