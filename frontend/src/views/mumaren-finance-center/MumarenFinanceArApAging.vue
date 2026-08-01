<template>
  <section class="panel">
    <div class="heading">
      <div><p class="panel-kicker">独立往来账</p><h2>账龄分析</h2><p>按账簿、应收或应付分别查看未结余额与账龄区间；历史迁移账簿仅查询。</p></div>
      <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
    </div>
    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable><el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" /></el-select>
      <el-radio-group v-model="orderType"><el-radio-button label="receivable">应收账龄</el-radio-button><el-radio-button label="payable">应付账龄</el-radio-button></el-radio-group>
      <el-date-picker v-model="asOf" type="date" value-format="YYYY-MM-DD" placeholder="截止日" clearable />
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <template v-else-if="aging">
      <el-descriptions :column="2" border><el-descriptions-item label="截止日">{{ aging.as_of }}</el-descriptions-item><el-descriptions-item label="未结余额">{{ money(aging.total_balance) }}</el-descriptions-item></el-descriptions>
      <el-row :gutter="12"><el-col v-for="bucket in buckets" :key="bucket" :xs="12" :sm="4"><el-card shadow="never" class="bucket"><span>{{ bucket }}</span><strong>{{ money(aging.buckets[bucket] || 0) }}</strong></el-card></el-col></el-row>
      <el-card shadow="never"><template #header>往来单位未结余额</template>
        <el-table :data="aging.counterparties" v-loading="loading" empty-text="暂无未结往来余额" stripe>
          <el-table-column prop="counterparty_name" :label="orderType === 'receivable' ? '客户' : '供应商'" min-width="180" />
          <el-table-column v-for="bucket in buckets" :key="bucket" :label="bucket" width="120" align="right"><template #default="scope">{{ money(scope.row[bucket] || 0) }}</template></el-table-column>
          <el-table-column label="未结余额" width="130" align="right"><template #default="scope">{{ money(scope.row.total_balance) }}</template></el-table-column>
        </el-table>
      </el-card>
      <el-card shadow="never"><template #header>单据明细</template>
        <el-table :data="orderRows" empty-text="暂无未结单据" stripe><el-table-column prop="counterparty_name" :label="orderType === 'receivable' ? '客户' : '供应商'" min-width="160" /><el-table-column prop="order_no" label="单号" min-width="140" /><el-table-column prop="order_date" label="单据日期" width="120" /><el-table-column prop="days" label="账龄(天)" width="100" align="right" /><el-table-column prop="bucket" label="账龄区间" width="120" /><el-table-column label="未结余额" width="130" align="right"><template #default="scope">{{ money(scope.row.balance) }}</template></el-table-column></el-table>
      </el-card>
    </template>
    <el-empty v-else-if="!loading" description="请选择独立账簿后查询账龄" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { mumarenFinanceCenterApi, type MumarenArApAging } from "@/api/mumarenFinanceCenter";

const buckets = ["0-30天", "31-60天", "61-90天", "91-120天", "120天以上"];
const { books, bookId, loadBooks } = useMumarenFinanceBook();
const orderType = ref<"receivable" | "payable">("receivable");
const asOf = ref("");
const aging = ref<MumarenArApAging>();
const loading = ref(false);
const error = ref("");
let loadRequestVersion = 0;
const money = (value: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const orderRows = computed(() => (aging.value?.counterparties || []).flatMap((counterparty) => (counterparty.orders || []).map((order) => ({ ...order, counterparty_name: counterparty.counterparty_name }))));
const load = async () => {
  const requestedBookId = bookId.value;
  const requestedOrderType = orderType.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId) { aging.value = undefined; loading.value = false; error.value = ""; return; }
  loading.value = true; error.value = "";
  try {
    const response = await mumarenFinanceCenterApi.getArApAging({ book_id: requestedBookId, order_type: requestedOrderType, as_of: asOf.value || undefined });
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || requestedOrderType !== orderType.value) return;
    aging.value = response.data.data;
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value && requestedOrderType === orderType.value) error.value = "无法加载独立账龄分析。";
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};
watch(bookId, load); watch(orderType, load); watch(asOf, load);
onMounted(async () => { try { await loadBooks(); await load(); } catch { error.value = "无法加载独立账簿。"; } });
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }.heading, .filters { display: flex; gap: 12px; align-items: center; }.heading { justify-content: space-between; align-items: flex-start; }.filters { flex-wrap: wrap; }.bucket { text-align: center; color: #5d6b7e; }.bucket strong { display: block; margin-top: 6px; color: #172033; font-size: 17px; }.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }h2 { margin: 8px 0; }p { color: #5d6b7e; }@media (max-width: 640px) { .filters, .heading { align-items: stretch; flex-direction: column; } }
</style>
