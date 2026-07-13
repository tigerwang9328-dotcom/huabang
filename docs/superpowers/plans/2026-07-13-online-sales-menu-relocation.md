# 线上销售菜单归属调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“投流优化”和“经营日报”从侧边栏顶层移动到“销售中心 → 线上销售”，同时保持原页面地址和功能不变。

**Architecture:** 仅修改 `MainLayout.vue` 的菜单数据结构，不修改两个页面组件和 Vue Router 路由。通过源码契约测试验证入口归属、顺序和旧地址兼容，再执行完整前端测试与生产构建。

**Tech Stack:** Vue 3、TypeScript、Node.js 内置测试运行器、Vite。

## Global Constraints

- 保留 `/app/marketing/investment` 和 `/app/report` 原路由。
- 两个入口只在“销售中心 → 线上销售”显示，不再作为顶层入口。
- 保留“线上总览、平台销售、退款售后”的规划中状态。
- 不修改页面、接口和数据采集逻辑。

---

### Task 1: 锁定菜单归属行为

**Files:**
- Modify: `frontend/tests/life-data-investment-page.test.cjs`
- Test: `frontend/tests/life-data-investment-page.test.cjs`

**Interfaces:**
- Consumes: `frontend/src/layouts/MainLayout.vue` 中的 `menuGroups` 源码。
- Produces: 菜单归属与旧路由兼容的回归约束。

- [ ] **Step 1: 写入失败测试**

测试截取 `label: "线上销售"` 对应的菜单片段，要求其中同时包含 `/app/marketing/investment`、`/app/report`，并要求顶层销售中心之前不再包含这两个入口。

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend && node --test tests/life-data-investment-page.test.cjs`

Expected: FAIL，原因是两个入口仍处于侧边栏顶层。

### Task 2: 最小化调整菜单结构

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue`
- Test: `frontend/tests/life-data-investment-page.test.cjs`

**Interfaces:**
- Consumes: 现有 `MenuGroup`、`MenuItem` 和三级菜单渲染逻辑。
- Produces: “销售中心 → 线上销售 → 投流优化、经营日报”的菜单结构。

- [ ] **Step 1: 删除两个顶层菜单对象**

删除路径为 `/app/marketing/investment` 和 `/app/report` 的顶层对象。

- [ ] **Step 2: 在线上销售 children 首部加入两个可点击项**

```ts
{ path: "/app/marketing/investment", label: "投流优化" },
{ path: "/app/report", label: "经营日报" },
```

- [ ] **Step 3: 运行目标测试并确认通过**

Run: `cd frontend && node --test tests/life-data-investment-page.test.cjs`

Expected: PASS。

### Task 3: 回归、构建与生产部署

**Files:**
- Verify: `frontend/src/layouts/MainLayout.vue`
- Verify: `frontend/src/router/index.ts`

**Interfaces:**
- Consumes: Task 2 的菜单结构。
- Produces: 可部署的生产前端构建。

- [ ] **Step 1: 运行全部前端测试**

Run: `cd frontend && node --test tests/*.test.cjs`

Expected: 全部 PASS。

- [ ] **Step 2: 运行生产构建**

Run: `cd frontend && npm run build`

Expected: Vite 构建退出码为 0。

- [ ] **Step 3: 备份并部署目标文件**

备份正式目录的 `MainLayout.vue`，只部署菜单与测试文件，不覆盖其他业务文件。

- [ ] **Step 4: 在正式目录重新测试和构建**

Run: `cd /srv/huabang-ai-center/frontend && node --test tests/*.test.cjs && npm run build`

Expected: 全部测试通过且构建退出码为 0。

- [ ] **Step 5: 验证生产构建产物**

确认 `dist/assets/MainLayout-*.js` 同时包含“投流优化”和“经营日报”，且源码中两个入口位于 `sales-online` 子菜单。
