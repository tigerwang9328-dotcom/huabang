const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("finance center base URL opens the V2 core workspace with the existing finance read permission", () => {
  const router = read("src/router/index.ts");

  assert.ok(
    router.includes('{ path: "finance-center", redirect: "/app/finance-center/core-workspace" }'),
    "the finance center base route must redirect to the V2 core workspace",
  );
  assert.ok(
    router.includes('["/app/finance-center", "finance:profit:view"]'),
    "the finance center route family must use the existing finance read permission",
  );
});
