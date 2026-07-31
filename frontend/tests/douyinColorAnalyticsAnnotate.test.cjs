"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("annotation routes are available to internal signed-in users without a new frontend permission gate", () => {
  const router = read("src/router/index.ts");
  const layout = read("src/layouts/MainLayout.vue");

  assert.ok(router.includes('path: "douyin-color-analytics/videos"'));
  assert.ok(router.includes('path: "douyin-color-analytics/videos/:videoId/annotate"'));
  assert.ok(router.includes('path: "douyin-color-analytics/styles"'));
  assert.ok(!router.includes('permission: "douyin.annotation.edit"'));
  assert.ok(layout.includes("/app/douyin-color-analytics/videos"));
});

test("annotation API keeps ids as strings and exposes video, clip, style, and review calls", () => {
  const api = read("src/api/douyinColorAnalytics.ts");

  for (const token of [
    "video_id_string: string",
    "listVideos",
    "getVideo",
    "listVideoClips",
    "createVideoClip",
    "updateVideoClip",
    "submitVideoClip",
    "approveVideoClip",
    "rejectVideoClip",
    "restoreVideoClip",
    "listStyles",
    "listColors",
  ]) {
    assert.ok(api.includes(token), `missing annotation API contract: ${token}`);
  }
});

test("annotation editor supports one primary garment or an explicit non-ranking focus outcome", () => {
  const editor = read("src/views/douyinColorAnalytics/Annotate.vue");

  for (const token of [
    "clear_primary",
    "multi_focus",
    "unclear",
    "selectedStyleId",
    "selectedColorId",
    "clearNonPrimaryGarment",
    "focus_status === \"clear_primary\"",
    "focus_status !== \"clear_primary\"",
  ]) {
    assert.ok(editor.includes(token), `missing focus safeguard: ${token}`);
  }
  assert.ok(!editor.includes("multiple"), "the primary garment selector must not allow multi-select");
});

test("annotation editor exposes safe preview, whole-second clip maintenance, validation errors, and audit-facing state", () => {
  const editor = read("src/views/douyinColorAnalytics/Annotate.vue");

  for (const token of [
    "video_preview_url",
    "creator_detail_path",
    "startSecond",
    "endSecond",
    "input_start_ms",
    "input_end_ms",
    "validationErrors",
    "review status",
    "version",
    "updated_by",
    "review_note",
  ]) {
    assert.ok(editor.includes(token), `missing clip maintenance/audit detail: ${token}`);
  }
});
