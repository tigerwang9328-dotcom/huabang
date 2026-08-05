const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const test = require("node:test");

const utilityUrl = pathToFileURL(path.resolve(__dirname, "..", "src", "utils", "mumarenVoucherLineSummary.mjs")).href;

test("later entered summary becomes the inherited source for following blank lines", async () => {
  const { resolveVoucherLineSummaries } = await import(utilityUrl);
  const result = resolveVoucherLineSummaries([
    { key: "1", summary: "第一笔摘要" },
    { key: "2", summary: "" },
    { key: "3", summary: "" },
    { key: "4", summary: "第二笔摘要" },
    { key: "5", summary: "" },
  ], new Set());

  assert.deepEqual(result.previewByKey, { "1": "", "2": "第一笔摘要", "3": "第一笔摘要", "4": "", "5": "第二笔摘要" });
  assert.deepEqual(result.savedByKey, { "1": "第一笔摘要", "2": "第一笔摘要", "3": "第一笔摘要", "4": "第二笔摘要", "5": "第二笔摘要" });
});

test("explicit clear hides preview and saves only that row blank", async () => {
  const { resolveVoucherLineSummaries } = await import(utilityUrl);
  const result = resolveVoucherLineSummaries([
    { key: "1", summary: "付款摘要" },
    { key: "2", summary: "" },
    { key: "3", summary: "" },
    { key: "4", summary: "" },
  ], new Set(["3"]));

  assert.equal(result.previewByKey["2"], "付款摘要");
  assert.equal(result.previewByKey["3"], "");
  assert.equal(result.savedByKey["3"], "");
  assert.equal(result.previewByKey["4"], "付款摘要");
  assert.equal(result.savedByKey["4"], "付款摘要");
});
