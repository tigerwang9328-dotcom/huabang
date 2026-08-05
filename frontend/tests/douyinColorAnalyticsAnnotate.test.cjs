"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("video annotation list sorts published videos newest first and keeps unknown dates last", () => {
  const source = read("src/views/douyinColorAnalytics/VideoList.vue");
  assert.ok(source.includes("sortVideosForAnnotation"));
  assert.ok(source.includes("published_at == null"));
  assert.ok(source.includes("Date.parse"));
  assert.ok(source.includes("一套清晰可见的穿搭"));
  assert.ok(!source.includes("每个片段只标注一件主要分析衣物"));
});

test("annotation routes are available to internal signed-in users without a new frontend permission gate", () => {
  const router = read("src/router/index.ts");
  const layout = read("src/layouts/MainLayout.vue");

  assert.ok(router.includes('path: "online-sales/douyin-analysis/videos"'));
  assert.ok(router.includes('path: "online-sales/douyin-analysis/videos/:videoId/annotate"'));
  assert.ok(router.includes('path: "online-sales/douyin-analysis/styles"'));
  assert.ok(!router.includes('permission: "douyin.annotation.edit"'));
  assert.ok(layout.includes("/app/online-sales/douyin-analysis"));
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

test("annotation editor supports full outfit annotation or an explicit non-ranking focus outcome", () => {
  const editor = read("src/views/douyinColorAnalytics/Annotate.vue");

  for (const token of [
    "clear_primary",
    "multi_focus",
    "unclear",
    "outfitParts",
    "clearNonPrimaryOutfit",
    "focus_status === \"clear_primary\"",
    "focus_status !== \"clear_primary\"",
    "GarmentPosition",
    "outfit_parts_json",
  ]) {
    assert.ok(editor.includes(token), `missing focus safeguard: ${token}`);
  }
  assert.ok(editor.includes("至少 2 件"), "clear_primary must require at least 2 garments");
  assert.ok(editor.includes("addPart"), "editor must allow adding outfit parts");
  assert.ok(editor.includes("removePart"), "editor must allow removing outfit parts");
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
    "overlap_reason",
  ]) {
    assert.ok(editor.includes(token), `missing clip maintenance/audit detail: ${token}`);
  }
});

test("annotation action payloads and catalog creates match the minimal backend contract", () => {
  const api = read("src/api/douyinColorAnalytics.ts");
  const editor = read("src/views/douyinColorAnalytics/Annotate.vue");
  const styles = read("src/views/douyinColorAnalytics/Styles.vue");

  assert.ok(!api.includes("review_note?: string"), "action requests must not invent a persisted review note");
  assert.ok(!editor.includes("ElMessageBox.prompt"), "the UI must not collect a rejection note the backend drops");
  assert.ok(!editor.includes("row.review_note"), "the UI must not display a rejection note as persisted");
  assert.ok(styles.includes("await load();"), "style create must reload the ID-only create response");
  assert.ok(styles.includes("await showColors(selectedStyle.value);"), "color create must reload the ID-only create response");
  assert.equal((api.match(/const \{ account_id, \.\.\.body \} = payload/g) || []).length, 2, "style/color patch requests must move account_id out of JSON");
});

test("catalog create responses are treated as ID acknowledgements", () => {
  const api = read("src/api/douyinColorAnalytics.ts");

  assert.ok(api.includes("export interface DouyinCreateResult"));
  assert.equal((api.match(/request\.post<DouyinCreateResult>/g) || []).length, 2);
});

test("annotation product selection searches the real archive and resolves only the selected product", () => {
  const editor = read("src/views/douyinColorAnalytics/Annotate.vue");
  const api = read("src/api/douyinColorAnalytics.ts");

  assert.ok(editor.includes("v-model=\"part.product_code\""));
  assert.ok(editor.includes("searchArchiveStyles"));
  assert.ok(editor.includes("selectArchiveStyle"));
  assert.ok(editor.includes("loadProductSkus"));
  assert.ok(editor.includes("product_name"), "saved clip parts must retain the archive snapshot label");
  assert.ok(!/async function searchArchiveStyles[\s\S]*resolveProductArchiveStyle/.test(editor), "search must not create a local mapping for every result");
  assert.ok(api.includes("searchProductArchiveStyles"));
  assert.ok(api.includes("listProductArchiveSkus"));
});

test("changing a product while its resolver is in flight cannot save the previous product mapping", () => {
  const editor = read("src/views/douyinColorAnalytics/Annotate.vue");

  assert.ok(editor.includes("selectionRequest"));
  assert.ok(editor.includes("part.product_code !== productCode"));
  assert.ok(editor.includes("part.resolving"));
});
