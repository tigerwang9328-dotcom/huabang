<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">系统设置</p>
        <h2>操作日志</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿未导入操作审计日志；当前仅保留已迁入业务数据的只读查询。" : "财务中心操作审计日志;按账簿与时间范围查询,只读展示。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-select v-model="filterModule" placeholder="按模块过滤" clearable style="width: 180px" @change="load">
        <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
      </el-select>
      <el-date-picker
        v-model="filterRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width: 280px"
        @change="load"
      />
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-alert
      v-else-if="isReadonly"
      type="info"
      title="金蝶迁移账簿未导入操作审计日志"
      :closable="false"
      show-icon
    />

    <el-table v-if="!isReadonly" v-loading="loading" :data="filteredLogs" empty-text="暂无日志" stripe>
      <el-table-column prop="operation_time" label="操作时间" width="180" />
      <el-table-column prop="module" label="模块" width="100" />
      <el-table-column prop="action" label="操作" width="100" />
      <el-table-column prop="operator" label="操作人" width="120" />
      <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip />
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  auditLogsApi,
  type MumarenAuditLog,
} from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";

const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const logs = ref<MumarenAuditLog[]>([]);
const loading = ref(false);
const error = ref("");
const filterModule = ref("");
const filterRange = ref<[string, string] | null>(null);
let loadRequestVersion = 0;

const moduleOptions = ["凭证", "AR-AP", "税务", "资产", "发票", "出纳", "工资", "结账"];

const filteredLogs = computed(() => {
  if (!filterModule.value) return logs.value;
  return logs.value.filter((x) => x.module === filterModule.value);
});

const load = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  if (isReadonly.value) {
    logs.value = [];
    loading.value = false;
    error.value = "";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const params: Parameters<typeof auditLogsApi.list>[0] = {};
    if (requestedBookId) params.book_id = requestedBookId;
    if (filterRange.value && filterRange.value.length === 2) {
      params.start_date = filterRange.value[0];
      params.end_date = filterRange.value[1];
    }
    const response = await auditLogsApi.list(params);
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) {
      logs.value = response.data.data;
    }
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) {
      error.value = "无法加载操作日志。";
    }
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

const onBookChange = () => {
  loadRequestVersion += 1;
  logs.value = [];
  loading.value = false;
  error.value = "";
  void load();
};

onMounted(async () => {
  try {
    await loadBooks();
    await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .filters { flex-direction: column; align-items: stretch; } .heading { flex-direction: column; } }
</style>
