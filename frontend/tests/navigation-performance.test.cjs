const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");
const ts = require("typescript");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");
const loadTypeScriptModule = (file) => {
  const filename = path.join(root, file);
  const source = fs.readFileSync(filename, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const loaded = new Module(filename, module);
  loaded.filename = filename;
  loaded.paths = Module._nodeModulePaths(path.dirname(filename));
  loaded._compile(output, filename);
  return loaded.exports;
};

test("offline sales menu has one store analysis entry", () => {
  const layout = read("src/layouts/MainLayout.vue");

  assert.ok(layout.includes('{ path: "/app/store", label: "单店分析" }'));
  assert.ok(!layout.includes('{ path: "/app/store/overview", label: "门店总览" }'));
});

test("floating assistant starts minimized and mounts chat only when opened", () => {
  const floating = read("src/components/ai/BossAiFloatingAssistant.vue");

  assert.ok(floating.includes("const minimized = ref(true)"));
  assert.ok(floating.includes('<section v-else class="floating-panel">'));
  assert.ok(floating.includes('<BossAiChat ref="chatRef" mode="floating" />'));
  assert.ok(floating.includes("defineAsyncComponent"));
  assert.ok(floating.includes('() => import("@/components/ai/BossAiChat.vue")'));
  assert.ok(!floating.includes('import BossAiChat from "@/components/ai/BossAiChat.vue"'));
});

test("route navigation cancels page requests without surfacing cancellation errors", () => {
  const request = read("src/api/request.ts");
  const router = read("src/router/index.ts");

  for (const token of [
    "persistAcrossRoutes?: boolean",
    "export const cancelRouteRequests",
    "shouldScopeRouteRequest",
    "config.signal = routeRequests.signal",
    "isRouteRequestCanceled(error)",
    "return Promise.reject(error)",
  ]) assert.ok(request.includes(token), `missing ${token}`);

  assert.ok(router.includes('import { cancelRouteRequests } from "@/api/request"'));
  assert.ok(!router.includes("router.beforeEach((to, _, next) => {\n  cancelRouteRequests();"));
  assert.ok(router.includes("router.afterEach((to, from, failure) => {"));
  assert.ok(router.includes("if (!failure && to.path !== from.path) cancelRouteRequests();"));
  assert.ok(!router.includes("to.fullPath !== from.fullPath"));
});

test("managed page cancellation boundaries handle query navigation and diagnosis users", () => {
  const diagnosis = read("src/views/diagnosis/Index.vue");
  const loadUsers = diagnosis.slice(
    diagnosis.indexOf("const loadUsers"),
    diagnosis.indexOf("const openConfirm"),
  );

  assert.ok(loadUsers.includes("isRouteRequestCanceled"));
  assert.ok(loadUsers.includes("catch"));
});

test("route request lifecycle cancels only read requests on managed pages", () => {
  const {
    RouteRequestLifecycle,
    isRouteRequestCanceled,
    shouldScopeRouteRequest,
  } = loadTypeScriptModule("src/api/routeRequestLifecycle.ts");

  assert.equal(shouldScopeRouteRequest("get", "/app/member", false, false), true);
  assert.equal(shouldScopeRouteRequest("head", "/app/ai-diagnosis/sales", false, false), true);
  for (const method of ["post", "put", "patch", "delete"]) {
    assert.equal(shouldScopeRouteRequest(method, "/app/member", false, false), false);
  }
  assert.equal(shouldScopeRouteRequest("get", "/app/system/users", false, false), false);
  assert.equal(shouldScopeRouteRequest("get", "/app/member", true, false), false);
  assert.equal(shouldScopeRouteRequest("get", "/app/member", false, true), false);

  const lifecycle = new RouteRequestLifecycle();
  const oldSignal = lifecycle.signal;
  lifecycle.cancel();
  assert.equal(oldSignal.aborted, true);
  assert.equal(lifecycle.signal.aborted, false);

  assert.equal(isRouteRequestCanceled({ code: "ERR_CANCELED", config: { routeScoped: true } }), true);
  assert.equal(isRouteRequestCanceled({ code: "ERR_CANCELED", config: {} }), false);
});

test("boss AI assistant requests persist while navigating", () => {
  const ai = read("src/api/ai.ts");
  const assistantBlock = ai.split("export const aiAssistantApi = {")[1].split("export const aiDiagnosisApi = {")[0];
  const persistentCalls = assistantBlock.match(/persistAcrossRoutes:\s*true/g) || [];

  assert.equal(persistentCalls.length, 6);
});
