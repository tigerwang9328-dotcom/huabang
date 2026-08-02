# 凭证快捷操作栏布局 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让录凭证页的快捷操作左对齐、金额汇总右对齐，并在小屏幕自然换行，不改变凭证行为。

**Architecture:** 仅重组 `MumarenFinanceVoucherCreate.vue` 的工具栏 DOM 为“操作组 + 汇总组”两个样式容器。现有 Vue 事件、计算属性和禁用条件不动；CSS 负责宽屏分布与窄屏换行。

**Tech Stack:** Vue 3、TypeScript、Element Plus、Vite。

## Global Constraints

- 不改动 `addLine`、`copyLastLine`、`addReceiptPair`、`addPaymentPair`、`balanceLastLine`、`canSave` 或任何凭证 API。
- 金蝶历史账簿只读规则保持不变。
- 不新增依赖。

---

### Task 1: 重组工具栏并保留所有交互

**Files:**
- Modify: `frontend/src/views/mumaren-finance-center/MumarenFinanceVoucherCreate.vue:55-67,335-341`
- Test: `frontend/tests/mumaren-finance-center.test.cjs`

**Interfaces:**
- Consumes: 现有按钮事件和 `totalDebit`、`totalCredit`、`balanceDiff`、`balanced`。
- Produces: `.voucher-actions` 左侧操作组和 `.totals` 右侧汇总组的响应式布局。

- [ ] **Step 1: 写入失败的静态布局测试**

```js
assert.match(voucherCreate, /class="voucher-actions"/);
assert.match(voucherCreate, /\.dialog-toolbar\s*\{[^}]*justify-content:\s*space-between/);
assert.match(voucherCreate, /\.voucher-actions\s*\{[^}]*display:\s*flex/);
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `node --test tests/mumaren-finance-center.test.cjs`

Expected: 新增测试因缺少 `voucher-actions` 而失败。

- [ ] **Step 3: 最小实现**

```vue
<div class="dialog-toolbar">
  <div class="voucher-actions">…现有五个按钮原样保留…</div>
  <div class="totals">…现有汇总原样保留…</div>
</div>
```

```css
.voucher-actions { display: flex; flex-wrap: wrap; gap: 12px; }
@media (max-width: 640px) { .totals { margin-left: 0; } }
```

- [ ] **Step 4: 运行测试与构建**

Run: `node --test tests/mumaren-finance-center.test.cjs && npm run type-check && npm run build`

Expected: 静态测试、类型检查与生产构建通过。

- [ ] **Step 5: 浏览器视觉验收与提交**

Run: 访问 `/app/finance-center/mumaren/vouchers/create`，确认操作按钮在左、汇总在右、窄屏可换行；随后提交：

```bash
git add frontend/src/views/mumaren-finance-center/MumarenFinanceVoucherCreate.vue frontend/tests/mumaren-finance-center.test.cjs docs/superpowers/plans/2026-08-02-voucher-action-toolbar-layout.md
git commit -m "style(finance): align voucher action toolbar"
```
