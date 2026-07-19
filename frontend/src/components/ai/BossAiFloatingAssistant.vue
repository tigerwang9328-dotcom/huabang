<template>
  <div v-if="canShowAssistant" class="boss-ai-floating" :class="{ minimized, dragging }" :style="panelStyle">
    <button v-if="minimized" type="button" class="floating-launcher" title="老板AI助手" aria-label="打开老板AI助手" @click="minimized = false">
      <el-icon><ChatDotRound /></el-icon>
    </button>
    <section v-else class="floating-panel">
      <header class="floating-header" @mousedown="startDrag">
        <strong>新聊天</strong>
        <div class="floating-actions">
          <button type="button" title="新建对话" aria-label="新建对话" @click.stop="chatRef?.startNewConversation()">
            <el-icon><Plus /></el-icon>
          </button>
          <button type="button" title="历史记录" aria-label="历史记录" @click.stop="router.push('/app/ai')">
            <el-icon><Clock /></el-icon>
          </button>
          <button type="button" title="最小化" aria-label="最小化" @click.stop="minimized = true">
            <el-icon><Minus /></el-icon>
          </button>
          <button type="button" title="全屏展开" aria-label="全屏展开" @click.stop="router.push('/app/ai')">
            <el-icon><FullScreen /></el-icon>
          </button>
        </div>
      </header>
      <BossAiChat ref="chatRef" mode="floating" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ChatDotRound, Clock, FullScreen, Minus, Plus } from "@element-plus/icons-vue";

const BossAiChat = defineAsyncComponent(() => import("@/components/ai/BossAiChat.vue"));

const router = useRouter();
const authStore = useAuthStore();
const minimized = ref(true);
const dragging = ref(false);
const chatRef = ref<{ startNewConversation: () => void | Promise<void> }>();
const position = ref({ right: 24, bottom: 24 });
let dragStart = { x: 0, y: 0, right: 24, bottom: 24 };

const canShowAssistant = computed(() =>
  authStore.hasPermission("knowledge:ai:view") &&
  authStore.hasAnyRole("boss", "ceo", "shareholder", "admin", "super_admin", "owner", "administrator", "general_manager")
);

const panelStyle = computed(() => ({
  right: `${position.value.right}px`,
  bottom: `${position.value.bottom}px`,
}));

const startDrag = (event: MouseEvent) => {
  if (window.innerWidth <= 700) return;
  dragging.value = true;
  dragStart = {
    x: event.clientX,
    y: event.clientY,
    right: position.value.right,
    bottom: position.value.bottom,
  };
  window.addEventListener("mousemove", onDrag);
  window.addEventListener("mouseup", stopDrag);
};

const onDrag = (event: MouseEvent) => {
  if (!dragging.value) return;
  const nextRight = dragStart.right - (event.clientX - dragStart.x);
  const nextBottom = dragStart.bottom - (event.clientY - dragStart.y);
  position.value = {
    right: Math.max(12, Math.min(window.innerWidth - 440, nextRight)),
    bottom: Math.max(12, Math.min(window.innerHeight - 320, nextBottom)),
  };
};

const stopDrag = () => {
  dragging.value = false;
  window.removeEventListener("mousemove", onDrag);
  window.removeEventListener("mouseup", stopDrag);
};

onBeforeUnmount(stopDrag);
</script>

<style scoped>
.boss-ai-floating {
  position: fixed;
  z-index: 1100;
}
.floating-launcher {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border: 0;
  border-radius: 50%;
  color: #ffffff;
  background: #0f766e;
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.18);
  cursor: pointer;
  font-size: 22px;
}
.floating-panel {
  display: flex;
  flex-direction: column;
  width: 420px;
  height: min(660px, calc(100vh - 48px));
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 28px;
  background: #ffffff;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.18), 0 4px 18px rgba(15, 23, 42, 0.08);
}
.floating-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 54px;
  padding: 12px 18px 8px 22px;
  color: #5f6673;
  background: #ffffff;
  cursor: move;
}
.floating-header strong {
  font-size: 15px;
  font-weight: 500;
}
.floating-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.floating-actions button {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  color: #2f3338;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
}
.floating-actions button:hover {
  background: #f2f3f5;
}
.dragging {
  user-select: none;
}
@media (max-width: 700px) {
  .boss-ai-floating {
    inset: 0 !important;
  }
  .floating-panel {
    width: 100vw;
    height: 100vh;
    border: 0;
    border-radius: 0;
  }
  .floating-header {
    cursor: default;
  }
}
</style>
