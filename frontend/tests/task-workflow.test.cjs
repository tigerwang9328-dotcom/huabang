const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("task list navigates inside the app route and includes create/feedback controls", () => {
  const source = read("src/views/task/Index.vue");
  assert.match(source, /`\/app\/task\/\$\{id\}`/);
  assert.match(source, /创建任务/);
  assert.match(source, /attachment_urls/);
});

test("task detail exposes confirm review return and close actions", () => {
  const source = read("src/views/task/Detail.vue");
  for (const label of ["确认派发", "提交反馈", "复查通过", "退回整改", "关闭任务"]) {
    assert.match(source, new RegExp(label));
  }
});

test("task API sends request ids for feedback and review idempotency", () => {
  const source = read("src/api/task.ts");
  assert.match(source, /request_id/);
  assert.match(source, /retryNotification/);
  assert.match(source, /retry-notification/);
});

test("task routes menu and workflow actions are permission gated", () => {
  const router = read("src/router/index.ts");
  const layout = read("src/layouts/MainLayout.vue");
  const list = read("src/views/task/Index.vue");
  const detail = read("src/views/task/Detail.vue");
  assert.match(router, /\["\/app\/task", "task:view"\]/);
  assert.match(layout, /path: "\/app\/task",[\s\S]*?permission: "task:view"/);
  for (const permission of ["task:create", "task:approve", "task:feedback"]) {
    assert.ok(list.includes(`authStore.hasPermission('${permission}')`));
  }
  for (const permission of ["task:approve", "task:feedback", "task:review", "task:close"]) {
    assert.ok(detail.includes(`authStore.hasPermission('${permission}')`));
  }
  assert.match(list, /row\.can_feedback/);
  assert.match(detail, /task\.can_feedback/);
  assert.match(list, /request_id: crypto\.randomUUID\(\)/);
  assert.match(detail, /review\.request_id = crypto\.randomUUID\(\)/);
  assert.match(detail, /safeAttachmentUrls/);
  assert.match(detail, /parsed\.protocol === 'http:'/);
  assert.match(detail, /rel="noopener noreferrer"/);
  assert.match(list, /重试通知/);
  assert.match(detail, /重试通知/);
  assert.match(list, /notification\.success/);
  assert.match(list, /taskApi\.retryNotification/);
  assert.match(detail, /taskApi\.retryNotification/);
});
