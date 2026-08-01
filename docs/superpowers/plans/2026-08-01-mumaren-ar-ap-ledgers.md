# 独立财务中心应收应付台账 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将独立财务中心的应收应付完善为三个可用、账簿隔离的台账入口。

**Architecture:** 复用 `mumarenFinanceCenterApi` 和现有 AR/AP 订单持久化接口；将现有混合视图提炼为可配置的台账视图，并新增只读账龄页。所有页通过 Pinia 共享账簿。

**Tech Stack:** Vue 3、TypeScript、Pinia、Element Plus、FastAPI、PostgreSQL。

## Global Constraints

- 仅使用 `/api/v1/finance-center/mumaren`。
- 金蝶迁移账簿永久只读。
- 不引入商品明细、税率和库存映射。

### Task 1: 导航与页面契约

**Files:**
- Modify: `frontend/tests/mumaren-finance-center.test.cjs`
- Modify: `frontend/src/config/mumarenFinanceCenter.ts`
- Modify: `frontend/src/router/index.ts`

- [ ] 写出菜单和路由的失败断言。
- [ ] 运行 `node --test tests/mumaren-finance-center.test.cjs`，确认新增断言失败。
- [ ] 新增三个入口配置与路由。
- [ ] 复跑前端测试。

### Task 2: 账簿隔离台账与账龄页

**Files:**
- Create: `frontend/src/views/mumaren-finance-center/MumarenFinanceArApLedger.vue`
- Create: `frontend/src/views/mumaren-finance-center/MumarenFinanceArApAging.vue`
- Modify: `frontend/tests/mumaren-finance-center.test.cjs`

- [ ] 为路由参数区分 receivable/payable、历史账簿禁写和账龄查询写失败断言。
- [ ] 实现共享账簿、订单筛选、草稿/审核/人工结算和历史只读守卫。
- [ ] 运行前端测试、`npm run type-check` 和 `npm run build`。

### Task 3: 回归、审查和发布

- [ ] 运行后端 AR/AP 与金蝶只读测试。
- [ ] 审查变更，修复阻断问题。
- [ ] 提交、推送、构建上线，使用浏览器切换普通/历史账簿验收。
