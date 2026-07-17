# Investment Decision History and DeepSeek Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent investment-decision loop that normalizes LifeData metrics, stores DeepSeek and rule-fallback recommendations, records human execution and outcomes, summarizes environment patterns daily, and exposes the history on `/app/marketing/investment`.

**Architecture:** Keep raw LifeData capture unchanged and add a long-lived normalized fact layer plus decision, recommendation, execution, outcome, and daily-summary tables. Generate advice asynchronously after a complete data period with deterministic guardrails before and after DeepSeek JSON mode; page requests only read stored results. Reuse the existing DeepSeek-compatible client and AI call log, and retain deterministic advice whenever data or model output is unsafe.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, PostgreSQL JSONB, Alembic, APScheduler, Pydantic v2, httpx, pytest, Vue 3, TypeScript, Element Plus, Node test runner, Codex Skill Markdown.

## Global Constraints

- The only business source is sanitized Douyin Laike 生意经 API JSON already accepted by `POST /life-data/ingest`.
- Never read, store, upload, log, or send Cookie, Authorization, session Token, dynamic signature, or signature secret to DeepSeek.
- Store money as integer fen; convert to yuan only in the frontend.
- Keep `exact`, `period_estimate`, and `missing` distinct; never upgrade an estimate to exact.
- Every recommendation must persist `requires_human_confirm=true` and `executed=false`; no endpoint may modify a Douyin campaign, plan, creative, or budget.
- DeepSeek receives normalized facts and evidence IDs, not raw request/response payloads.
- Page refreshes never trigger model calls; identical input hashes never generate duplicate decision runs.
- `ProvinceDistribution` and `CityDistribution` remain separate as `region_province` and `region_city`.
- Historical metrics, recommendations, executions, outcomes, and summaries are not deleted by the 90-day raw-capture cleanup.
- Existing dirty production-tree changes are user-owned; develop in an isolated worktree and do not stage or revert unrelated files.

---

### Task 1: Persistent decision-history schema

**Files:**
- Create: `backend/alembic/versions/2a0f6a7b8c93_investment_decision_history.py`
- Modify: `backend/app/models/life_data.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_investment_decision_models.py`

**Interfaces:**
- Consumes: existing `Base` and PostgreSQL `app` schema.
- Produces: `InvestmentMetricSnapshot`, `InvestmentDecisionRun`, `InvestmentRecommendation`, `InvestmentExecutionRecord`, `InvestmentOutcomeSnapshot`, and `InvestmentEnvironmentSummaryDaily` ORM classes.

- [ ] **Step 1: Write failing model-contract tests**

```python
from app.models.life_data import (
    InvestmentDecisionRun, InvestmentEnvironmentSummaryDaily,
    InvestmentExecutionRecord, InvestmentMetricSnapshot,
    InvestmentOutcomeSnapshot, InvestmentRecommendation,
)

def test_investment_history_tables_and_constraints_exist():
    assert InvestmentMetricSnapshot.__table__.schema == "app"
    assert InvestmentMetricSnapshot.__tablename__ == "investment_metric_snapshot"
    assert {"region_province", "region_city"}.issubset(
        set(InvestmentMetricSnapshot.DIMENSION_TYPES)
    )
    assert InvestmentRecommendation.requires_human_confirm.default.arg is True
    assert InvestmentRecommendation.executed.default.arg is False
    assert InvestmentOutcomeSnapshot.window_hours.type.python_type is int
    assert InvestmentEnvironmentSummaryDaily.__tablename__ == "investment_environment_summary_daily"
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_investment_decision_models.py -q`

Expected: import failure because the six models do not exist.

- [ ] **Step 3: Add the six ORM models and one Alembic migration**

Implement typed core metrics, JSONB evidence/extra fields, timestamps, foreign keys, check constraints for enum-like values, and these idempotency constraints:

```python
UniqueConstraint(
    "account_id", "stat_start", "stat_end", "dimension_type",
    "dimension_key", "input_hash", name="uq_investment_metric_snapshot_input",
)
UniqueConstraint(
    "account_id", "trigger_type", "input_hash",
    name="uq_investment_decision_run_input",
)
UniqueConstraint(
    "execution_record_id", "window_hours",
    name="uq_investment_outcome_window",
)
UniqueConstraint(
    "account_id", "summary_date", "lookback_days", "input_hash",
    name="uq_investment_environment_summary_input",
)
```

Use `299f6a7b8c92` as the migration parent only after the isolated worktree confirms that it is committed there; otherwise use the worktree's actual `alembic heads` result and document the later merge dependency.

- [ ] **Step 4: Verify models and migration**

Run: `cd backend && .venv/bin/pytest tests/test_investment_decision_models.py tests/test_life_data_models.py -q`

Expected: all tests pass.

Run: `cd backend && .venv/bin/alembic upgrade head --sql > /tmp/investment_history.sql`

Expected: SQL renders six `app.investment_*` tables without executing against production.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/alembic/versions/2a0f6a7b8c93_investment_decision_history.py \
  backend/app/models/life_data.py backend/app/models/__init__.py \
  backend/tests/test_investment_decision_models.py
git commit -m "feat: add investment decision history schema"
```

### Task 2: Long-lived metric normalization and regional separation

**Files:**
- Create: `backend/app/services/investment_metric_service.py`
- Create: `backend/scripts/backfill_investment_metrics.py`
- Test: `backend/tests/test_investment_metric_service.py`
- Modify: `backend/app/services/life_data_analysis_service.py`
- Test: `backend/tests/test_life_data_analysis_service.py`

**Interfaces:**
- Consumes: `LifeDataCapture` rows and Task 1 `InvestmentMetricSnapshot`.
- Produces: `normalize_capture(capture) -> list[MetricFact]`, `persist_metric_snapshots(db, account_id, captures) -> list[int]`, and `backfill_account(db, account_id) -> dict[str, int]`.

- [ ] **Step 1: Write failing normalization tests**

```python
def test_region_levels_are_separate(ad_analysis_capture):
    facts = normalize_capture(ad_analysis_capture)
    province = [f for f in facts if f.dimension_type == "region_province"]
    city = [f for f in facts if f.dimension_type == "region_city"]
    assert [(f.dimension_label, f.spend_fen) for f in province] == [("贵州省", 113423)]
    assert [(f.dimension_label, f.spend_fen) for f in city] == [("贵阳市", 113174)]

def test_metric_fact_preserves_fen_period_quality_and_capture_id(home_capture):
    fact = next(f for f in normalize_capture(home_capture) if f.dimension_type == "account")
    assert fact.verified_gmv_fen == 990
    assert fact.stat_end.isoformat() == "2026-07-16"
    assert fact.attribution_quality == "period_estimate"
    assert fact.source_capture_ids == [home_capture.id]
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_investment_metric_service.py -q`

Expected: import failure for `investment_metric_service`.

- [ ] **Step 3: Implement deterministic normalization and idempotent persistence**

Define a frozen `MetricFact` dataclass with typed core metrics. Detect response module paths explicitly:

```python
REGION_MODULES = {
    "ProvinceDistribution": "region_province",
    "CityDistribution": "region_city",
}

def region_facts(response_payload, *, stat_start, stat_end, capture_id):
    for module_name, dimension_type in REGION_MODULES.items():
        for row in rows_below_named_module(response_payload, module_name):
            label_key = "province_resident" if dimension_type == "region_province" else "city_resident"
            label = row.get(label_key)
            if label and valid_fen(row.get("sub_ad_cost")):
                yield MetricFact(
                    dimension_type=dimension_type,
                    dimension_key=str(label), dimension_label=str(label),
                    spend_fen=int(row["sub_ad_cost"]),
                    metrics_extra={"spend_rate": row.get("sub_ad_cost_rate")},
                    source_capture_ids=[capture_id],
                    stat_start=stat_start, stat_end=stat_end,
                    attribution_quality="period_estimate",
                )
```

Use PostgreSQL `ON CONFLICT DO NOTHING` with the Task 1 unique constraint. Keep account, material, age-gender, trend, province, and city facts separate.

- [ ] **Step 4: Change overview regional output without breaking current summary**

Return:

```python
"regions": {
    "province": province_rows,
    "city": city_rows,
    "meaning": "投放触达人群居住地的广告消耗分布",
    "supports_effectiveness_decision": False,
}
```

Do not emit a combined province/city list. Keep account summary, materials, demographics, and trends behavior unchanged.

- [ ] **Step 5: Implement a read-only backfill script**

The script defaults to dry-run and requires `--apply` to write. It reads retained captures in ID batches, calls `persist_metric_snapshots`, reports inserted/duplicate/error counts, and never creates recommendations or execution records.

- [ ] **Step 6: Verify Task 2**

Run: `cd backend && .venv/bin/pytest tests/test_investment_metric_service.py tests/test_life_data_analysis_service.py -q`

Expected: all tests pass, including separate province/city assertions.

- [ ] **Step 7: Commit Task 2**

```bash
git add backend/app/services/investment_metric_service.py \
  backend/app/services/life_data_analysis_service.py \
  backend/scripts/backfill_investment_metrics.py \
  backend/tests/test_investment_metric_service.py \
  backend/tests/test_life_data_analysis_service.py
git commit -m "feat: normalize investment metric history"
```

### Task 3: Guardrailed DeepSeek decision generation and persistence

**Files:**
- Create: `backend/app/services/investment_decision_service.py`
- Create: `backend/app/schemas/investment_decision.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_investment_decision_service.py`

**Interfaces:**
- Consumes: Task 1 decision models, Task 2 metric snapshots, `AIEngine._call_business_advice`.
- Produces: `build_rule_envelope(snapshots) -> RuleEnvelope`, `generate_for_latest_period(db, account_id) -> DecisionResult`, and validated Pydantic `DeepSeekInvestmentPayload`.

- [ ] **Step 1: Write failing guardrail and cache tests**

```python
@pytest.mark.asyncio
async def test_identical_input_hash_returns_cached_run(service, model_spy):
    first = await service.generate_for_latest_period(ACCOUNT_ID)
    second = await service.generate_for_latest_period(ACCOUNT_ID)
    assert first.run_id == second.run_id
    assert model_spy.await_count == 1

@pytest.mark.asyncio
async def test_missing_or_inconsistent_data_blocks_model(service, model_spy):
    result = await service.generate_for_latest_period(ACCOUNT_ID)
    assert result.status == "blocked"
    assert result.recommendations[0].action == "collect_more_data"
    model_spy.assert_not_awaited()

@pytest.mark.asyncio
async def test_invalid_deepseek_budget_falls_back_to_rules(service, model_spy):
    model_spy.return_value = {"content": json.dumps({
        "decision_summary": "加投", "recommendations": [{
            "action": "increase", "target_type": "account", "target_key": ACCOUNT_ID,
            "title": "无限加投", "reasoning": "无证据", "budget_min_fen": 1,
            "budget_max_fen": 999999999, "review_window_hours": 24,
            "stop_loss": "无", "confidence": "high", "evidence_refs": ["missing:1"]
        }], "pattern_observations": [], "data_limitations": []
    }), "model": "deepseek-chat"}
    result = await service.generate_for_latest_period(ACCOUNT_ID)
    assert result.status == "fallback"
    assert result.model_used == "deterministic_rules"
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_investment_decision_service.py -q`

Expected: missing service and schemas.

- [ ] **Step 3: Add dedicated configuration**

```python
INVESTMENT_AI_ENABLED: bool = True
INVESTMENT_AI_MODEL: str = "deepseek-chat"
INVESTMENT_AI_TIMEOUT_SECONDS: int = 45
INVESTMENT_AI_MIN_INTERVAL_MINUTES: int = 60
INVESTMENT_AI_MAX_BUDGET_FEN: int = 30000
```

Document the same non-secret defaults in `.env.example`; continue using `DEEPSEEK_API_KEY` and `DEEPSEEK_BASE_URL`.

- [ ] **Step 4: Implement input hashing, advisory locking, JSON mode, validation, and persistence**

Use prompt/schema versions `investment-decision-v1` and `investment-decision-json-v1`. Hash sorted normalized facts plus model, prompt version, schema version, and rule version. Acquire `pg_advisory_xact_lock` for `account_id + stat_end`. Call:

```python
model_result = await AIEngine(db)._call_business_advice(
    INVESTMENT_SYSTEM_PROMPT,
    json.dumps(model_context, ensure_ascii=False, sort_keys=True),
    max_tokens=2500,
)
payload = DeepSeekInvestmentPayload.model_validate_json(model_result["content"])
validated = enforce_rule_envelope(payload, envelope)
```

Persist one `InvestmentDecisionRun`, child recommendations, and one sanitized `LogAiCall`. On timeout, invalid JSON, fake evidence, confidence escalation, forbidden action, or over-budget output, persist `fallback` plus deterministic recommendations.

- [ ] **Step 5: Verify Task 3**

Run: `cd backend && .venv/bin/pytest tests/test_investment_decision_service.py tests/test_ai_business_advice.py -q`

Expected: all tests pass; no real network calls occur.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/app/services/investment_decision_service.py \
  backend/app/schemas/investment_decision.py backend/app/core/config.py \
  backend/.env.example backend/tests/test_investment_decision_service.py
git commit -m "feat: generate guardrailed DeepSeek investment advice"
```

### Task 4: Decision history, human decision, and execution APIs

**Files:**
- Create: `backend/app/api/v1/investment_decision.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/schemas/investment_decision.py`
- Modify: `backend/app/services/investment_decision_service.py`
- Test: `backend/tests/test_investment_decision_api.py`

**Interfaces:**
- Consumes: Task 3 service and schemas.
- Produces: overview, history, detail, decision registration, execution registration, and daily-pattern read endpoints.

- [ ] **Step 1: Write failing API contract tests**

```python
def test_overview_is_read_only_and_returns_persisted_source(client, service_mock):
    response = client.get("/api/v1/investment-decisions/overview")
    assert response.status_code == 200
    assert response.json()["data"]["recommendation_source"] in {"deepseek", "rules"}
    service_mock.generate_for_latest_period.assert_not_called()

def test_decision_click_does_not_mark_executed(client):
    response = client.post("/api/v1/investment-decisions/12/decision", json={"decision": "accepted"})
    assert response.json()["data"]["executed"] is False

def test_execution_requires_actual_budget(client):
    response = client.post("/api/v1/investment-decisions/12/execution", json={})
    assert response.json()["success"] is False
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_investment_decision_api.py -q`

Expected: route does not exist.

- [ ] **Step 3: Implement authenticated routes**

Use `require_permission("dashboard:overview:view")` for reads and `require_permission("task:edit")` for decision/execution writes. Request literals are `accepted/rejected/partially_accepted/expired`; actual budget is positive integer fen. Execution registration sets the recommendation's `executed=true` only after an `InvestmentExecutionRecord` is committed.

- [ ] **Step 4: Verify Task 4**

Run: `cd backend && .venv/bin/pytest tests/test_investment_decision_api.py tests/test_life_data_api.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/app/api/v1/investment_decision.py backend/app/api/v1/router.py \
  backend/app/schemas/investment_decision.py \
  backend/app/services/investment_decision_service.py \
  backend/tests/test_investment_decision_api.py
git commit -m "feat: expose investment decision history workflow"
```

### Task 5: Outcome windows and daily environment summaries

**Files:**
- Create: `backend/app/jobs/investment_decision_jobs.py`
- Create: `backend/app/services/investment_environment_service.py`
- Modify: `backend/app/jobs/scheduler.py`
- Test: `backend/tests/test_investment_decision_jobs.py`
- Test: `backend/tests/test_investment_environment_service.py`

**Interfaces:**
- Consumes: executions, metric snapshots, decision generator, DeepSeek JSON client.
- Produces: `run_investment_period_generation()`, `capture_due_outcomes()`, `run_daily_investment_summary()`, and `summarize_environment(db, account_id, summary_date, lookback_days)`.

- [ ] **Step 1: Write failing job and summary tests**

```python
@pytest.mark.asyncio
async def test_outcomes_are_idempotent_for_24_72_168_hours(job, db):
    await job.capture_due_outcomes(now=EXECUTED_AT + timedelta(hours=169))
    await job.capture_due_outcomes(now=EXECUTED_AT + timedelta(hours=170))
    rows = await load_outcomes(db)
    assert [row.window_hours for row in rows] == [24, 72, 168]

@pytest.mark.asyncio
async def test_daily_summary_does_not_claim_causality(service):
    result = await service.summarize_environment(ACCOUNT_ID, date(2026, 7, 17), 30)
    assert result.confidence in {"low", "medium"}
    assert "造成" not in json.dumps(result.patterns, ensure_ascii=False)
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_investment_decision_jobs.py tests/test_investment_environment_service.py -q`

Expected: missing job and environment service modules.

- [ ] **Step 3: Implement idempotent jobs with one-process file locks**

Register:

```python
CronTrigger(minute=50, timezone="Asia/Shanghai")  # generate after hourly core collection
CronTrigger(minute="*/15", timezone="Asia/Shanghai")  # due outcome windows
CronTrigger(hour=6, minute=30, timezone="Asia/Shanghai")  # daily 7/30/90 summaries
```

Use non-blocking `/tmp/huabang_investment_*.lock` files to avoid multi-worker duplication, plus database unique constraints as the final idempotency layer.

- [ ] **Step 4: Implement daily DeepSeek summary validation**

Allow only evidence-backed observations, risks, sample size, confidence, and evidence refs. Replace causal verbs with a blocked/fallback response if output claims causality without exact evidence. Missing history returns a deterministic “样本不足” summary without calling DeepSeek.

- [ ] **Step 5: Verify Task 5**

Run: `cd backend && .venv/bin/pytest tests/test_investment_decision_jobs.py tests/test_investment_environment_service.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add backend/app/jobs/investment_decision_jobs.py \
  backend/app/services/investment_environment_service.py \
  backend/app/jobs/scheduler.py \
  backend/tests/test_investment_decision_jobs.py \
  backend/tests/test_investment_environment_service.py
git commit -m "feat: track investment outcomes and daily patterns"
```

### Task 6: Investment page history and meaningful regional UI

**Files:**
- Modify: `frontend/src/api/lifeDataAnalysis.ts`
- Modify: `frontend/src/views/marketing/InvestmentOptimization.vue`
- Modify: `frontend/tests/life-data-investment-page.test.cjs`

**Interfaces:**
- Consumes: Task 4 APIs and separated `regions.province/city` overview payload.
- Produces: persisted latest advice, decision history, human-decision form, execution form, outcome windows, daily patterns, and province/city regional tabs.

- [ ] **Step 1: Write failing source-contract tests**

```javascript
for (const required of [
  'DeepSeek 增强建议', '规则兜底建议', '决策历史', '24小时', '72小时', '7天结果',
  '投放人群地域消耗分布（按居住地）', '省份', '城市',
  '仅代表广告消耗流向，不能单独判断地域效果',
]) assert.equal(source.includes(required), true, `missing: ${required}`)
assert.equal(source.includes('贵阳及周边消耗分布'), false)
```

- [ ] **Step 2: Verify RED**

Run: `cd frontend && node --test tests/life-data-investment-page.test.cjs`

Expected: missing new copy and API methods.

- [ ] **Step 3: Add API methods and refactor page sections**

Expose `getDecisionOverview`, `getDecisionHistory`, `recordDecision`, `recordExecution`, and `getDailyPatterns`. Render recommendation source and generation time. Decision acceptance opens a form; only execution submission with an actual budget marks executed. Render province and city tables independently with top 10 plus “其他”.

- [ ] **Step 4: Verify Task 6**

Run: `cd frontend && node --test tests/life-data-investment-page.test.cjs`

Expected: all tests pass.

Run: `cd frontend && npm run build`

Expected: Vue/TypeScript production build succeeds.

- [ ] **Step 5: Commit Task 6**

```bash
git add frontend/src/api/lifeDataAnalysis.ts \
  frontend/src/views/marketing/InvestmentOptimization.vue \
  frontend/tests/life-data-investment-page.test.cjs
git commit -m "feat: add investment decision history UI"
```

### Task 7: Skill and data-contract upgrade

**Files:**
- Modify outside repo source package: `C:/Users/Administrator/.codex/skills/huabang-douyin-laike-optimizer/SKILL.md`
- Modify outside repo source package: `C:/Users/Administrator/.codex/skills/huabang-douyin-laike-optimizer/references/data-contract.md`
- Create repository mirror: `docs/skills/huabang-douyin-laike-optimizer.md`
- Test: `backend/tests/test_investment_skill_contract.py`

**Interfaces:**
- Consumes: Task 4 APIs, Task 5 summary semantics, Task 6 region meaning.
- Produces: a Skill workflow that reads persisted advice/history, distinguishes model/fallback, and forbids unsupported regional or causal claims.

- [ ] **Step 1: Write failing repository contract test**

```python
def test_investment_skill_contract_documents_history_and_region_semantics():
    text = Path("../docs/skills/huabang-douyin-laike-optimizer.md").read_text("utf-8")
    for required in (
        "investment-decisions/history", "requires_human_confirm: true",
        "region_province", "region_city", "投放触达人群居住地",
        "24/72/168", "DeepSeek", "规则兜底",
    ):
        assert required in text
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && .venv/bin/pytest tests/test_investment_skill_contract.py -q`

Expected: repository mirror does not exist.

- [ ] **Step 3: Update Skill and mirror the approved contract**

The Skill sequence becomes: collector health -> complete period -> persisted recommendation -> decision history/outcomes -> environment summary -> evidence-limited recommendation. It must refuse regional effectiveness claims when only `sub_ad_cost` exists and must never directly execute.

- [ ] **Step 4: Verify Task 7**

Run: `cd backend && .venv/bin/pytest tests/test_investment_skill_contract.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit repository-owned Skill mirror and test**

```bash
git add docs/skills/huabang-douyin-laike-optimizer.md \
  backend/tests/test_investment_skill_contract.py
git commit -m "docs: upgrade investment optimizer skill contract"
```

### Task 8: Full verification, backfill rehearsal, and production handoff

**Files:**
- Modify: `docs/operations/investment-decision-history-runbook.md`
- Modify: `docs/superpowers/plans/2026-07-17-investment-decision-history-deepseek.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified release candidate, dry-run counts, migration/runbook, and explicit production deployment evidence.

- [ ] **Step 1: Run backend focused and full suites**

Run:

```bash
cd backend
.venv/bin/pytest tests/test_investment_decision_models.py \
  tests/test_investment_metric_service.py \
  tests/test_investment_decision_service.py \
  tests/test_investment_decision_api.py \
  tests/test_investment_decision_jobs.py \
  tests/test_investment_environment_service.py \
  tests/test_life_data_analysis_service.py \
  tests/test_life_data_api.py -q
.venv/bin/pytest -q
```

Expected: all focused and full backend tests pass.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
cd frontend
node --test tests/*.test.cjs
npm run build
```

Expected: all frontend tests and the production build pass.

- [ ] **Step 3: Rehearse migration and backfill without production writes**

Run:

```bash
cd backend
.venv/bin/alembic upgrade head --sql > /tmp/investment_history_upgrade.sql
.venv/bin/python scripts/backfill_investment_metrics.py
```

Expected: migration SQL renders; dry-run reports retained capture counts and zero database writes.

- [ ] **Step 4: Write the operational runbook**

Document exact backup, migration, `--apply` backfill, service restart, health checks, rollback, first real decision verification, and 24-hour observation commands. State that production writes require an explicit deployment step after reconciling the dirty production tree.

- [ ] **Step 5: Run mandatory reviews**

Use code review for all changes, Python review for backend changes, TypeScript review for frontend changes, database review for the migration, and security review for DeepSeek input/logging and write endpoints. Resolve every high/medium issue or document a user-approved deferral.

- [ ] **Step 6: Commit the runbook and verified plan status**

```bash
git add docs/operations/investment-decision-history-runbook.md \
  docs/superpowers/plans/2026-07-17-investment-decision-history-deepseek.md
git commit -m "docs: add investment history rollout runbook"
```

- [ ] **Step 7: Production deployment checkpoint**

Before applying the migration, compare the feature worktree with `/srv/huabang-ai-center` dirty changes, integrate without overwriting user-owned work, rerun the full verification, back up the database, then request or rely on explicit deployment authorization. Do not infer production completion from local tests or a successful build.
