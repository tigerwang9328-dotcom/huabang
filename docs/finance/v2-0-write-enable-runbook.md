# 华邦财务中心 V2.0：生产开写 Gate 手册

> 本手册只定义 Go/No-Go 和受控操作。它不替代真实数据、财务核对或管理员授权；任何一项未满足时保持 V2 写 Gate 关闭。

## Gate 总表

| Gate | 必须的直接证据 | 未通过时的动作 |
| --- | --- | --- |
| R1 恢复副本 | `016cfd3c1454`、`c82e5a1f9d70`、`e951b2d0a6c4` 在独立恢复库完成 upgrade→downgrade→upgrade，角色核验 ready | 不发布迁移，不重启，不开 Gate |
| R2 备份恢复 | 当日备份、恢复演练、异机/异存储 RPO/RTO 证据 | 最多只读发布，禁止正式开写 |
| R3 权限与只读发布 | `fin_app` 最小权限、已登录财务/超级管理员浏览器验收、历史标记/审计可见 | 不启用 V2 制单 |
| R4 数据与报表 | 最终增量、逐凭证/逐余额核对、最终期初已验证/锁定/批准、正式报表映射已核对 | 不启用 V2 制单 |
| R5 运行保障 | 真实告警通知闭环、非空生产形态性能测量、锁等待/死锁/5xx 和余额差异处置证据 | 不启用审核或过账 |
| R6 切换 | 旧系统冻结成功、旧入口无第二写路径、责任人在线、切换窗口批准 | 保持旧系统写入，V2 Gate 关闭 |

## R1：恢复副本迁移演练

服务器已准备隔离工作树 `/tmp/huabang-finance-v2-rehearsal-20260730`，它与运行目录 `/srv/huabang-ai-center` 分离。数据库目标固定为 `huabang_ai_finance_drill_20260729_r2`，脚本会拒绝生产库名。

由项目管理员在本地终端以交互方式执行：

```powershell
ssh -t xiaohu@100.94.89.49 "bash /tmp/huabang-finance-v2-rehearsal-20260730/deploy/rehearse_finance_v2_migrations.sh --database-name huabang_ai_finance_drill_20260729_r2 --execute"
```

这会要求系统的 sudo 验证一次；不要把密码写入命令、脚本、`.env`、Git 或聊天记录。成功输出必须包含两次角色核验 `status=ready` 和最终 `completed`。失败时停止，不尝试用 `fin_app` 迁移或给应用账号 DDL 权限。

## 允许开写的顺序

1. R1–R6 全部 Go 后，先启用批准试点范围的 `draft_enabled`。
2. 第一日逐笔核对通过后启用 `review_enabled`。
3. 第二次日对账通过、余额与审计无差异后启用 `post_enabled`。
4. 每次启用前记录操作者、理由、账簿/角色范围、时间与回滚点；任何异常立即关闭上级 Gate。

## 紧急停止与回滚边界

- 写 Gate 关闭后，历史 `fin_read` 查询和已过账凭证审计必须继续可读。
- V2 尚无已过账凭证时，可恢复旧系统写入或维持批准冻结窗口；禁止双写。
- V2 出现已过账凭证后，普通发布问题只能前向修复；仅数据库灾难可按已验证备份/PITR 恢复，并补录和核对 RPO 范围内事实。
