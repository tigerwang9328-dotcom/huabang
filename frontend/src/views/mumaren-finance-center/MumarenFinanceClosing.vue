<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">期末结账</p>
        <h2>结账</h2>
        <p>期间结账与重新开启;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="periods" empty-text="暂无结账期间" stripe>
      <el-table-column prop="period" label="期间" width="140" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="结账时间" width="180">
        <template #default="{ row }">{{ row.closed_at || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-popconfirm v-if="row.status === 'open'" title="确定对该期间结账?" @confirm="close(row)">
            <template #reference>
              <el-button :disabled="isReadonly" link type="success" size="small" :loading="actingId === row.id">结账</el-button>
            </template>
          </el-popconfirm>
          <el-popconfirm v-if="row.status === 'closed'" title="确定重新开启该期间?" @confirm="reopen(row)">
            <template #reference>
              <el-button :disabled="isReadonly" link type="warning" size="small" :loading="actingId === row.id">重新开启</el-button>
            </template>
          </el-popconfirm>
          <span v-if="row.status === 'closing'" class="done-text">结账中</span>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { storeToRefs } from "pinia";
import { ElMessage } from "element-plus";
import {
  mumarenFinanceCenterApi,
  periodsApi,
  type MumarenFinanceBook,
  type MumarenPeriod,
} from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBookStore } from "@/stores/mumarenFinanceBook";

const bookStore = useMumarenFinanceBookStore();
const { books, bookId, isReadonly } = storeToRefs(bookStore);
const periods = ref<MumarenPeriod[]>([]);
const loading = ref(false);
const error = ref("");
const actingId = ref<number>();

const statusLabel = (s: string) => (s === "open" ? "未结账" : s === "closing" ? "结账中" : "已结账");
const statusTagType = (s: string): "info" | "warning" | "success" =>
  s === "open" ? "info" : s === "closing" ? "warning" : "success";

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    periods.value = (await periodsApi.list({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载结账期间。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  periods.value = [];
  load();
};

onMounted(async () => {
  try {
    await bookStore.loadBooks();
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const close = async (row: MumarenPeriod) => {
  if (isReadonly.value) return;
  if (!bookId.value || row.status !== "open") return;
  actingId.value = row.id;
  try {
    await periodsApi.close(row.id, bookId.value);
    ElMessage.success(`期间 ${row.period} 已结账`);
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "结账失败");
  } finally {
    actingId.value = undefined;
  }
};

const reopen = async (row: MumarenPeriod) => {
  if (isReadonly.value) return;
  if (!bookId.value || row.status !== "closed") return;
  actingId.value = row.id;
  try {
    await periodsApi.reopen(row.id, bookId.value);
    ElMessage.success(`期间 ${row.period} 已重新开启`);
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "重新开启失败");
  } finally {
    actingId.value = undefined;
  }
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
.done-text { color: #909399; font-size: 13px; }
@media (max-width: 640px) { .filters { flex-direction: column; } .heading { flex-direction: column; } }
</style>
