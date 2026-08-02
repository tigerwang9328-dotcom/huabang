<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证流程</p>
        <h2>查凭证</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿凭证；永久只读，仅供核对。" : "独立当前账凭证列表:草稿 → 审核 → 人工过账。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button :disabled="!vouchers.length" @click="exportVouchers">导出当前列表</el-button>
        <router-link to="/app/finance-center/mumaren/vouchers/create">
          <el-button type="primary" :disabled="isReadonly">录入新凭证</el-button>
        </router-link>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-else :data="vouchers" :empty-text="isReadonly ? '该金蝶迁移账簿暂无凭证' : '暂无独立当前账凭证'" stripe>
      <el-table-column prop="voucher_no" label="凭证号" min-width="130" />
      <el-table-column prop="voucher_date" label="日期" width="120" />
      <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
      <el-table-column label="状态" width="110">
        <template #default="scope">
          <el-tag v-if="isReadonly" type="info" size="small">金蝶迁移</el-tag>
          <el-tag v-else :type="statusTagType(scope.row.status)" size="small">{{ statusLabel(scope.row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="140" align="right">
        <template #default="scope">{{ money(scope.row.total_debit) }}</template>
      </el-table-column>
      <el-table-column label="贷方" width="140" align="right">
        <template #default="scope">{{ money(scope.row.total_credit) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="scope">
          <el-button v-if="scope.row.status === 'draft'" size="small" link type="primary" :disabled="isReadonly" :loading="actingId === scope.row.id" @click="review(scope.row)">审核</el-button>
          <el-popconfirm v-if="scope.row.status === 'draft' && !isReadonly" title="确定删除该草稿凭证？此操作不可恢复。" @confirm="remove(scope.row)">
            <template #reference><el-button size="small" link type="danger" :loading="actingId === scope.row.id">删除</el-button></template>
          </el-popconfirm>
          <el-button v-if="scope.row.status === 'reviewed'" size="small" link type="success" :disabled="isReadonly" :loading="actingId === scope.row.id" @click="post(scope.row)">人工过账</el-button>
          <span v-if="scope.row.status === 'posted'" class="done-text">已过账</span>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceVoucher,
} from "@/api/mumarenFinanceCenter";

const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const vouchers = ref<MumarenFinanceVoucher[]>([]);
const error = ref("");
const loading = ref(false);
const actingId = ref<number>(); // 当前正在审核/过账的凭证 id

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const statusLabel = (s: string) => ({ draft: "草稿", reviewed: "已审核", posted: "已过账" }[s] || s);
const statusTagType = (s: string): "" | "warning" | "success" => (s === "draft" ? "" : s === "reviewed" ? "warning" : "success");

const load = async () => {
  loading.value = true;
  error.value = "";
  try {
    vouchers.value = (await mumarenFinanceCenterApi.listVouchers(bookId.value ? { book_id: bookId.value } : undefined)).data.data;
  } catch {
    error.value = "无法加载独立当前账凭证。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = async () => {
  await load();
};

const exportVouchers = () => {
  const quote = (value: unknown) => {
    let text = String(value ?? "");
    if (/^[=+@-]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  };
  const rows = [
    ["凭证号", "日期", "摘要", "状态", "借方", "贷方"],
    ...vouchers.value.map((row) => [
      row.voucher_no,
      row.voucher_date,
      row.summary,
      statusLabel(row.status),
      money(row.total_debit),
      money(row.total_credit),
    ]),
  ];
  const blob = new Blob([`\uFEFF${rows.map((row) => row.map(quote).join(",")).join("\r\n")}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `独立财务凭证-${bookId.value || "全部"}.csv`;
  link.click();
  URL.revokeObjectURL(url);
};

onMounted(async () => {
  try {
    await loadBooks();
  } catch {
    error.value = "无法加载独立账簿。";
  }
  await load();
});

// ── 审核与人工过账(状态机:draft → reviewed → posted,禁止反向) ──
const review = async (row: MumarenFinanceVoucher) => {
  if (isReadonly.value) return;
  actingId.value = row.id;
  try {
    await mumarenFinanceCenterApi.reviewVoucher(row.id);
    ElMessage.success("凭证已审核");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "审核失败");
  } finally {
    actingId.value = undefined;
  }
};

const remove = async (row: MumarenFinanceVoucher) => {
  if (isReadonly.value || row.status !== "draft") return;
  actingId.value = row.id;
  try {
    await mumarenFinanceCenterApi.deleteVoucher(row.id);
    ElMessage.success("草稿凭证已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const post = async (row: MumarenFinanceVoucher) => {
  if (isReadonly.value) return;
  actingId.value = row.id;
  try {
    await mumarenFinanceCenterApi.postVoucher(row.id);
    ElMessage.success("凭证已人工过账");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "过账失败");
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
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
