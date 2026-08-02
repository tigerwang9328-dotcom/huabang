<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证分析</p>
        <h2>凭证汇总</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿已导入的已过账凭证按凭证字/月份聚合，只读查询。" : "按凭证字/月份聚合当前账凭证发生额;前端派生展示。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="load">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-select v-model="monthFilter" placeholder="按月份过滤" clearable>
        <el-option v-for="m in monthOptions" :key="m" :label="m" :value="m" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-empty v-else-if="!bookId" description="请先选择独立账簿" />

    <el-table
      v-else
      :data="summaryRows"
      empty-text="暂无凭证数据"
      stripe
      show-summary
      :summary-method="summaryMethod"
    >
      <el-table-column type="expand" width="52">
        <template #default="{ row }">
          <div class="voucher-details">
            <p>该月份、该凭证字下的全部凭证</p>
            <el-table :data="row.vouchers" size="small" stripe>
              <el-table-column prop="voucher_no" label="凭证号" min-width="130" />
              <el-table-column prop="voucher_date" label="日期" width="120" />
              <el-table-column prop="summary" label="摘要" min-width="220" show-overflow-tooltip />
              <el-table-column label="状态" width="100">
                <template #default="detail">{{ statusLabel(detail.row.status) }}</template>
              </el-table-column>
              <el-table-column label="借方" width="140" align="right">
                <template #default="detail">{{ money(detail.row.total_debit) }}</template>
              </el-table-column>
              <el-table-column label="贷方" width="140" align="right">
                <template #default="detail">{{ money(detail.row.total_credit) }}</template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="month" label="月份" width="120" />
      <el-table-column prop="voucher_type" label="凭证字" width="120" />
      <el-table-column prop="count" label="凭证数" width="100" align="center" />
      <el-table-column label="借方合计" align="right">
        <template #default="scope">{{ money(scope.row.total_debit) }}</template>
      </el-table-column>
      <el-table-column label="贷方合计" align="right">
        <template #default="scope">{{ money(scope.row.total_credit) }}</template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref } from "vue";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceVoucher,
} from "@/api/mumarenFinanceCenter";

const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const vouchers = ref<MumarenFinanceVoucher[]>([]);
const monthFilter = ref("");
const error = ref("");
const loading = ref(false);
let loadRequestVersion = 0;

const money = (value?: number | string) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value) || 0);

const statusLabel = (status: MumarenFinanceVoucher["status"]) =>
  ({ draft: "草稿", reviewed: "已审核", posted: "已过账" }[status]);

// 凭证字:voucher_no 第一个分隔符前的部分,如 "记" 或 "转";无分隔符时取前导非数字字符。
const extractVoucherType = (voucherNo: string): string => {
  if (!voucherNo) return "";
  const parts = voucherNo.split(/[-_－/:：]/);
  if (parts.length > 1) return parts[0];
  const match = voucherNo.match(/^[^\d]+/);
  return match ? match[0] : voucherNo;
};

interface SummaryRow {
  month: string;
  voucher_type: string;
  count: number;
  total_debit: number;
  total_credit: number;
  vouchers: MumarenFinanceVoucher[];
}

const summaryRows = computed<SummaryRow[]>(() => {
  const map = new Map<string, SummaryRow>();
  for (const v of vouchers.value) {
    const month = (v.voucher_date || "").slice(0, 7);
    const voucherType = extractVoucherType(v.voucher_no || "");
    const key = `${month}|${voucherType}`;
    if (!map.has(key)) {
      map.set(key, { month, voucher_type: voucherType, count: 0, total_debit: 0, total_credit: 0, vouchers: [] });
    }
    const row = map.get(key)!;
    row.count += 1;
    row.total_debit += Number(v.total_debit) || 0;
    row.total_credit += Number(v.total_credit) || 0;
    row.vouchers.push(v);
  }
  return Array.from(map.values())
    .filter((r) => !monthFilter.value || r.month === monthFilter.value)
    .sort((a, b) =>
      a.month < b.month ? -1 : a.month > b.month ? 1 : a.voucher_type.localeCompare(b.voucher_type),
    );
});

const monthOptions = computed(() => {
  const set = new Set<string>();
  for (const v of vouchers.value) {
    set.add((v.voucher_date || "").slice(0, 7));
  }
  return Array.from(set).sort();
});

const summaryMethod = ({ columns }: { columns: Array<Record<string, unknown>> }) => {
  return columns.map((_, index) => {
    const label = String(columns[index].label || "");
    if (label === "月份") return "合计";
    if (label === "凭证数") return String(summaryRows.value.reduce((s, r) => s + r.count, 0));
    if (label === "借方合计") return money(summaryRows.value.reduce((s, r) => s + r.total_debit, 0));
    if (label === "贷方合计") return money(summaryRows.value.reduce((s, r) => s + r.total_credit, 0));
    return "";
  });
};

const load = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId) {
    vouchers.value = [];
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const response = await mumarenFinanceCenterApi.listVouchers({ book_id: requestedBookId, limit: 500 });
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) {
      vouchers.value = response.data.data;
    }
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) {
      error.value = "无法加载独立账簿凭证。";
    }
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
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
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
.voucher-details { padding: 8px 24px 16px; }
.voucher-details p { margin: 0 0 8px; font-size: 13px; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
