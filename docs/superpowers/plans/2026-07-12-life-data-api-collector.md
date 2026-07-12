# 生意经油猴 API 采集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 由油猴在已登录的生意经页面内主动调用业务 API，把不含 Cookie 的业务 JSON 上传华邦 AI 中台，保存视频/经营快照并对自然播放首次达到 2,000 的视频创建一次人工确认待办。

**Architecture:** 油猴从页面真实 XHR 学习三个非 Cookie 业务头和成功请求模板，以 100 条分页轮询视频接口，并把业务响应通过写入专用令牌上传。FastAPI 接口校验令牌与主体，原样留档后标准化视频快照，利用数据库唯一约束幂等创建阈值事件和现有 `AppActionTask` 草稿。

**Tech Stack:** Tampermonkey userscript、JavaScript/Node.js 20 `node:test`、FastAPI、Pydantic 2、SQLAlchemy 2、PostgreSQL、Alembic、pytest。

## Global Constraints

- Cookie、Authorization、完整请求头、站内消息和平台风控日志不得离开浏览器。
- 主体固定为 `1798826701211732`，对应 life account `7319301636050913280`。
- 视频每 5 分钟采集，其他成功模板每 30 分钟重放；同一浏览器只允许一个主标签轮询。
- 生意经数据最大日期为昨日；提醒含义是平台数据更新且采集页面在线后立即发现。
- 播放达到或超过 2,000 只产生一次 `draft` 待办，不自动投放、不设置截止日期。
- 保留生产目录现有脏改动；所有实现先在独立 worktree 完成并测试。
- 新迁移 revision 为 `f1b2c3d4e5f6`，`down_revision = "f0a1b2c3d4e5"`，不得修改并行工作的 `f0a1b2c3d4e5_store_targets.py`。

---

### Task 1: 数据模型与迁移

**Files:**
- Create: `backend/app/models/life_data.py`
- Create: `backend/alembic/versions/f1b2c3d4e5f6_life_data_collector.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_life_data_models.py`

**Interfaces:**
- Produces: `LifeDataCapture`, `LifeDataVideoSnapshot`, `LifeDataAlertEvent`, `LifeDataCollectorState` SQLAlchemy 模型。
- Produces: 唯一键 `event_id`、`(account_id,item_id,metrics_hash)`、`(account_id,item_id,rule_code)`。

- [ ] **Step 1: 写失败的模型测试**

```python
from app.models.life_data import (
    LifeDataAlertEvent, LifeDataCapture, LifeDataCollectorState,
    LifeDataVideoSnapshot,
)

def test_life_data_tables_and_uniques():
    assert LifeDataCapture.__table__.fullname == "app.life_data_capture"
    assert LifeDataVideoSnapshot.__table__.fullname == "app.life_data_video_snapshot"
    assert LifeDataAlertEvent.__table__.fullname == "app.life_data_alert_event"
    assert LifeDataCollectorState.__table__.fullname == "app.life_data_collector_state"
    unique_sets = {
        tuple(c.name for c in constraint.columns)
        for constraint in LifeDataAlertEvent.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("account_id", "item_id", "rule_code") in unique_sets
```

- [ ] **Step 2: 运行测试确认因模块缺失而失败**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_models.py -q`
Expected: FAIL with `ModuleNotFoundError: app.models.life_data`.

- [ ] **Step 3: 实现四张表和模型导出**

核心字段固定如下：

```python
class LifeDataCapture(Base):
    __tablename__ = "life_data_capture"
    __table_args__ = (UniqueConstraint("event_id"), {"schema": "app"})
    id = Column(BigInteger, primary_key=True)
    event_id = Column(String(64), nullable=False)
    account_id = Column(String(32), nullable=False, index=True)
    page_path = Column(String(256), nullable=False)
    endpoint = Column(String(256), nullable=False)
    request_payload = Column(JSON, nullable=False)
    response_payload = Column(JSON, nullable=False)
    response_hash = Column(String(64), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class LifeDataVideoSnapshot(Base):
    __tablename__ = "life_data_video_snapshot"
    __table_args__ = (
        UniqueConstraint("account_id", "item_id", "metrics_hash"),
        {"schema": "app"},
    )
    id = Column(BigInteger, primary_key=True)
    account_id = Column(String(32), nullable=False, index=True)
    item_id = Column(String(96), nullable=False, index=True)
    title = Column(Text, nullable=False)
    author_id = Column(String(64))
    author_name = Column(String(128))
    published_at = Column(DateTime(timezone=True))
    stat_start = Column(Date, nullable=False)
    stat_end = Column(Date, nullable=False)
    play_count = Column(BigInteger, nullable=False, default=0)
    pay_gmv_fen = Column(BigInteger, nullable=False, default=0)
    verify_gmv_fen = Column(BigInteger, nullable=False, default=0)
    refund_gmv_fen = Column(BigInteger, nullable=False, default=0)
    metrics_hash = Column(String(64), nullable=False)
    metrics = Column(JSON, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
```

迁移用 `CREATE TABLE IF NOT EXISTS`、明确索引和唯一约束，`downgrade()` 只删除这四张表。

- [ ] **Step 4: 运行模型测试和 Alembic 语法检查**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_models.py -q && .venv/bin/python -m py_compile alembic/versions/f1b2c3d4e5f6_life_data_collector.py`
Expected: PASS.

- [ ] **Step 5: 提交模型任务**

```bash
git add backend/app/models/life_data.py backend/app/models/__init__.py backend/alembic/versions/f1b2c3d4e5f6_life_data_collector.py backend/tests/test_life_data_models.py
git commit -m "feat: add life data collector schema"
```

### Task 2: 视频解析、快照和阈值任务服务

**Files:**
- Create: `backend/app/services/life_data_service.py`
- Create: `backend/tests/fixtures/life_data_video_response.json`
- Create: `backend/tests/test_life_data_service.py`

**Interfaces:**
- Produces: `extract_video_rows(response: dict) -> list[dict]`。
- Produces: `normalize_video(row: dict, stat_start: date, stat_end: date, captured_at: datetime) -> NormalizedVideo`。
- Produces: `LifeDataIngestService.ingest(db, body) -> IngestResult`。

- [ ] **Step 1: 写解析和阈值失败测试**

```python
def test_extract_and_normalize_video_fixture():
    rows = extract_video_rows(load_fixture())
    video = normalize_video(rows[0], date(2026, 7, 5), date(2026, 7, 11), captured_at)
    assert video.item_id == "video-over-2000"
    assert video.play_count == 34310
    assert video.pay_gmv_fen == 4500
    assert video.verify_gmv_fen == 0
    assert video.metrics["play_5s_rate"] == 0.49048197

def test_threshold_is_inclusive_and_once():
    assert should_create_alert(play_count=2000, existing_alert=False) is True
    assert should_create_alert(play_count=1999, existing_alert=False) is False
    assert should_create_alert(play_count=34310, existing_alert=True) is False
```

- [ ] **Step 2: 运行测试确认函数缺失**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_service.py -q`
Expected: FAIL on missing parser/service symbols.

- [ ] **Step 3: 实现纯解析函数**

递归寻找任何 `itemRank.data`，只接受含 `item_id` 与 `item_play_cnt` 的字典。金额保持“分”，`metrics_hash` 对排序后的标准化 metrics JSON 做 SHA-256。解析 `item_create_ts` 时使用 Asia/Shanghai 并转 UTC 保存。

```python
@dataclass(frozen=True)
class NormalizedVideo:
    item_id: str
    title: str
    author_id: str | None
    author_name: str | None
    published_at: datetime | None
    play_count: int
    pay_gmv_fen: int
    verify_gmv_fen: int
    refund_gmv_fen: int
    metrics_hash: str
    metrics: dict[str, Any]
```

- [ ] **Step 4: 实现事务服务**

使用 PostgreSQL `insert(...).on_conflict_do_nothing().returning(...)`：

1. 插入 `LifeDataCapture`，重复 `event_id` 直接返回 duplicate。
2. 每条视频按 metrics hash 插入快照，无变化不新增。
3. 播放大于等于 2,000 时插入唯一 `LifeDataAlertEvent(rule_code="natural_play_2000")`。
4. 仅当 alert insert 返回新 id 时新增 `AppActionTask`，`status="draft"`、`priority=8`、`risk_level="medium"`、`source_type="life_data_rule"`、`requires_human_confirm=True`、`due_date=None`。
5. 待办证据记录播放、5秒率、完播、互动、成交、核销、退款、统计周期和视频信息。

- [ ] **Step 5: 用 fake async session 验证重复上传和一次提醒**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_service.py -q`
Expected: PASS, including duplicate event, unchanged metrics and one-task assertions.

- [ ] **Step 6: 提交服务任务**

```bash
git add backend/app/services/life_data_service.py backend/tests/fixtures/life_data_video_response.json backend/tests/test_life_data_service.py
git commit -m "feat: normalize life data video metrics"
```

### Task 3: 只写采集 API 与鉴权

**Files:**
- Create: `backend/app/schemas/life_data.py`
- Create: `backend/app/api/v1/life_data.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_life_data_api.py`

**Interfaces:**
- Consumes: `LifeDataIngestService.ingest(db, body)`。
- Produces: `POST /api/v1/life-data/ingest`。
- Produces response data: `duplicate`, `videos_seen`, `snapshots_created`, `tasks_created`。

- [ ] **Step 1: 写 API 鉴权和输入限制失败测试**

```python
def test_ingest_rejects_missing_token(client):
    assert client.post("/api/v1/life-data/ingest", json=payload()).status_code == 401

def test_ingest_rejects_wrong_account(client, valid_token):
    body = payload(account_id="wrong")
    response = client.post(PATH, json=body, headers={"X-Collector-Token": valid_token})
    assert response.status_code == 403

def test_ingest_accepts_valid_business_json(client, valid_token):
    response = client.post(PATH, json=payload(), headers={"X-Collector-Token": valid_token})
    assert response.status_code == 200
    assert response.json()["data"]["videos_seen"] == 1
```

- [ ] **Step 2: 运行测试确认路由不存在**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_api.py -q`
Expected: FAIL with 404.

- [ ] **Step 3: 添加设置和 Pydantic schema**

```python
LIFE_DATA_COLLECTOR_TOKEN_SHA256: str = ""
LIFE_DATA_ACCOUNT_ID: str = "1798826701211732"
LIFE_DATA_TASK_CREATOR_ID: int = 1
LIFE_DATA_MAX_PAYLOAD_BYTES: int = 2_000_000
```

Schema 禁止额外字段；`event_id` 长度 16..64，endpoint 必须是 `/api/dito/query` 或 `/api/lowcode_api/query`，request/response 必须是 JSON object。

- [ ] **Step 4: 实现常量时间令牌校验和路由**

```python
digest = hashlib.sha256(x_collector_token.encode()).hexdigest()
if not settings.LIFE_DATA_COLLECTOR_TOKEN_SHA256:
    raise HTTPException(status_code=503, detail="采集令牌未配置")
if not hmac.compare_digest(digest, settings.LIFE_DATA_COLLECTOR_TOKEN_SHA256):
    raise HTTPException(status_code=401, detail="采集令牌无效")
```

序列化业务 body 后检查 2,000,000 bytes；账号不匹配返回 403。任何日志只记录 event_id、账号、endpoint 和计数。

- [ ] **Step 5: 运行 API 与现有匿名路由测试**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_api.py tests/test_business_routes_auth.py -q`
Expected: PASS.

- [ ] **Step 6: 提交 API 任务**

```bash
git add backend/app/schemas/life_data.py backend/app/api/v1/life_data.py backend/app/api/v1/router.py backend/app/core/config.py backend/tests/test_life_data_api.py
git commit -m "feat: add life data ingest endpoint"
```

### Task 4: 油猴主动 API 采集器

**Files:**
- Create: `frontend/public/life-data-collector.user.js`
- Create: `frontend/tests/life-data-collector.test.cjs`

**Interfaces:**
- Consumes: 生意经 `POST /api/dito/query` 和 AI 中台 `POST https://hbreare.com/api/v1/life-data/ingest`。
- Produces: `buildVideoRequest(template, offset, limit)`、`extractItemRank(response)`、`isAllowedEndpoint(url)` 可测试纯函数。

- [ ] **Step 1: 写 Node 失败测试**

```javascript
test('builds 100-row video pages without mutating template', () => {
  const result = core.buildVideoRequest(template, 100, 100)
  assert.equal(result.biz_params.module_params.ItemRank.offset, 100)
  assert.equal(result.biz_params.module_params.ItemRank.limit, 100)
  assert.equal(template.biz_params.module_params.ItemRank.offset, 0)
})

test('allows business endpoints and blocks messages/logs', () => {
  assert.equal(core.isAllowedEndpoint('https://www.life-data.cn/api/dito/query'), true)
  assert.equal(core.isAllowedEndpoint('https://www.life-data.cn/api/msg/query'), false)
  assert.equal(core.isAllowedEndpoint('https://dypay.douyin.com/addone/alert/api/log_info/batch'), false)
})
```

- [ ] **Step 2: 运行 Node 测试确认脚本缺失**

Run: `node --test frontend/tests/life-data-collector.test.cjs`
Expected: FAIL with module not found.

- [ ] **Step 3: 实现单文件 userscript 元数据和纯函数**

元数据必须包含：

```javascript
// @match        https://www.life-data.cn/*
// @run-at       document-start
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @connect      hbreare.com
```

Node 环境通过 `module.exports` 导出纯函数；浏览器环境才执行 `main()`。

- [ ] **Step 4: 实现请求学习、主标签和主动轮询**

- 包装 XHR `open/setRequestHeader/send`，只保存三个非 Cookie 业务头、允许的 endpoint、请求 JSON 和成功响应 JSON。
- 观察到视频成功模板后立即采集 offset 0，每批 100；读取 `itemRank.total` 后采集 offset 100、200...。
- 用 `GM_setValue("lifeDataLeader", {tabId, expiresAt})` 做 30 秒租约，只有主标签运行定时器。
- 视频定时器 300,000 ms；其他模板 1,800,000 ms；API 非 0、账号不符或未捕获模板时显示错误，不上传零值。

- [ ] **Step 5: 实现上传、离线队列和浮层**

- 首次运行 `prompt()` 输入写入令牌；令牌仅存 Tampermonkey 私有存储且不进入 payload/log。
- payload 用 `crypto.randomUUID()` 生成 event_id，仅包含白名单业务 JSON。
- `GM_xmlhttpRequest` 超时 20 秒；失败队列最多 100 个事件，指数退避 30 秒、2 分钟、10 分钟、30 分钟。
- 浮层显示账号、最近采集/上传、视频数、队列数、错误和“立即采集”；支持最小化。

- [ ] **Step 6: 运行 userscript 测试**

Run: `node --test frontend/tests/life-data-collector.test.cjs`
Expected: PASS for pagination, filters, itemRank extraction, leader lease and queue bounds.

- [ ] **Step 7: 提交 userscript**

```bash
git add frontend/public/life-data-collector.user.js frontend/tests/life-data-collector.test.cjs
git commit -m "feat: add life data Tampermonkey collector"
```

### Task 5: 安装文档、全量测试与部署

**Files:**
- Create: `docs/life-data-collector-install.md`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces install URL: `https://hbreare.com/life-data-collector.user.js`。
- Produces operational checks for collector status and threshold task.

- [ ] **Step 1: 写安装与故障恢复文档**

文档包含 Tampermonkey 安装、脚本 URL、一次性输入令牌、保持一个生意经标签在线、浮层状态解释、登录失效恢复、令牌轮换和卸载步骤。明确浏览器关闭时无法采集，重新打开后只补平台仍可查询的数据。

- [ ] **Step 2: 更新 `.env.example`**

只加入哈希和固定账号配置，不写真实令牌：

```dotenv
LIFE_DATA_COLLECTOR_TOKEN_SHA256=
LIFE_DATA_ACCOUNT_ID=1798826701211732
LIFE_DATA_TASK_CREATOR_ID=1
LIFE_DATA_MAX_PAYLOAD_BYTES=2000000
```

- [ ] **Step 3: 运行完整验证**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_models.py tests/test_life_data_service.py tests/test_life_data_api.py tests/test_business_routes_auth.py -q`
Expected: all PASS.

Run: `node --test frontend/tests/life-data-collector.test.cjs && cd frontend && npm run build`
Expected: Node tests PASS and Vite build exits 0.

- [ ] **Step 4: 代码审查并修复发现**

检查敏感字段过滤、金额单位、唯一约束、并发、重传、任务证据、页面资源占用和现有路由兼容；任何修复后重复 Step 3。

- [ ] **Step 5: 提交文档**

```bash
git add docs/life-data-collector-install.md backend/.env.example
git commit -m "docs: add life data collector operations"
```

- [ ] **Step 6: 部署到生产目录**

1. 备份将覆盖的文件和数据库。
2. 将实现 commits 合并/拣选到 `/srv/huabang-ai-center`，不暂存原有脏文件。
3. 生成 32-byte URL-safe token；`.env` 只写 SHA-256，原始 token 只交付一次。
4. `cd backend && .venv/bin/alembic upgrade f1b2c3d4e5f6`。
5. `cd frontend && npm run build`，按现有部署流程发布静态文件。
6. 重启 `huabang-backend.service`，检查 `/health` 和日志无异常。

- [ ] **Step 7: 真实账号验收**

1. 安装 userscript，输入一次性令牌并打开视频分析页。
2. 确认浮层显示主体正确、两批共 114 条视频、上传成功、队列为 0。
3. 数据库查询确认 114 个 `item_id` 入库且原始 JSON 不含 `cookie`/`authorization`。
4. 确认 34,310 播放的视频产生且只产生一个 `life_data_rule` 草稿待办。
5. 再次立即采集，确认无重复 alert/task；核销金额字段保持“分”存储、页面展示换算为元。
