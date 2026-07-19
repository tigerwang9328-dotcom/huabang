const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("boss AI assistant API client exposes new route contract and keeps legacy ask", () => {
  const api = read("src/api/ai.ts");

  for (const token of [
    "aiAssistantApi",
    "/ai-assistant/brief",
    "/ai-assistant/conversations",
    "sendMessage",
    "web_mode",
    "signal",
    "contextData",
    "/ai/ask",
  ]) assert.ok(api.includes(token), `missing ${token}`);
});

test("shared boss AI chat renders structured safe content without v-html", () => {
  const component = read("src/components/ai/BossAiChat.vue");

  for (const token of [
    "conversation-list",
    "archiveConversation",
    "selectConversation",
    "startNewConversation",
    "errorText",
    "历史记录",
    "answer.findings",
    "answer.evidence",
    "answer.external_findings",
    "answer.actions",
    "answer.limitations",
    "target=\"_blank\"",
    "rel=\"noopener noreferrer\"",
    "aiAssistantApi",
    "formatEvidenceNumber",
    "toFixed(2)",
  ]) assert.ok(component.includes(token), `missing ${token}`);
  assert.ok(!component.includes("v-html"));
});

test("floating assistant has drag minimize fullscreen and management role gate", () => {
  const floating = read("src/components/ai/BossAiFloatingAssistant.vue");
  const layout = read("src/layouts/MainLayout.vue");

  for (const token of [
    "boss-ai-floating",
    "minimized = ref(true)",
    "dragging",
    "router.push('/app/ai')",
    "hasPermission(\"knowledge:ai:view\")",
    "hasAnyRole",
    "BossAiChat",
    "ChatDotRound",
    "Plus",
    "Clock",
    "FullScreen",
    "新聊天",
    "border-radius: 28px",
    "aria-label=\"打开老板AI助手\"",
  ]) assert.ok(floating.includes(token), `missing ${token}`);
  assert.ok(!floating.includes(">新建</button>"));
  assert.ok(!floating.includes(">历史</button>"));
  assert.ok(layout.includes("<BossAiFloatingAssistant"));
  assert.ok(layout.includes("import BossAiFloatingAssistant"));
});

test("floating chat follows quick chat shell with icon input controls", () => {
  const component = read("src/components/ai/BossAiChat.vue");

  for (const token of [
    "v-if=\"mode === 'page'\"",
    "input-new-chat",
    "Promotion",
    "thinking-dot",
    "stopThinking",
    "AbortController",
    "ERR_CANCELED",
    "input-stop-button",
    "stop-square",
    ":circle=\"mode === 'floating'\"",
    "boss-ai-chat-floating .chat-input",
    "border-radius: 999px",
  ]) assert.ok(component.includes(token), `missing ${token}`);
});

test("ai page reuses shared boss AI chat component", () => {
  const page = read("src/views/ai/Index.vue");

  assert.ok(page.includes("<BossAiChat mode=\"page\""));
  assert.ok(page.includes("import BossAiChat"));
  assert.ok(!page.includes("v-html"));
});
