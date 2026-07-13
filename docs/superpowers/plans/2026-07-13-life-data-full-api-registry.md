# LifeData Full API Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the installed Tampermonkey collector into a grouped, deduplicated API registry that replays all learned LifeData business modules from any open authenticated LifeData tab and reports completeness to the AI center.

**Architecture:** Keep browser credentials inside the existing userscript. Add pure registry/classification helpers to the userscript, migrate learned templates in place, run video/business/advertising/other groups on separate schedules, and upload sanitized business JSON through the existing ingest API. Extend collector status with bounded group health so the backend can persist freshness and create one deduplicated human-review task when required groups become stale.

**Tech Stack:** Tampermonkey userscript, browser Fetch/XHR, Node.js built-in test runner, Vue 3/Element Plus panel host, FastAPI, Pydantic v2, SQLAlchemy async, PostgreSQL, Alembic, pytest.

## Global Constraints

- Page DOM is never the source of business metrics; pages only teach successful API request templates.
- Cookie, Authorization, session headers, and browser storage never leave the browser.
- Browser collection requires any authenticated `life-data.cn` tab to remain open; it must not require the source page to remain active.
- Video runs every 5 minutes; business, advertising, and other groups run every 30 minutes.
- Phase one gives advice and draft tasks only; it never creates or changes an advertising campaign.
- Actual verified GMV is the final business outcome; attributed advertising data and same-period account data must remain distinguishable.

---

### Task 1: Pure template registry and classification

**Files:**
- Modify: `frontend/public/life-data-collector.user.js`
- Modify: `frontend/tests/life-data-collector.test.cjs`

**Interfaces:**
- Produces: `templateFingerprint(template): string`, `classifyTemplate(template): 'video'|'business'|'advertising'|'other'`, `hasMeaningfulBusinessData(response, group): boolean`, `mergeTemplateRegistry(current, learned, now): object`.
- Consumes: existing `requestPagePath`, `moduleIdentity`, `deepCloneJson`, and CommonJS export block.

- [ ] **Step 1: Write failing registry tests**

Add tests proving that advertising first-render and refresh copies deduplicate, dates and pagination do not affect identity, `/dito/pc/ad/analysis` classifies as `advertising`, `/dito/pc/business/page` as `business`, video as `video`, and explain-only responses are rejected.

```js
test('deduplicates volatile advertising request variants', () => {
  const a = fixtureAdTemplate({ start_date: '2026-07-06', offset: 0 })
  const b = fixtureAdTemplate({ start_date: '2026-07-07', offset: 100 })
  assert.equal(core.templateFingerprint(a), core.templateFingerprint(b))
  assert.equal(core.classifyTemplate(a), 'advertising')
})

test('rejects explain-only advertising responses', () => {
  assert.equal(core.hasMeaningfulBusinessData({ code: 0, data: { explain: [] } }, 'advertising'), false)
  assert.equal(core.hasMeaningfulBusinessData(adCostFixture, 'advertising'), true)
})
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd frontend && node --test tests/life-data-collector.test.cjs`

Expected: FAIL because the four registry helpers are not exported.

- [ ] **Step 3: Implement deterministic registry helpers**

Normalize a cloned request by removing `start_date`, `end_date`, `date_type`, `offset`, `limit`, cursors, and Dito event-only refresh noise before stable key sorting and hashing. Classify by business path. Meaningful advertising data must include one of `total_ad_cost`, `current_ad_cost`, `ad_pay_gmv`, or `total_ad_pay_gmv`; meaningful business data must include `verify_gmv`, `pay_gmv`, or `refund_gmv`; video must contain valid `ItemRank`.

- [ ] **Step 4: Run focused tests**

Run: `cd frontend && node --test tests/life-data-collector.test.cjs`

Expected: all collector core tests PASS.

- [ ] **Step 5: Commit registry core**

```bash
git add frontend/public/life-data-collector.user.js frontend/tests/life-data-collector.test.cjs
git commit -m "feat: add life data api template registry"
```

### Task 2: Registry migration and complete template learning

**Files:**
- Modify: `frontend/public/life-data-collector.user.js`
- Modify: `frontend/tests/life-data-collector-runtime.test.cjs`

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: persisted registry schema `lifeDataTemplateRegistryV2` with `{schemaVersion, templates}`, and `learnTemplate(record, response, learnedAt)`.

- [ ] **Step 1: Write failing runtime tests**

Cover migration from `lifeDataTemplates`, successful Fetch and XHR learning, replacement of an older structurally equivalent template, preservation of the last valid template when an empty response arrives, and a maximum of 80 templates.

```js
assert.equal(saved.schemaVersion, 2)
assert.equal(Object.keys(saved.templates).length, 1)
assert.equal(Object.values(saved.templates)[0].group, 'advertising')
assert.equal(Object.values(saved.templates)[0].lastLearnedAt, nowIso)
```

- [ ] **Step 2: Run the runtime test and confirm failure**

Run: `cd frontend && node --test tests/life-data-collector-runtime.test.cjs`

Expected: FAIL because registry v2 and `learnTemplate` do not exist.

- [ ] **Step 3: Implement migration and bounded learning**

Migrate once on startup, retain the newest valid template per fingerprint, and evict invalid/oldest `other` templates before required groups. Never persist response bodies in the browser registry; persist only request, endpoint, group, timestamps, summary field names, and failure counters.

- [ ] **Step 4: Verify runtime and core suites**

Run: `cd frontend && node --test tests/life-data-collector.test.cjs tests/life-data-collector-runtime.test.cjs`

Expected: both suites PASS and no credential appears in serialized registry assertions.

- [ ] **Step 5: Commit learning integration**

```bash
git add frontend/public/life-data-collector.user.js frontend/tests/life-data-collector-runtime.test.cjs
git commit -m "feat: persist complete life data api registry"
```

### Task 3: Group scheduler and full manual collection

**Files:**
- Modify: `frontend/public/life-data-collector.user.js`
- Modify: `frontend/tests/life-data-collector.test.cjs`
- Modify: `frontend/tests/life-data-collector-runtime.test.cjs`

**Interfaces:**
- Produces: `runCollectionGroup(group, reason): Promise<GroupRunResult>`, `runFullCollection(reason): Promise<FullRunResult>`, with result `{group, attempted, succeeded, failed, queued, completedAt, errors}`.
- Consumes: Task 2 registry, existing `replayLifeData`, `publishCapture`, `collectVideo`, queue, and leader lock.

- [ ] **Step 1: Add failing scheduler tests**

Test that video uses the newest video template with complete pagination, advertising replays every distinct valid advertising fingerprint, one failure does not stop sibling templates, scheduled runs skip a busy lock, and manual full collection executes all four groups sequentially.

```js
assert.deepEqual(result.groups.map((item) => item.group), [
  'video', 'business', 'advertising', 'other',
])
assert.equal(result.failed, 1)
assert.equal(result.succeeded, 6)
```

- [ ] **Step 2: Run and confirm scheduler failures**

Run: `cd frontend && node --test tests/life-data-collector*.test.cjs`

Expected: FAIL because grouped collection functions are missing.

- [ ] **Step 3: Implement grouped replay**

Replace `replayOtherTemplates` with group runs. Refresh relative dates immediately before each request. Keep video pagination validation. For non-video pagination, only paginate when a recognized request module contains numeric `offset/limit` and the matching response exposes numeric `total`; cap a single template at 100 pages and surface a completeness error at the cap.

- [ ] **Step 4: Wire schedules and manual action**

Keep `VIDEO_INTERVAL = 300_000`; run `business`, `advertising`, and `other` every `1_800_000`. Change both the panel button and Tampermonkey menu command to `runFullCollection('manual')`. Do not start overlapping runs.

- [ ] **Step 5: Run all userscript tests**

Run: `cd frontend && node --test tests/life-data-collector.test.cjs tests/life-data-collector-runtime.test.cjs`

Expected: PASS with full collection order and failure isolation verified.

- [ ] **Step 6: Commit grouped replay**

```bash
git add frontend/public/life-data-collector.user.js frontend/tests
git commit -m "feat: replay life data api groups"
```

### Task 4: Collector panel feedback and group health payload

**Files:**
- Modify: `frontend/public/life-data-collector.user.js`
- Modify: `frontend/tests/life-data-collector-runtime.test.cjs`
- Modify: `backend/app/schemas/life_data.py`
- Modify: `backend/tests/test_life_data_api.py`

**Interfaces:**
- Produces browser payload field `groups: Record<string, {status,last_success_at,last_error,template_count}>`, `template_count`, and `last_full_success_at` on status reports.
- Maintains backward compatibility by making new status fields optional and bounded.

- [ ] **Step 1: Write failing UI and schema tests**

Assert button text changes to `采集中…`, becomes disabled, then reports `成功 4 组，失败 0 组`; panel renders four group rows. Add API tests accepting four known group keys and rejecting unknown keys, overlong errors, and more than four groups.

- [ ] **Step 2: Run focused failures**

Run: `cd frontend && node --test tests/life-data-collector-runtime.test.cjs`

Run: `cd backend && .venv/bin/pytest tests/test_life_data_api.py -q`

Expected: FAIL on missing UI state and forbidden extra Pydantic fields.

- [ ] **Step 3: Implement bounded status contract**

Add Pydantic models `LifeDataGroupHealth` and optional status fields. Restrict group names to `video`, `business`, `advertising`, `other`; timestamps are ISO datetimes, template count is `0..80`, and errors are at most 300 characters.

- [ ] **Step 4: Implement panel state**

Persist only status summaries, render group freshness, registered template count, last full success, failed modules, and next run. Disable manual button while `state.collecting` is true and restore it in `finally`.

- [ ] **Step 5: Run frontend and API tests**

Run the two commands from Step 2.

Expected: both PASS.

- [ ] **Step 6: Commit status contract and UI**

```bash
git add frontend/public/life-data-collector.user.js frontend/tests/life-data-collector-runtime.test.cjs backend/app/schemas/life_data.py backend/tests/test_life_data_api.py
git commit -m "feat: report life data group health"
```

### Task 5: Persist completeness and create deduplicated anomaly tasks

**Files:**
- Modify: `backend/app/models/life_data.py`
- Modify: `backend/app/services/life_data_service.py`
- Create: `backend/alembic/versions/a2b3c4d5e6f7_life_data_group_health.py`
- Modify: `backend/tests/test_life_data_models.py`
- Modify: `backend/tests/test_life_data_service.py`

**Interfaces:**
- Produces JSON column `group_health`, integer `template_count`, datetime `last_full_success_at` on `LifeDataCollectorState`.
- Produces one `AppActionTask` per account/group/stale episode with source type `life_data_collector_health`, status `draft`, and `requires_human_confirm=True`.

- [ ] **Step 1: Write failing model and service tests**

Test status persistence, out-of-order heartbeat protection, stale threshold of 10 minutes for video and 60 minutes for business/advertising, no required freshness for `other`, one task per ongoing stale episode, and a new task only after recovery followed by a new stale episode.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_models.py tests/test_life_data_service.py -q`

Expected: FAIL because health columns and stale-episode logic do not exist.

- [ ] **Step 3: Add migration and model fields**

Create nullable/backward-compatible fields with `group_health JSONB NOT NULL DEFAULT '{}'`, `template_count INTEGER NOT NULL DEFAULT 0`, and nullable `last_full_success_at TIMESTAMPTZ`. Add a JSONB GIN index only if query plans show it is needed; do not add it preemptively.

- [ ] **Step 4: Implement stale episode logic**

Store group health only from the latest heartbeat. Use task number `LIFEHEALTH-{account_id}-{group}-{episode_started_at:%Y%m%d%H%M}` and a deterministic source ID derived from the episode. Task evidence includes last success, template count, error, threshold, collector last seen, and requires manual confirmation.

- [ ] **Step 5: Run backend tests and migration smoke test**

Run: `cd backend && .venv/bin/pytest tests/test_life_data_api.py tests/test_life_data_models.py tests/test_life_data_service.py tests/test_life_data_retention.py -q`

Run: `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic current`

Expected: tests PASS and current revision equals the new health revision.

- [ ] **Step 6: Commit backend completeness**

```bash
git add backend/app backend/alembic/versions backend/tests
git commit -m "feat: track life data collection completeness"
```

### Task 6: End-to-end verification and safe deployment

**Files:**
- Modify: `docs/life-data-collector-install.md`
- Modify: `frontend/public/life-data-collector.user.js` metadata version.

**Interfaces:**
- Validates all prior tasks against the real account `1798826701211732` without exposing credentials.

- [ ] **Step 1: Update operator documentation and version**

Document registry groups, any-tab requirement, browser-closed behavior, full collection button, group health meanings, recovery after login expiry, and how to relearn a changed module. Increment userscript version from `1.0.5` to `1.1.0` and update the metadata test.

- [ ] **Step 2: Run complete automated verification**

Run: `cd frontend && node --test tests/life-data-collector.test.cjs tests/life-data-collector-runtime.test.cjs && npm run build`

Run: `cd backend && .venv/bin/pytest tests/test_life_data_api.py tests/test_life_data_models.py tests/test_life_data_service.py tests/test_life_data_retention.py -q`

Expected: all tests PASS and Vue production build exits 0.

- [ ] **Step 3: Review the complete diff**

Run: `git diff --check HEAD~5..HEAD && git status --short`

Expected: no whitespace errors and only intended files changed.

- [ ] **Step 4: Deploy with a fresh backup**

Create a timestamped backup, cherry-pick reviewed commits into the live branch, run Alembic, build frontend assets, and restart only the backend process using the existing production procedure. Preserve all unrelated dirty production files.

- [ ] **Step 5: Verify live API collection**

From any LifeData page, trigger `立即全量采集`. Confirm server captures include `/flow/content/analysis/video`, `/dito/pc/business/page`, and `/dito/pc/ad/analysis`; advertising includes total cost, material, audience, and region; business includes `verify_gmv`; queue returns to zero; a second run is idempotent.

- [ ] **Step 6: Commit documentation**

```bash
git add docs/life-data-collector-install.md frontend/public/life-data-collector.user.js frontend/tests/life-data-collector.test.cjs
git commit -m "docs: operate full life data api collection"
```
