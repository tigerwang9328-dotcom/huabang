<template>
  <div class="ai-page">
    <div class="chat-header">
      <h2>AI经营助手</h2>
      <p>基于华邦经营数据的智能问答 · 权限范围内回答 · 不编造数据</p>
    </div>
    <div class="chat-messages" ref="messagesRef">
      <div v-for="msg in messages" :key="msg.id" :class="[\"msg\", msg.role]">
        <div class="msg-content">
          <div class="msg-role">{{ msg.role === \"user\" ? \"您\" : \"AI助手\" }}</div>
          <div class="msg-text" v-html="msg.content.replace(/\n/g, \"<br>\")"></div>
          <div class="msg-tip" v-if="msg.tip">⚠️ {{ msg.tip }}</div>
        </div>
      </div>
      <div v-if="loading" class="msg assistant"><div class="msg-content"><div class="msg-role">AI助手</div><div class="msg-text">思考中...</div></div></div>
    </div>
    <div class="chat-input">
      <el-input v-model="question" placeholder="输入问题，例如：昨天哪个门店销售最好？今天有哪些待处理任务？" :disabled="loading" @keyup.enter="sendQuestion" clearable>
        <template #append>
          <el-button type="primary" @click="sendQuestion" :loading="loading">发送</el-button>
        </template>
      </el-input>
      <div class="quick-questions">
        <el-button v-for="q in quickQuestions" :key="q" size="small" @click="question = q; sendQuestion()">{{ q }}</el-button>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, nextTick } from "vue";
import { aiApi } from "@/api/ai";
let msgId = 0;
const messages = ref<any[]>([{ id: msgId++, role: "assistant", content: "你好！我是华邦AI经营助手。\n\n我可以帮您分析经营数据、诊断门店问题、生成任务建议。\n\n⚠️ 重要提示：\n• 我只基于系统内真实数据回答\n• 数据不完整时会明确提示\n• 您只能查看权限范围内的数据\n• 所有高风险操作需要人工确认" }]);
const question = ref("");
const loading = ref(false);
const messagesRef = ref<HTMLElement>();
const quickQuestions = ["昨天销售情况如何？", "有哪些待处理任务？", "库存预警有哪些？", "哪个门店表现最好？"];
const sendQuestion = async () => {
  if (!question.value.trim() || loading.value) return;
  const q = question.value.trim();
  messages.value.push({ id: msgId++, role: "user", content: q });
  question.value = "";
  loading.value = true;
  await nextTick();
  messagesRef.value?.scrollTo({ top: 9999 });
  try {
    const res = await aiApi.ask(q);
    const data = res.data.data;
    messages.value.push({
      id: msgId++, role: "assistant",
      content: data.permission_blocked ? `❌ ${data.block_reason}` : data.answer,
      tip: data.data_tip,
    });
  } catch (e: any) {
    messages.value.push({ id: msgId++, role: "assistant", content: "AI服务暂时不可用，请稍后重试。" });
  } finally {
    loading.value = false;
    await nextTick();
    messagesRef.value?.scrollTo({ top: 9999 });
  }
};
</script>
<style scoped>
.ai-page { display: flex; flex-direction: column; height: calc(100vh - 140px); }
.chat-header { margin-bottom: 16px; }
.chat-header h2 { font-size: 18px; color: #333; }
.chat-header p { color: #999; font-size: 13px; }
.chat-messages { flex: 1; overflow-y: auto; background: #f9f9f9; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.msg { display: flex; margin-bottom: 16px; }
.msg.user { justify-content: flex-end; }
.msg-content { max-width: 80%; }
.msg.user .msg-content { background: #409eff; color: #fff; border-radius: 8px 2px 8px 8px; padding: 12px 16px; }
.msg.assistant .msg-content { background: #fff; border-radius: 2px 8px 8px 8px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
.msg-role { font-size: 11px; opacity: 0.7; margin-bottom: 4px; }
.msg-text { font-size: 14px; line-height: 1.6; }
.msg-tip { font-size: 12px; color: #e6a23c; margin-top: 8px; }
.chat-input { background: #fff; border-radius: 8px; padding: 16px; }
.quick-questions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
</style>
