# backend — FastAPI 后端

<!-- agentmap:generated:start -->
## 范围

FastAPI 后端单体,位于 `backend/`。提供 HTTP API、业务服务、ETL 管线、第三方集成、APScheduler 调度、SQLAlchemy ORM 模型。**不负责**:前端 Vue 页面、纯 shell 同步脚本(在项目根 `scripts/`)。

## 直接拥有的文件

- `app/main.py` — FastAPI 入口,lifespan 启动 DB/Redis 检查 + APScheduler,注册全局异常处理与 CORS
- `alembic.ini` + `alembic/versions/`(50 个迁移)— schema 演进
- `requirements.txt` — FastAPI 0.115.5 / SQLAlchemy 2.0.36 / asyncpg / APScheduler / dingtalk-stream 等
- `.env` / `.env.example` — 配置(绝不提交 .env)
- `.venv/` — Python 3.12 虚拟环境
- `scripts/` — 一次性运维脚本(导入金蝶、回填指标、种子权限等),非 crontab 调度
- `tests/` — pytest 测试套件(150+ 测试文件)

## 直接子模块摘要

| 子模块 | 路径 | 职责 |
| --- | --- | --- |
| backend_api | `app/api/v1/` | 28 个 HTTP 路由,参数校验+鉴权+调用 service |
| backend_core | `app/core/` | 配置/DB会话/Redis/JWT/白名单/数据范围/字段权限/异常/日志 |
| backend_models | `app/models/` | ORM 模型,按 ods/dim/dwd/dws/dm/fin/kingdee/sys/log/app/ai/life 分层 |
| backend_services | `app/services/` | 30+ 业务 service(报告/指挥台/财务/AI/会员/库存/投流/规则/利润) |
| backend_services_etl | `app/services/etl/` | ETL 管线 ods→dwd→dws→dm(backend_services 的子模块) |
| backend_integrations_baison | `app/integrations/baison/` | 百胜 E3ERP 客户端 + 15 同步服务 |
| backend_modules_dingtalk | `app/modules/dingtalk/` | 钉钉 Stream 独立进程,入站事件消费 |
| backend_jobs | `app/jobs/` | APScheduler 定时任务注册与执行 |

> `app/schemas/`(common/investment_decision/life_data)与 `app/utils/` 体量小,未单列模块,随用随读。

## 模块不变量

1. uvicorn 监听 `127.0.0.1:8000`,由 Nginx 反代 `/api/`;不放公网直连。
2. 所有路由前缀 `/api/v1`,注册在 `app/api/v1/router.py`;鉴权在 `deps.py` + `core/security.py`。
3. PostgreSQL 16(asyncpg),schema 按层划分;DB 会话经 `core/database.get_db` 注入,自动 commit/rollback。
4. Alembic 单一 head;迁移不可回灌生产,变更必须 `alembic upgrade head`。
5. `.env` 绝不提交 Git;密钥由 pydantic-settings 注入,不进日志。

## 公共接口(跨模块契约)

- 对 frontend:所有 HTTP 接口在 `/api/v1/<resource>`,响应统一经 `core/exceptions.py` 的 `app_exception_handler` 包装。
- 对 scripts:`backend/scripts/*.py` 可独立运行(导入金蝶、回填、种子),需 `cd backend && .venv/bin/python -m scripts.xxx`。
- 对 dingtalk-stream 服务:`app.modules.dingtalk.runner` 是独立入口,不走 FastAPI lifespan。

## 本地校验

```bash
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest -q
.venv/bin/alembic heads
.venv/bin/python -c "from app.main import app; print(len(app.routes))"
```
<!-- agentmap:generated:end -->

## 手动备注

后端 uvicorn 当前为手动启停(非 systemd):`.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2`。重启后注意前端 chunk 缓存导致的 404(index.html 需 no-cache)。
