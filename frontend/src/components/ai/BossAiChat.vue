<template>
  <section class="boss-ai-chat" :class="`boss-ai-chat-${mode}`">
    <header v-if="mode === 'page'" class="boss-ai-chat-head">
      <div>
        <h2>老板AI助手</h2>
        <p v-if="mode === 'page'">只读分析 · 华邦真实数据优先 · 外部经验仅作参考</p>
      </div>
      <div class="chat-tools">
        <el-button size="small" @click="startNewConversation">新建对话</el-button>
        <el-button size="small" @click="showHistory = !showHistory">历史记录</el-button>
        <el-button v-if="conversationId" size="small" type="danger" plain @click="archiveCurrentConversation">归档</el-button>
      </div>
    </header>

    <div v-if="errorText" class="assistant-error">{{ errorText }}</div>

    <aside v-if="showHistory" class="conversation-list">
      <button
        v-for="item in conversations"
        :key="item.id"
        type="button"
        :class="{ active: item.id === conversationId }"
        @click="selectConversation(item.id)"
      >
        <strong>{{ item.title || "新对话" }}</strong>
        <span>{{ item.last_message_at || item.created_at || "" }}</span>
      </button>
      <p v-if="!conversations.length">暂无历史记录</p>
    </aside>

    <div class="assistant-brief" v-if="brief && messages.length === 0">
      <div class="brief-date">经营日 {{ brief.data_as_of || "暂无快照" }}</div>
      <div class="health-row">
        <span>就绪 {{ brief.data_health?.ready || 0 }}</span>
        <span>估算 {{ brief.data_health?.estimated || 0 }}</span>
        <span>较旧 {{ brief.data_health?.stale || 0 }}</span>
        <span>待接入 {{ brief.data_health?.pending_data || 0 }}</span>
      </div>
      <div class="brief-list">
        <p v-for="item in brief.findings || []" :key="item.text">{{ item.text }}</p>
      </div>
      <div class="quick-questions">
        <button v-for="q in brief.suggested_questions || []" :key="q" type="button" @click="askQuick(q)">
          {{ q }}
        </button>
      </div>
    </div>

    <div class="message-list" ref="messagesRef">
      <article v-for="msg in messages" :key="msg.localId || msg.id" :class="['message', msg.role]">
        <div class="message-bubble">
          <div class="message-role">{{ msg.role === "user" ? "您" : "老板AI助手" }}</div>
          <p v-if="msg.role === 'user'" class="plain-text">{{ msg.content }}</p>
          <template v-else>
            <p class="plain-text">{{ msg.answer?.summary || msg.content }}</p>
            <div class="answer-section" v-if="msg.answer?.findings?.length">
              <h3>华邦真实数据</h3>
              <ul>
                <li v-for="finding in msg.answer.findings" :key="finding.text">
                  <span>{{ finding.text }}</span>
                  <em>{{ confidenceLabel(finding.confidence) }}</em>
                </li>
              </ul>
            </div>
            <div class="answer-section evidence-section" v-if="msg.answer?.evidence?.length">
              <h3>证据卡</h3>
              <div class="evidence-grid">
                <div v-for="item in msg.answer.evidence" :key="item.ref" class="evidence-card">
                  <span>{{ item.label }}</span>
                  <strong>{{ evidenceValue(item) }}</strong>
                  <small>{{ item.status || "unknown" }}</small>
                </div>
              </div>
            </div>
            <div class="answer-section" v-if="msg.answer?.external_findings?.length">
              <h3>外部经验</h3>
              <p v-for="item in msg.answer.external_findings" :key="item.url || item.title">{{ item.summary || item.title }}</p>
            </div>
            <div class="answer-section" v-if="msg.answer?.actions?.length">
              <h3>建议</h3>
              <ul>
                <li v-for="action in msg.answer.actions" :key="action.text">
                  <span>{{ action.text }}</span>
                  <em>需人工确认</em>
                </li>
              </ul>
            </div>
            <div class="answer-section limitations" v-if="msg.answer?.limitations?.length">
              <h3>数据限制</h3>
              <p v-for="item in msg.answer.limitations" :key="item">{{ item }}</p>
            </div>
            <div class="answer-section sources" v-if="msg.answer?.sources?.length">
              <h3>来源</h3>
              <a
                v-for="source in msg.answer.sources"
                :key="source.url"
                :href="source.url"
                target="_blank"
                rel="noopener noreferrer"
              >{{ source.title || source.url }}</a>
            </div>
          </template>
        </div>
      </article>
      <article v-if="loading" class="message assistant thinking-message">
        <div class="message-bubble">
          <div class="message-role">老板AI助手</div>
          <div v-if="mode === 'floating'" class="thinking-dot" aria-label="老板AI助手正在思考"></div>
          <p v-else class="plain-text">正在核对经营快照...</p>
        </div>
      </article>
    </div>

    <footer class="chat-input">
      <button
        v-if="mode === 'floating'"
        type="button"
        class="input-new-chat"
        title="新建对话"
        aria-label="新建对话"
        @click="startNewConversation"
      >
        <el-icon><Plus /></el-icon>
      </button>
      <el-input
        v-model="question"
        :autosize="{ minRows: 1, maxRows: 4 }"
        type="textarea"
        resize="none"
        :disabled="loading"
        placeholder="问经营问题，例如：昨天整体经营最需要关注什么？"
        @keydown.enter.exact.prevent="sendQuestion"
      />
      <el-button
        type="primary"
        :loading="mode === 'page' && loading"
        :circle="mode === 'floating'"
        :class="{ 'input-stop-button': mode === 'floating' && loading }"
        @click="handleSubmitButton"
      >
        <span v-if="mode === 'floating' && loading" class="stop-square" aria-hidden="true"></span>
        <el-icon v-else-if="mode === 'floating'"><Promotion /></el-icon>
        <span v-else>发送</span>
      </el-button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { aiAssistantApi } from "@/api/ai";
import { Plus, Promotion } from "@element-plus/icons-vue";

const props = defineProps<{ mode: "page" | "floating" }>();
const route = useRoute();
const storageKey = "hb_boss_ai_current_conversation";
let localId = 1;

const brief = ref<any>();
const messages = ref<any[]>([]);
const conversations = ref<any[]>([]);
const conversationId = ref<number | null>(Number(localStorage.getItem(storageKey)) || null);
const question = ref("");
const loading = ref(false);
const showHistory = ref(false);
const errorText = ref("");
const messagesRef = ref<HTMLElement>();
const activeController = ref<AbortController | null>(null);

const contextData = () => ({
  route: route.fullPath,
  stat_date: typeof route.query.stat_date === "string" ? route.query.stat_date : undefined,
  store_code: typeof route.query.store_code === "string" ? route.query.store_code : undefined,
});

const scrollBottom = async () => {
  await nextTick();
  messagesRef.value?.scrollTo({ top: messagesRef.value.scrollHeight, behavior: "smooth" });
};

const loadBrief = async () => {
  try {
    const res = await aiAssistantApi.getBrief(contextData());
    brief.value = res.data.data;
    errorText.value = "";
  } catch {
    brief.value = null;
    errorText.value = "暂时无法读取经营快照。";
  }
};

const loadConversations = async () => {
  try {
    const res = await aiAssistantApi.listConversations();
    conversations.value = res.data.data || [];
    if (!conversationId.value && conversations.value[0]?.id) {
      conversationId.value = conversations.value[0].id;
      localStorage.setItem(storageKey, String(conversationId.value));
    }
  } catch {
    conversations.value = [];
  }
};

const selectConversation = async (id: number) => {
  conversationId.value = id;
  localStorage.setItem(storageKey, String(id));
  showHistory.value = false;
  await loadMessages();
};

const ensureConversation = async (): Promise<number> => {
  if (conversationId.value) return conversationId.value;
  const res = await aiAssistantApi.createConversation(contextData());
  conversationId.value = res.data.data.id;
  localStorage.setItem(storageKey, String(conversationId.value));
  if (!conversationId.value) throw new Error("会话创建失败");
  return conversationId.value;
};

const loadMessages = async () => {
  if (!conversationId.value) return;
  try {
    const res = await aiAssistantApi.getMessages(conversationId.value);
    messages.value = (res.data.data || []).map((item: any) => ({ ...item, answer: item.answer || item.answer_payload }));
    scrollBottom();
  } catch {
    messages.value = [];
  }
};

const startNewConversation = async () => {
  const res = await aiAssistantApi.createConversation(contextData());
  conversationId.value = res.data.data.id;
  localStorage.setItem(storageKey, String(conversationId.value));
  messages.value = [];
  showHistory.value = false;
  await loadConversations();
  await loadBrief();
};

const archiveCurrentConversation = async () => {
  if (!conversationId.value) return;
  await aiAssistantApi.archiveConversation(conversationId.value);
  localStorage.removeItem(storageKey);
  conversationId.value = null;
  messages.value = [];
  await loadConversations();
  await loadBrief();
};

const askQuick = (value: string) => {
  question.value = value;
  sendQuestion();
};

const isRequestCanceled = (error: any) =>
  error?.code === "ERR_CANCELED" || error?.name === "CanceledError" || error?.message === "canceled";

const stopThinking = () => {
  activeController.value?.abort();
  activeController.value = null;
  loading.value = false;
};

const handleSubmitButton = () => {
  if (loading.value && props.mode === "floating") {
    stopThinking();
    return;
  }
  sendQuestion();
};

const sendQuestion = async () => {
  const text = question.value.trim();
  if (!text || loading.value) return;
  question.value = "";
  loading.value = true;
  errorText.value = "";
  const controller = new AbortController();
  activeController.value = controller;
  messages.value.push({ localId: `u-${localId++}`, role: "user", content: text });
  await scrollBottom();
  try {
    const id = await ensureConversation();
    const res = await aiAssistantApi.sendMessage(id, text, contextData(), controller.signal);
    messages.value.push({
      localId: `a-${localId++}`,
      role: "assistant",
      content: res.data.data.summary,
      answer: res.data.data,
    });
    await loadConversations();
  } catch (error: any) {
    if (isRequestCanceled(error)) return;
    errorText.value = error?.message || "老板AI助手暂时不可用，请稍后再试。";
    messages.value.push({
      localId: `e-${localId++}`,
      role: "assistant",
      content: errorText.value,
    });
  } finally {
    if (activeController.value === controller) {
      loading.value = false;
      activeController.value = null;
    }
    await scrollBottom();
  }
};

const confidenceLabel = (value?: string) => {
  if (value === "high") return "高置信";
  if (value === "low") return "低置信";
  return "中置信";
};

const formatEvidenceNumber = (value: number) => {
  if (!Number.isFinite(value)) return String(value);
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
};

const evidenceValue = (item: any) => {
  if (item.status === "pending_data") return "待接入";
  if (item.value === null || item.value === undefined || item.value === "") return "未展示";
  const rawValue = typeof item.value === "number" ? formatEvidenceNumber(item.value) : item.value;
  return `${rawValue}${item.unit || ""}`;
};

onMounted(async () => {
  await loadBrief();
  await loadConversations();
  await loadMessages();
});

watch(() => props.mode, () => scrollBottom());

defineExpose({ startNewConversation, selectConversation });
</script>

<style scoped>
.boss-ai-chat {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: #f7f9fb;
  color: #1f2a37;
}
.boss-ai-chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 12px;
}
.boss-ai-chat-floating {
  background: #ffffff;
}
.boss-ai-chat-head h2 {
  margin: 0;
  font-size: 20px;
}
.boss-ai-chat-head p,
.plain-text,
.answer-section p {
  margin: 0;
}
.chat-tools {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}
.assistant-error {
  margin: 8px 12px 0;
  padding: 8px 10px;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  color: #9a3412;
  background: #fff7ed;
  font-size: 13px;
}
.conversation-list {
  display: grid;
  gap: 6px;
  margin: 8px 12px 0;
  padding: 8px;
  max-height: 160px;
  overflow: auto;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #ffffff;
}
.conversation-list button {
  display: grid;
  gap: 2px;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  text-align: left;
  background: #f8fafc;
  cursor: pointer;
}
.conversation-list button.active {
  border-color: #2563eb;
  background: #eff6ff;
}
.conversation-list strong {
  font-size: 13px;
}
.conversation-list span,
.conversation-list p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}
.assistant-brief {
  margin: 12px;
  padding: 12px;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #ffffff;
}
.boss-ai-chat-floating .assistant-brief {
  order: 2;
  margin: 0 22px 16px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.boss-ai-chat-floating .brief-date {
  display: none;
}
.boss-ai-chat-floating .health-row {
  display: none;
}
.boss-ai-chat-floating .brief-list {
  display: none;
}
.boss-ai-chat-floating .quick-questions {
  display: grid;
  gap: 2px;
  margin-top: 0;
}
.boss-ai-chat-floating .quick-questions::before {
  content: "快捷问题";
  margin-bottom: 8px;
  color: #8a8f98;
  font-size: 14px;
}
.boss-ai-chat-floating .quick-questions button {
  justify-content: flex-start;
  padding: 8px 0;
  border: 0;
  border-radius: 0;
  color: #565c66;
  background: transparent;
  text-align: left;
  font-size: 14px;
}
.boss-ai-chat-floating .quick-questions button:hover {
  color: #111827;
}
.brief-date {
  font-weight: 700;
}
.health-row,
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.health-row span,
.quick-questions button {
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #f4f7fa;
  padding: 6px 9px;
  font-size: 12px;
}
.quick-questions button {
  cursor: pointer;
}
.brief-list p {
  margin: 8px 0 0;
  font-size: 13px;
}
.message-list {
  flex: 1;
  overflow: auto;
  padding: 12px;
}
.boss-ai-chat-floating .message-list {
  order: 1;
  padding: 8px 22px 16px;
  background: #ffffff;
}
.message {
  display: flex;
  margin-bottom: 12px;
}
.message.user {
  justify-content: flex-end;
}
.message-bubble {
  width: min(100%, 720px);
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #d8e0ea;
  background: #ffffff;
}
.boss-ai-chat-floating .message-bubble {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.message.user .message-bubble {
  width: auto;
  max-width: 82%;
  color: #ffffff;
  background: #2563eb;
  border-color: #2563eb;
}
.boss-ai-chat-floating .message.user .message-bubble {
  max-width: 84%;
  padding: 10px 12px;
  border-radius: 18px;
  color: #ffffff;
  background: #2563eb;
}
.boss-ai-chat-floating .message.assistant .message-bubble {
  width: 100%;
}
.boss-ai-chat-floating .thinking-message {
  justify-content: flex-start;
  min-height: 160px;
  align-items: center;
}
.thinking-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #15191f;
  animation: thinking-pulse 1.25s ease-in-out infinite;
}
@keyframes thinking-pulse {
  0%,
  100% {
    transform: scale(0.86);
    box-shadow: 0 0 0 0 rgba(21, 25, 31, 0.12);
  }
  50% {
    transform: scale(1);
    box-shadow: 0 0 0 6px rgba(21, 25, 31, 0);
  }
}
.boss-ai-chat-floating .message-role {
  display: none;
}
.boss-ai-chat-floating .answer-section {
  border-top-color: #f0f1f3;
}
.message-role {
  margin-bottom: 6px;
  font-size: 12px;
  opacity: 0.68;
}
.plain-text {
  white-space: pre-wrap;
  line-height: 1.6;
  font-size: 14px;
}
.answer-section {
  margin-top: 12px;
  border-top: 1px solid #edf1f5;
  padding-top: 10px;
}
.answer-section h3 {
  margin: 0 0 8px;
  font-size: 13px;
}
.answer-section ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.answer-section li {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 13px;
}
.answer-section em {
  flex: 0 0 auto;
  color: #64748b;
  font-style: normal;
  font-size: 12px;
}
.evidence-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
}
.evidence-card {
  display: grid;
  gap: 4px;
  padding: 8px;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #f8fafc;
}
.evidence-card span,
.evidence-card small {
  color: #64748b;
  font-size: 12px;
}
.evidence-card strong {
  font-size: 14px;
}
.limitations {
  color: #8a5a00;
}
.sources {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.sources a {
  color: #2563eb;
  font-size: 13px;
}
.chat-input {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #d8e0ea;
  background: #ffffff;
}
.boss-ai-chat-floating .chat-input {
  order: 3;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: end;
  gap: 8px;
  margin: 0 14px 14px;
  padding: 8px 8px 8px 16px;
  border: 1px solid #e8eaee;
  border-radius: 999px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
}
.input-new-chat {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  align-self: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  color: #5f6673;
  background: transparent;
  cursor: pointer;
  font-size: 17px;
}
.input-new-chat:hover {
  background: #f2f3f5;
}
.boss-ai-chat-floating .chat-input :deep(.el-textarea__inner) {
  min-height: 30px !important;
  padding: 5px 0;
  border: 0;
  box-shadow: none;
  color: #111827;
  background: transparent;
  line-height: 20px;
}
.boss-ai-chat-floating .chat-input :deep(.el-textarea__inner::placeholder) {
  color: #b0b5bd;
}
.boss-ai-chat-floating .chat-input :deep(.el-button) {
  width: 34px;
  height: 34px;
  min-height: 34px;
  border: 0;
  background: #8d939b;
}
.boss-ai-chat-floating .chat-input :deep(.el-button:hover) {
  background: #6f7680;
}
.boss-ai-chat-floating .chat-input :deep(.input-stop-button) {
  background: #15191f;
}
.boss-ai-chat-floating .chat-input :deep(.input-stop-button:hover) {
  background: #15191f;
}
.stop-square {
  width: 11px;
  height: 11px;
  border-radius: 3px;
  background: #ffffff;
}
@media (max-width: 700px) {
  .boss-ai-chat-head {
    padding: 12px;
  }
  .chat-input {
    grid-template-columns: 1fr;
  }
  .boss-ai-chat-floating .chat-input {
    grid-template-columns: auto 1fr auto;
    margin: 0 12px 12px;
  }
}
</style>
