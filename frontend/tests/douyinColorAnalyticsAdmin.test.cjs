"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("online sales exposes the Douyin analysis entry and its analysis routes", () => {
  const router = read("src/router/index.ts");
  const layout = read("src/layouts/MainLayout.vue");

  for (const route of [
    'path: "online-sales/douyin-analysis"',
    'path: "online-sales/douyin-analysis/videos"',
    'path: "online-sales/douyin-analysis/videos/:videoId/annotate"',
    'path: "online-sales/douyin-analysis/styles"',
    'path: "online-sales/douyin-analysis/report"',
  ]) assert.ok(router.includes(route), `missing route: ${route}`);

  assert.ok(layout.includes('path: "/app/online-sales/douyin-analysis"'));
  assert.ok(layout.includes('label: "抖音视频分析"'));
});

test("token rotation displays the raw token once and clears it without persistent storage", () => {
  const admin = read("src/views/douyinColorAnalytics/Admin.vue");
  const api = read("src/api/douyinColorAnalytics.ts");

  for (const required of [
    "issuedToken",
    "<el-dialog",
    "navigator.clipboard.writeText",
    "clearIssuedToken",
    "onBeforeRouteLeave",
    "res.data.upload_token",
    "我已保存",
  ]) assert.ok(admin.includes(required), `missing one-time token behaviour: ${required}`);

  assert.ok(!admin.includes("localStorage"), "raw upload tokens must not be persisted in the browser");
  assert.ok(!admin.includes("res.data.token_prefix"), "rotate result must not rely on a non-contract token prefix");
  assert.ok(!api.includes("token_prefix: string;\n  expires_at: string;\n}"), "rotate response must match the backend response");
});

test("admin page uses the server dot-style permission and keeps advanced controls collapsed", () => {
  const admin = read("src/views/douyinColorAnalytics/Admin.vue");

  assert.ok(admin.includes('auth.hasPermission("douyin.admin")'));
  assert.ok(!admin.includes('auth.hasPermission("douyin:admin")'));
  assert.ok(admin.includes("高级管理"));
  assert.ok(admin.includes("<el-collapse"));
  assert.ok(admin.includes("数据分析入口"));
  assert.ok(admin.includes("采集状态"));
  assert.ok(admin.includes("采集令牌"));
});
