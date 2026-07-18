<template>
  <div class="ai-page">
    <BossAiChat mode="page" />
  </div>
</template>

<script setup lang="ts">
import BossAiChat from "@/components/ai/BossAiChat.vue";
</script>

<style scoped>
.ai-page {
  height: calc(100vh - 96px);
  min-height: 560px;
  overflow: hidden;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #f7f9fb;
}
@media (max-width: 700px) {
  .ai-page {
    height: calc(100vh - 64px);
    min-height: 0;
    border: 0;
    border-radius: 0;
  }
}
</style>
