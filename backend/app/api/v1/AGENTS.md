# backend/app/api/v1 — HTTP API 层

<!-- agentmap:generated:start -->
## 范围

FastAPI HTTP 路由层,28 个路由模块。负责参数校验、鉴权、依赖注入、调用 service、组装响应。**不负责**:业务逻辑实现(在 services)、ORM 定义(在 models)、外部 API 调用(在 integrations)。

## 入口与关键文件

- `router.py` — 总路由注册,`api_router = APIRouter(prefix="/api/v1")`,include 全部 28 子路由
- `deps.py` — 依赖注入:`get_db` / `get_current_user` / `require_permission` / `get_data_scope`
- `auth.py` — 登录/刷新/token 校验
- 28 路由(按业务域):
  - **系统**:auth、system、audit、rules、acceptance
  - **数据**:sync、etl、baison、dingtalk、dingtalk_finance
  - **经营**:dashboard、report、store、product、inventory、member、hr
  - **财务**:finance、kingdee_finance、finance_center
  - **AI**:ai、ai_assistant、ai_diagnosis、life_data、life_data_analysis、investment_decision
  - **任务**:task、mobile

## 本地状态与失败行为

- 鉴权失败 → 401(未登录)/ 403(无权限),经 `core/exceptions.py` 统一包装
- 参数校验失败 → 422,经 `validation_exception_handler`
- 业务异常 → `AppException` 子类,携带 code/message
- 未捕获异常 → `global_exception_handler` 返回 500,落 `log_error`

## 公共输入/输出

- 入参:路径/查询/体参数,经 Pydantic schema(`app/schemas/`)校验
- 出参:统一 JSON,成功 `{"code":0,"data":...,"msg":"ok"}`,异常由 handler 包装
- 鉴权:`Authorization: Bearer <jwt>`,deps 解析用户与权限

## 消费者/生产者

- **消费**:`backend_core`(deps/config/security/data_scope/field_permissions)、`backend_services`(业务)、`backend_schemas`(校验模型)
- **生产**:对前端 `/api/v1/*`,对 scripts 不可直接调用(走 service)

## 模块不变量

1. 所有路由必须注册在 `router.py`;新增路由在此 include。
2. 受保护接口依赖 `deps.get_current_user` / `require_permission`;匿名接口显式标注。
3. 数据范围经 `core/data_scope.get_data_scope` 限定,不可在路由层绕过白名单。
4. 字段级权限经 `core/field_permissions.apply_field_permissions` 在返回前应用。
5. 路由层不直接操作第三方 API,必须经 service/integration。

## 焦点测试/构建命令

```bash
cd /srv/huabang-ai-center/backend
.venv/bin/python -m pytest tests/test_business_routes_auth.py tests/test_member_api.py tests/test_kingdee_finance_api.py -q
.venv/bin/python -c "from app.api.v1.router import api_router; print(len(api_router.routes))"
```
<!-- agentmap:generated:end -->

## 手动备注

新增业务域时,同步更新 `router.py` include + `seed_module_permissions.py` 权限种子 + 前端 `api/*.ts` 与 `router/index.ts`。
