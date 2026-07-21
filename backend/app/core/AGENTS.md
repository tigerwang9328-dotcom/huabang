# backend/app/core — 核心基础设施

<!-- agentmap:generated:start -->
## 范围

后端核心基础设施:配置、异步数据库会话、Redis、JWT 安全、门店/仓库白名单、数据范围、字段权限、标准进价、异常处理、日志。**不负责**:业务 service、ORM 模型定义、HTTP 路由。

## 关键文件

- `config.py` — `Settings(BaseSettings)`,从 `.env` 注入所有配置(DB/Redis/JWT/AI/钉钉/百胜/金蝶/生意经/上传/日志)。`@lru_cache` 单例。
- `database.py` — `create_async_engine`(asyncpg)、`AsyncSessionLocal`、`Base(DeclarativeBase)`、`get_db` 依赖、`check_db_connection`
- `security.py` — bcrypt 密码哈希、JWT access/refresh token 签发与校验
- `store_whitelist.py` — **业务口径核心**:门店/仓库/库存白名单 + 实收支付方式白名单 + SQL IN 字面量生成器
- `data_scope.py` — 用户岗位→可查询数据范围映射(self/store/dept/company/all)
- `field_permissions.py` — 字段级权限(hide/mask/summary/none)
- `standard_purchase_price.py` — 标准进价策略
- `redis.py` — Redis 连接 + `check_redis_connection`(限流降级兜底)
- `exceptions.py` — `AppException` 体系 + 4 个全局 handler
- `logger.py` — structlog/json 日志配置

## 本地状态与失败行为

- DB 连接失败:lifespan 记录 error 但不阻断启动(健康检查会暴露 disconnected)
- Redis 不可用:限流降级,不致命
- 配置缺失:pydantic-settings 启动即抛校验错
- JWT 过期/非法:`decode_token` 返回 None,deps 抛 401

## 公共输入/输出

- `get_db()` → `AsyncGenerator[AsyncSession]`,自动 commit/rollback
- `get_data_scope(db, user)` → `DataScope(scope, store_codes, inventory_codes, role_codes)`
- `apply_field_permissions(db, user, module, data)` → 脱敏后的 data
- `allowed_store_sql_in()` → `('134681','185805',...)` 可直接拼 SQL

## 模块不变量

1. `ALLOWED_STORE_CODES` = 7 个销售门店;`ALLOWED_INVENTORY_CODES` = 7 门店 + `GZ001`/`GZ002`/`GYNG`。销售/收款只走门店白名单,库存走库存白名单。
2. `ACTUAL_PAY_CODES` = `{000,666,971,003,004,011}` 定义实收口径;VIP 卡消费(004)进销售额也进实收,但不进充值;排除礼券(001)/积分(005)。
3. `gz002` 小写必须按 `GZ002` 匹配;维度表保留全量供审计。
4. AppSecret/JWT 密钥/DB 密码绝不进日志、不进请求参数。
5. DB 会话经 `get_db` 注入,自动 commit/rollback;禁止 service 层裸 commit 跨边界。

## 焦点测试/构建命令

```bash
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest tests/test_redis_rate_limit.py tests/test_cost_policy.py tests/test_standard_purchase_price_policy.py -q
```
<!-- agentmap:generated:end -->

## 手动备注

`store_whitelist.py` 是全项目最敏感的业务口径文件之一,改动必须同步审查 ETL `dwd_to_dws` 与所有 baison 同步服务的过滤逻辑,并重建受影响日期的 dws/dm。改 `ACTUAL_PAY_CODES` 必须回填历史 dwd。
