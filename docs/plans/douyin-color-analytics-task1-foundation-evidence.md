# 抖音颜色分析 Task 1 基础设施证据

日期：2026-07-30（Asia/Shanghai）

## 本次范围

- 新模块数据位于独立 PostgreSQL `douyin` schema；没有向 `fin_current`、`fin_history` 或应用账号扩大权限。
- 账号、令牌、采集实例、视频、批次、分片、快照和采集项均显式含 `account_id`；跨账号引用使用复合外键。
- 账号只保存预期创作者的不可逆指纹；不保存原始创作者 ID、Cookie、token 或签名 URL。
- 独立 `huabang_douyin_migrator` 角色只拥有 `douyin` schema；迁移版本表也位于该 schema，与全局 Alembic 链隔离。
- 统一审计写入服务在调用方事务内 `flush` 而不自行提交，递归脱敏敏感键、授权信息和带 query/fragment 的 URL。既有系统和认证审计辅助函数已委托给该服务。
- 权限初始化脚本复用中台 `sys_role`、`sys_permission`、`sys_role_permission`：首期向全部启用角色授予查看、标注和商品维护；导出与账号配置只保留给既有管理员绕过权限。

## 验证

- 红灯：新增基础契约后，模型、统一审计服务及独立迁移资产均不存在，测试失败。
- 绿灯：`pytest tests/test_douyin_color_foundations.py tests/test_douyin_color_analysis_task0_contract_v31.py -q` 为 `16 passed`。
- 静态 SQL：独立 Alembic 链生成 `douyin.alembic_version` 和 8 张业务表，没有 finance schema 引用。
- 真实临时库：`huabang_douyin_task1_verify_20260730` 内成功执行迁移，检查结果为 `tables=9`、schema owner=`huabang_douyin_migrator`、revision=`20260730_01_douyin_color_core`；脚本退出时删除该临时库。
- 回归中发现并修复：`SET ROLE` 开启 SQLAlchemy 隐式事务导致 DDL 在连接关闭时回滚。现在在角色切换后显式提交，再由 Alembic 管理 DDL 事务。
- 生产只读复核：生产 `huabang_ai` 不存在 `douyin` schema，未部署、未迁移、未重启。

## 未完成项

Task 1 尚未完成。穿搭/套内商品模型、完整标注与报告表会按已冻结的 v3.2 穿搭口径在后续模型提交中补齐；本次没有沿用旧的“单件主要衣物”业务模型。
