<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证分析</p>
        <h2>凭证汇总</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿已导入的已过账凭证按会计期间和真实凭证字汇总，只读查询。" : "按会计期间和真实凭证字汇总；默认只显示已过账凭证。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button>
        <el-button :disabled="!summary.rows.length" @click="exportCsv">导出汇总</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="load">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-select v-model="monthFilter" placeholder="全部期间" clearable>
        <el-option v-for="period in summary.available_periods" :key="period" :label="period" :value="period" />
      </el-select>
      <el-select v-model="status" placeholder="凭证状态">
        <el-option label="已过账" value="posted" />
        <el-option label="已审核" value="reviewed" />
        <el-option label="草稿" value="draft" />
      </el-select>
      <el-select v-model="voucherTypeFilter" placeholder="全部凭证字" clearable>
        <el-option v-for="type in summary.available_voucher_types" :key="type" :label="type" :value="type" />
      </el-select>
      <el-input v-model="keyword" clearable placeholder="凭证号或摘要" @keyup.enter="load" />
      <el-button @click="resetFilters">重置</el-button>
    </div>

    <el-alert
      v-if="status !== 'posted'"
      title="当前为非正式凭证汇总，不代表正式账簿数据。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-empty v-else-if="!bookId" description="请先选择独立账簿" />

    <template v-else>
      <div class="summary-cards">
        <div><span>凭证数</span><strong>{{ summary.total_voucher_count }}</strong></div>
        <div><span>借方合计</span><strong>{{ money(summary.total_debit) }}</strong></div>
        <div><span>贷方合计</span><strong>{{ money(summary.total_credit) }}</strong></div>
        <div><span>借贷状态</span><el-tag :type="summary.is_balanced ? 'success' : 'danger'">{{ summary.is_balanced ? '平衡' : '不平衡' }}</el-tag></div>
      </div>

      <el-alert v-if="summary.rows.some((row) => !row.is_balanced)" title="存在借贷不平的凭证汇总行，请展开核查。" type="error" :closable="false" show-icon />

      <el-table
        ref="summaryTable"
        :data="summary.rows"
        :row-key="summaryRowKey"
        empty-text="暂无符合条件的凭证"
        stripe
        show-summary
        :summary-method="summaryMethod"
        @expand-change="onExpand"
      >
        <el-table-column type="expand" width="52">
          <template #default="{ row }">
            <div class="voucher-details">
              <el-table :data="detailPage(row).items" size="small" stripe v-loading="detailLoading[summaryRowKey(row)]">
                <el-table-column prop="voucher_no" label="凭证号" min-width="150">
                  <template #default="detail">
                    <el-button link type="primary" @click="openVoucher(detail.row)">{{ detail.row.voucher_no }}</el-button>
                  </template>
                </el-table-column>
                <el-table-column prop="voucher_date" label="日期" width="120" />
                <el-table-column prop="summary" label="摘要" min-width="220" show-overflow-tooltip />
                <el-table-column label="借方" width="140" align="right"><template #default="detail">{{ money(detail.row.total_debit) }}</template></el-table-column>
                <el-table-column label="贷方" width="140" align="right"><template #default="detail">{{ money(detail.row.total_credit) }}</template></el-table-column>
              </el-table>
              <el-pagination
                v-if="detailPage(row).total > detailPage(row).limit"
                small layout="prev, pager, next, total" :page-size="detailPage(row).limit"
                :current-page="Math.floor(detailPage(row).offset / detailPage(row).limit) + 1"
                :total="detailPage(row).total" @current-change="(page: number) => loadDetails(row, (page - 1) * detailPage(row).limit)"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="period" label="期间" width="120" />
        <el-table-column label="凭证字" width="120">
          <template #default="scope"><el-tag :type="scope.row.voucher_type === '未设置' ? 'warning' : 'info'">{{ scope.row.voucher_type }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="voucher_count" label="凭证数" width="100" align="center" />
        <el-table-column label="借方合计" align="right"><template #default="scope">{{ money(scope.row.total_debit) }}</template></el-table-column>
        <el-table-column label="贷方合计" align="right"><template #default="scope">{{ money(scope.row.total_credit) }}</template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="scope"><el-button link type="primary" @click="showDetails(scope.row)">展开</el-button></template></el-table-column>
      </el-table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceVoucher,
  type MumarenVoucherSummary,
  type MumarenVoucherSummaryDetailPage,
  type MumarenVoucherSummaryRow,
} from "@/api/mumarenFinanceCenter";

const router = useRouter();
const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const status = ref<MumarenFinanceVoucher["status"]>("posted");
const monthFilter = ref("");
const voucherTypeFilter = ref("");
const keyword = ref("");
const loading = ref(false);
const error = ref("");
const summary = ref<MumarenVoucherSummary>({ rows: [], total_voucher_count: 0, total_debit: 0, total_credit: 0, is_balanced: true, available_periods: [], available_voucher_types: [] });
const details = ref<Record<string, MumarenVoucherSummaryDetailPage>>({});
const detailLoading = ref<Record<string, boolean>>({});
const summaryTable = ref<{ toggleRowExpansion: (row: MumarenVoucherSummaryRow, expanded: boolean) => void } | null>(null);
const loadRequestVersion = ref(0);
const detailRequestVersion = ref<Record<string, number>>({});

const money = (value?: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const summaryRowKey = (row: MumarenVoucherSummaryRow) => `${row.period}|${row.voucher_type}`;
const currentParams = () => ({ book_id: bookId.value!, status: status.value, period: monthFilter.value || undefined, voucher_type: voucherTypeFilter.value || undefined, keyword: keyword.value.trim() || undefined });
const detailPage = (row: MumarenVoucherSummaryRow): MumarenVoucherSummaryDetailPage => details.value[summaryRowKey(row)] || { items: [], total: 0, offset: 0, limit: 20 };

const load = async () => {
  const requestVersion = ++loadRequestVersion.value;
  if (!bookId.value) {
    summary.value = { rows: [], total_voucher_count: 0, total_debit: 0, total_credit: 0, is_balanced: true, available_periods: [], available_voucher_types: [] };
    details.value = {};
    detailRequestVersion.value = {};
    loading.value = false;
    error.value = "";
    return;
  }
  loading.value = true;
  error.value = "";
  details.value = {};
  try {
    const response = await mumarenFinanceCenterApi.getVoucherSummary(currentParams());
    if (requestVersion !== loadRequestVersion.value) return;
    summary.value = response.data.data;
  } catch {
    if (requestVersion === loadRequestVersion.value) error.value = "无法加载凭证汇总。";
  } finally {
    if (requestVersion === loadRequestVersion.value) loading.value = false;
  }
};

const resetFilters = async () => { monthFilter.value = ""; status.value = "posted"; voucherTypeFilter.value = ""; keyword.value = ""; await load(); };

const loadDetails = async (row: MumarenVoucherSummaryRow, offset = 0) => {
  if (!bookId.value) return;
  const key = summaryRowKey(row);
  const requestVersion = (detailRequestVersion.value[key] || 0) + 1;
  const summaryVersion = loadRequestVersion.value;
  detailRequestVersion.value[key] = requestVersion;
  detailLoading.value[key] = true;
  try {
    const response = await mumarenFinanceCenterApi.getVoucherSummaryDetails({ ...currentParams(), period: row.period, voucher_type: row.voucher_type, offset, limit: 20 });
    if (summaryVersion !== loadRequestVersion.value || requestVersion !== detailRequestVersion.value[key]) return;
    details.value[key] = response.data.data;
  } finally {
    if (summaryVersion === loadRequestVersion.value && requestVersion === detailRequestVersion.value[key]) detailLoading.value[key] = false;
  }
};

const onExpand = (row: MumarenVoucherSummaryRow, expandedRows: MumarenVoucherSummaryRow[]) => {
  if (expandedRows.some((item) => summaryRowKey(item) === summaryRowKey(row)) && !details.value[summaryRowKey(row)]) void loadDetails(row);
};

const showDetails = (row: MumarenVoucherSummaryRow) => {
  summaryTable.value?.toggleRowExpansion(row, true);
};

const openVoucher = (voucher: MumarenFinanceVoucher) => router.push({ path: "/app/finance-center/mumaren/vouchers/list", query: { book_id: String(voucher.book_id), voucher_id: String(voucher.id) } });

const summaryMethod = ({ columns }: { columns: Array<Record<string, unknown>> }) => columns.map((column) => {
  const label = String(column.label || "");
  if (label === "期间") return "合计";
  if (label === "凭证数") return String(summary.value.total_voucher_count);
  if (label === "借方合计") return money(summary.value.total_debit);
  if (label === "贷方合计") return money(summary.value.total_credit);
  return "";
});

const exportCsv = () => {
  const quote = (value: unknown) => { let text = String(value ?? ""); if (/^[=+@-]/.test(text)) text = `'${text}`; return `"${text.replace(/"/g, '""')}"`; };
  const rows = [["期间", "凭证字", "凭证数", "借方合计", "贷方合计"], ...summary.value.rows.map((row) => [row.period, row.voucher_type, row.voucher_count, money(row.total_debit), money(row.total_credit)]), ["合计", "", summary.value.total_voucher_count, money(summary.value.total_debit), money(summary.value.total_credit)]];
  const url = URL.createObjectURL(new Blob([`\uFEFF${rows.map((row) => row.map(quote).join(",")).join("\r\n")}`], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a"); link.href = url; link.download = `凭证汇总-${bookId.value}-${status.value}.csv`; link.click(); URL.revokeObjectURL(url);
};

onMounted(async () => { try { await loadBooks(); await load(); } catch { error.value = "无法加载独立账簿。"; } });
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions, .filters { display: flex; gap: 12px; flex-wrap: wrap; }
.filters > * { width: 190px; } .filters > .el-input { width: 240px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; } h2 { margin: 8px 0; } p { color: #5d6b7e; }
.summary-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.summary-cards > div { padding: 14px 16px; border: 1px solid #e6edf5; border-radius: 10px; background: #f9fbfe; display: grid; gap: 6px; } .summary-cards span { color: #66758a; font-size: 13px; } .summary-cards strong { color: #18283c; font-size: 20px; }
.voucher-details { padding: 10px 20px 18px; display: grid; gap: 12px; }
@media (max-width: 768px) { .heading { flex-direction: column; } .filters > *, .filters > .el-input { width: 100%; } .summary-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
