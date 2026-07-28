<template>
  <section class="workspace">
    <el-card shadow="never" class="hero">
      <template #header>
        <div class="title-row">
          <div>
            <p class="eyebrow">财务中心 / V2.0</p>
            <h1>会计工作台</h1>
          </div>
          <el-tag type="warning" effect="light">当前为只读验收阶段</el-tag>
        </div>
      </template>
      <p>
        新账采用“草稿 → 财务人员审核 → 人工过账”。历史金蝶数据与当前账严格隔离；在最终切换 Gate 通过前，不开放 V2 制单、审核或过账。
      </p>
      <el-alert
        :title="gateMessage"
        :type="books.length ? 'warning' : 'info'"
        :closable="false"
        show-icon
      />
    </el-card>

    <el-card shadow="never" class="book-card">
      <template #header>
        <div class="title-row">
          <strong>当前账账簿</strong>
          <el-button :loading="loading" text type="primary" @click="loadBooks">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="books" empty-text="尚未建立 V2 当前账账簿">
        <el-table-column prop="book_code" label="账簿编码" min-width="140" />
        <el-table-column prop="book_name" label="账簿名称" min-width="220" />
        <el-table-column prop="status" label="状态" min-width="120" />
        <el-table-column label="正式报表">
          <template #default="{ row }">
            <el-tag :type="row.formal_report_blocked ? 'danger' : 'success'" effect="plain">
              {{ row.formal_report_blocked ? "已阻断" : "可出具" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { financeV2Api, type FinanceV2Book } from "@/api/financeV2";

const books = ref<FinanceV2Book[]>([]);
const loading = ref(false);
const loadError = ref("");

const gateMessage = computed(() => {
  if (loadError.value) return `无法读取 V2 账簿：${loadError.value}`;
  if (!books.value.length) return "尚未导入或批准 V2 当前账数据；这不是零余额，也不代表可开始制单。";
  return "生产写入开关仍应保持关闭，直至历史核对、最终期初、旧入口冻结与人工验收全部通过。";
});

async function loadBooks() {
  loading.value = true;
  loadError.value = "";
  try {
    const response = await financeV2Api.listBooks();
    books.value = response.data || [];
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "请求失败";
  } finally {
    loading.value = false;
  }
}

onMounted(loadBooks);
</script>

<style scoped>
.workspace { display: grid; gap: 16px; }
.hero p { margin: 0 0 16px; color: var(--el-text-color-regular); line-height: 1.7; }
.title-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.title-row h1 { margin: 2px 0 0; font-size: 22px; }
.eyebrow { margin: 0; color: var(--el-color-primary); font-size: 12px; font-weight: 600; }
.book-card { min-height: 260px; }
</style>
