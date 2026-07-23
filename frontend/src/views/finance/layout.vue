<template>
  <div class="finance-wrap">
    <!-- 账套 & 期间切换工具栏 -->
    <div class="finance-bar">
      <span class="bar-label">账套</span>
      <el-select
        v-model="store.bookId"
        size="small"
        style="width:130px"
        @change="store.switchBook($event)"
      >
        <el-option
          v-for="b in store.books"
          :key="b.id"
          :label="b.book_name"
          :value="b.id"
        />
      </el-select>
      <span class="bar-sep">|</span>
      <span class="bar-label">期间</span>
      <el-date-picker
        v-model="store.currentPeriod"
        type="month"
        value-format="YYYY-MM"
        format="YYYY年MM月"
        size="small"
        style="width:130px"
        @change="store.setPeriod($event)"
      />
    </div>

    <!-- 页面内容 -->
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue"
import { useFinanceStore } from "@/stores/finance"

const store = useFinanceStore()

onMounted(() => {
  if (!store.loaded) store.loadBooks()
})
</script>

<style scoped>
.finance-wrap {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.finance-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 14px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border, #e8edf2);
  flex-shrink: 0;
}

.bar-label {
  font-size: 12px;
  color: var(--text-4, #9ca3af);
  white-space: nowrap;
}

.bar-sep {
  color: var(--border, #d1d5db);
  font-size: 14px;
  margin: 0 4px;
  user-select: none;
}
</style>
