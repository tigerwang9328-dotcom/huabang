# 华邦老板经营指挥台运维手册

适用环境：`/srv/huabang-ai-center`，服务器时区 UTC，业务时区 Asia/Shanghai。

## 每日数据顺序

| 北京时间 | 作业 | 关键日志 |
| --- | --- | --- |
| 02:30 | 百胜商品/门店主档同步 | `logs/sync_master_daily.log` |
| 03:00 | 百胜会员余额同步 | `logs/sync_members_daily.log` |
| 03:15 | 百胜会员充值同步 | `logs/member_deposit_sync.log` |
| 04:00 | 百胜小票、支付与退货同步 | `logs/sync_tickets_daily.log` |
| 05:30 | 百胜外穿衣物库存同步 | `logs/sync_inventory_daily.log` |
| 06:00 | 尺码墙快照 | `logs/size_wall_snapshot.log` |
| 06:30 | 老板经营快照、异常和任务草稿 | `logs/command_center_daily.log` |

库存日内还在北京时间 10:00、12:00、14:00、16:00、18:00、20:00、22:00 刷新。所有同步使用 `flock` 防并发；日报和任务生成必须按业务日及稳定来源键幂等。

## 日常检查

```bash
systemctl is-active huabang-backend.service
curl -fsS http://127.0.0.1:8000/health
tail -n 120 /srv/huabang-ai-center/logs/sync_tickets_daily.log
tail -n 120 /srv/huabang-ai-center/logs/sync_inventory_daily.log
tail -n 120 /srv/huabang-ai-center/logs/sync_members_daily.log
tail -n 160 /srv/huabang-ai-center/logs/command_center_daily.log
```

确认最近一个完整北京时间日周期中：销售、退货、库存、会员均先完成，06:30 日报随后成功；同一业务日只有一份有效日报，异常和任务草稿没有重复。

## 监控与告警

- `scripts/health_check.sh` 可人工检查后端、前端、数据库、Redis、最近同步和备份。
- 任一核心同步连续失败 2 次、最新可信库存超过 4 小时或 06:30 日报未生成时，应按重大数据异常处理，暂停用该指标作经营结论并标记 `stale`。
- 当前钉钉推送开关关闭，健康检查也未加入独立定时告警。因此日志可查不等于自动告警可用；启用告警前，值班人必须在 06:40 和日内库存刷新后人工检查日志。该项未启用前不能在最终验收中标记“自动告警通过”。

## 退货金额排查

退货金额来自百胜支付/退款明细 `baison_pos.refund_amount`，经营快照来源名固定为 `baison_pos.refund_amount`。状态规则：

- 同步已完成且金额为 0：显示 `0` 和 `ready`。
- 同步已完成且有退款：显示真实退货金额和 `ready`。
- 当日退货同步没有完成：保留最近可信值或空值，状态显示 `stale`，不得写“待接入”或强制填 0。

排查顺序：先查小票同步日志，再查 DWD 支付明细，再查 `dm.dm_boss_daily_report.return_amount / return_rate / source_statuses`，最后重新幂等生成该业务日快照。不要直接改日报金额。

## 手工幂等重算

先记录业务日期和当前行数，再使用项目已有脚本按单日重算。执行前确认没有同一 `flock` 作业运行；完成后重复执行一次，确认日报、异常和任务草稿计数不增长。

```bash
cd /srv/huabang-ai-center
/usr/bin/flock -n /tmp/huabang_command_center.lock \
  scripts/generate_boss_command_center_daily.sh
```

## 部署与技术验收

```bash
cd /srv/huabang-ai-center/backend
PYTHONPATH=. .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/alembic upgrade head

cd /srv/huabang-ai-center/frontend
node --test tests/*.test.cjs
npm run type-check
npm run build
```

部署后检查服务、健康接口、经营总览、日报、门店、商品、库存、会员、异常、任务、AI 和移动接口。桌面与移动截图不得出现空白主区、横向溢出或导航死链。

## 数据库迁移回滚

1. 记录当前 revision、数据库备份位置及关键业务表计数。
2. 只在已确认最新迁移的 `downgrade()` 不删除业务历史时执行一步回滚。
3. 执行 `alembic downgrade -1`，核对关键计数，再执行 `alembic upgrade head`。
4. 最终 `alembic current` 必须恢复到唯一 `head`。
5. 回滚失败立即停止写作业并从备份恢复；不得连续盲目降级。

## 前端版本回滚

1. 发布前保存当前 `frontend/dist` 的带时间戳副本，并记录 Git commit。
2. 新版本发布后抽查主要路由和静态资源。
3. 如需回滚，用同一服务器上的上一份 `dist` 原子替换当前目录，重载 Web 服务并复查路由。
4. 回滚演练只验证版本切换与恢复，不修改后端数据。

## 故障处置原则

- AI、通知或移动端故障不得阻断基础经营快照、日报、规则和任务数据。
- 缺失值不显示为零，预估值不显示为真实，费用不全不判断经营利润。
- 同步失败时保留最近可信值并标记 `stale`，恢复后按业务日幂等补算。
- 每阶段发布后至少观察一个完整北京时间日周期，再认定定时同步、06:30 日报和任务去重稳定。
