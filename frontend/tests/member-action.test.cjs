const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const memberView = fs.readFileSync(path.join(root, "src/views/member/Index.vue"), "utf8");
const taskView = fs.readFileSync(path.join(root, "src/views/task/Detail.vue"), "utf8");
const memberApi = fs.readFileSync(path.join(root, "src/api/member.ts"), "utf8");
const taskApi = fs.readFileSync(path.join(root, "src/api/task.ts"), "utf8");

test("member page exposes a daily VIP action list and honest effect metrics", () => {
  assert.match(memberView, /今日行动/);
  assert.match(memberView, /触达率/);
  assert.match(memberView, /到店率/);
  assert.match(memberView, /成交率/);
  assert.match(memberView, /自然复购/);
  assert.match(memberView, /fetchMemberActions/);
  assert.match(memberApi, /\/member\/actions\/overview/);
  assert.match(memberApi, /\/member\/actions\/list/);
  assert.match(memberApi, /\/member\/actions\/rebuild/);
});

test("member action task requires human confirmation and structured follow-up", () => {
  assert.match(taskView, /VIP会员行动/);
  assert.match(taskView, /确认联系话术/);
  assert.match(taskView, /是否联系/);
  assert.match(taskView, /是否到店/);
  assert.match(taskView, /是否成交/);
  assert.match(taskView, /关联百胜小票/);
  assert.match(taskView, /未成交原因/);
  assert.match(taskView, /下次跟进时间/);
  assert.match(taskView, /member_followup/);
  assert.match(taskApi, /\/task\/assignees/);
});
