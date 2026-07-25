<template>
  <div class="history-finance">
    <header class="page-header">
      <div>
        <h1>历史财务</h1>
        <p>金蝶 K/3 WISE 只读账套</p>
      </div>
      <el-tag :type="qualityTagType" effect="plain">{{ statusLabel(currentStatus) }}</el-tag>
    </header>

    <el-tabs v-model="activeTab" class="history-tabs" @tab-change="changeTab">
      <el-tab-pane label="历史账套" name="account-sets" />
      <el-tab-pane label="财务报表" name="statements" />
      <el-tab-pane label="科目余额" name="account-balances" />
      <el-tab-pane label="凭证查询" name="vouchers" />
      <el-tab-pane label="数据质量" name="data-quality" />
    </el-tabs>

    <div v-if="activeTab !== 'account-sets'" class="filter-bar">
      <el-select v-model="accountSetCode" placeholder="选择账套" filterable @change="accountSetChanged">
        <el-option v-for="item in accountSets" :key="item.account_set_code" :label="item.company_name" :value="item.account_set_code" />
      </el-select>
      <el-select v-if="needsPeriod" v-model="period" placeholder="选择期间" @change="loadActiveView">
        <el-option v-for="item in periods" :key="item.period" :label="item.period" :value="item.period" />
      </el-select>
      <el-input v-if="activeTab === 'account-balances' || activeTab === 'vouchers'" v-model="keyword" clearable placeholder="科目或凭证号" @keyup.enter="search">
        <template #append><el-button :icon="Search" aria-label="查询" @click="search" /></template>
      </el-input>
      <el-button :icon="Refresh" circle aria-label="刷新" @click="loadActiveView" />
    </div>


    <section v-loading="loading" class="table-section">
      <el-table v-if="activeTab === 'account-sets'" :data="accountSets" stripe>
        <el-table-column prop="account_set_code" label="账套编码" min-width="170" />
        <el-table-column prop="company_name" label="公司名称" min-width="220" />
        <el-table-column prop="short_name" label="简称" min-width="120" />
        <el-table-column prop="start_period" label="启用期间" width="110" />
        <el-table-column prop="current_period" label="截止期间" width="110" />
        <el-table-column label="状态" width="100"><template #default><el-tag type="success" effect="plain">正式</el-tag></template></el-table-column>
      </el-table>

      <template v-else-if="activeTab === 'statements'">
        <el-radio-group v-model="statementType" class="statement-switch" @change="loadStatements">
          <el-radio-button label="balance_sheet">资产负债表</el-radio-button>
          <el-radio-button label="profit">利润表</el-radio-button>
          <el-radio-button label="cashflow">现金流量表</el-radio-button>
        </el-radio-group>
        <el-table :data="statement.items" stripe>
          <el-table-column prop="line_code" label="行次" width="100" />
          <el-table-column prop="line_name" label="项目" min-width="240" />
          <el-table-column label="本期金额" min-width="150" align="right"><template #default="scope"><el-button link type="primary" @click="drillStatement(scope.row)">{{ money(scope.row.current_amount) }}</el-button></template></el-table-column>
          <el-table-column label="本年累计" min-width="150" align="right"><template #default="scope"><el-button link type="primary" @click="drillStatement(scope.row)">{{ money(scope.row.year_to_date_amount) }}</el-button></template></el-table-column>
        </el-table>
      </template>

      <el-table v-else-if="activeTab === 'account-balances'" :data="balances.items" stripe>
        <el-table-column prop="account_code" label="科目编码" width="130" fixed />
        <el-table-column prop="account_name" label="科目名称" min-width="200" fixed />
        <el-table-column label="期初借" width="130" align="right"><template #default="scope">{{ money(scope.row.opening_debit) }}</template></el-table-column>
        <el-table-column label="期初贷" width="130" align="right"><template #default="scope">{{ money(scope.row.opening_credit) }}</template></el-table-column>
        <el-table-column label="本期借" width="130" align="right"><template #default="scope"><el-button link type="primary" @click="drillBalance(scope.row)">{{ money(scope.row.period_debit) }}</el-button></template></el-table-column>
        <el-table-column label="本期贷" width="130" align="right"><template #default="scope"><el-button link type="primary" @click="drillBalance(scope.row)">{{ money(scope.row.period_credit) }}</el-button></template></el-table-column>
        <el-table-column label="期末借" width="130" align="right"><template #default="scope">{{ money(scope.row.closing_debit) }}</template></el-table-column>
        <el-table-column label="期末贷" width="130" align="right"><template #default="scope">{{ money(scope.row.closing_credit) }}</template></el-table-column>
      </el-table>

      <el-table v-else-if="activeTab === 'vouchers'" :data="vouchers.items" stripe @row-click="openVoucher">
        <el-table-column prop="voucher_date" label="日期" width="120" />
        <el-table-column prop="voucher_no" label="凭证号" min-width="160" />
        <el-table-column prop="source_status" label="原状态" width="110" />
        <el-table-column label="借方合计" min-width="150" align="right"><template #default="scope">{{ money(scope.row.total_debit) }}</template></el-table-column>
        <el-table-column label="贷方合计" min-width="150" align="right"><template #default="scope">{{ money(scope.row.total_credit) }}</template></el-table-column>
        <el-table-column label="模式" width="100"><template #default><el-tag effect="plain">只读</el-tag></template></el-table-column>
      </el-table>

      <template v-else>
        <div class="quality-summary">
          <div><span>科目数</span><strong>{{ quality.account_count ?? "-" }}</strong></div>
          <div><span>已确认映射</span><strong>{{ quality.mapped_account_count ?? "-" }}</strong></div>
          <div><span>待处理问题</span><strong>{{ quality.issues?.length ?? 0 }}</strong></div>
        </div>
        <el-table :data="quality.issues || []" stripe>
          <el-table-column prop="code" label="问题" min-width="220" />
          <el-table-column prop="severity" label="级别" width="120" />
          <el-table-column prop="count" label="数量" width="120" />
        </el-table>
        <h2 class="section-title">导入批次</h2>
        <el-table :data="batches" stripe>
          <el-table-column prop="batch_id" label="批次" min-width="240" />
          <el-table-column prop="source_database" label="来源账套" min-width="170" />
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column prop="completed_at" label="完成时间" min-width="190" />
          <el-table-column label="SHA-256" min-width="190"><template #default="scope"><code>{{ shortHash(scope.row.backup_sha256) }}</code></template></el-table-column>
        </el-table>
      </template>
    </section>

    <el-pagination v-if="showPagination" v-model:current-page="page" :page-size="50" :total="activeTab === 'vouchers' ? vouchers.total : balances.total" layout="total, prev, pager, next" @current-change="loadActiveView" />

    <el-drawer v-model="voucherDrawer" size="min(760px, 92vw)" title="凭证详情">
      <template v-if="voucherDetail">
        <div class="voucher-meta"><strong>{{ voucherDetail.voucher_no }}</strong><span>{{ voucherDetail.voucher_date }}</span><el-tag effect="plain">read_only</el-tag></div>
        <el-table :data="voucherDetail.entries" stripe>
          <el-table-column prop="account_code" label="科目" width="120" />
          <el-table-column prop="account_name" label="科目名称" min-width="150" />
          <el-table-column prop="summary" label="摘要" min-width="220" />
          <el-table-column label="借方" width="120" align="right"><template #default="scope">{{ money(scope.row.debit_amount) }}</template></el-table-column>
          <el-table-column label="贷方" width="120" align="right"><template #default="scope">{{ money(scope.row.credit_amount) }}</template></el-table-column>
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { kingdeeFinanceApi, type AccountBalance, type AccountSet, type DataQuality, type FinancePeriod, type FinanceQualityStatus, type ImportBatch, type PageResult, type StatementResult, type VoucherDetail, type VoucherListItem } from "@/api/kingdeeFinance";

const route = useRoute();
const router = useRouter();
const tabs = ["account-sets", "statements", "account-balances", "vouchers", "data-quality"] as const;
type TabName = typeof tabs[number];
const routeTab = () => String(route.meta.financeTab || "account-sets") as TabName;

const activeTab = ref<TabName>(routeTab());
const accountSets = ref<AccountSet[]>([]);
const periods = ref<FinancePeriod[]>([]);
const accountSetCode = ref("");
const period = ref("");
const keyword = ref("");
const statementType = ref("balance_sheet");
const statement = ref<StatementResult>({ status: "pending_data", items: [], issues: [] });
const balances = ref<PageResult<AccountBalance>>({ items: [], total: 0, page: 1, page_size: 50 });
const vouchers = ref<PageResult<VoucherListItem>>({ items: [], total: 0, page: 1, page_size: 50 });
const quality = ref<Partial<DataQuality>>({ status: "pending_data", issues: [] });
const batches = ref<ImportBatch[]>([]);
const voucherDetail = ref<VoucherDetail | null>(null);
const voucherDrawer = ref(false);
const loading = ref(false);
const page = ref(1);
const statementLineCode = ref("");
const balanceStatementType = ref("");
const voucherAccountCode = ref("");

const needsPeriod = computed(() => activeTab.value === "statements" || activeTab.value === "account-balances");
const showPagination = computed(() => activeTab.value === "account-balances" || activeTab.value === "vouchers");
const currentStatus = computed<FinanceQualityStatus>(() => activeTab.value === "statements" ? statement.value.status : activeTab.value === "data-quality" ? quality.value.status || "pending_data" : accountSets.value.length ? "ready" : "pending_data");
const qualityTagType = computed(() => currentStatus.value === "ready" ? "success" : currentStatus.value === "pending_mapping" ? "warning" : "info");
const statusLabel = (status: FinanceQualityStatus) => ({ ready: "数据已就绪", pending_mapping: "映射待确认", pending_data: "数据待接入" }[status]);
const money = (value: number | null | undefined) => value == null ? "-" : new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
const shortHash = (value: string) => value ? `${value.slice(0, 12)}...${value.slice(-8)}` : "-";

const unwrap = <T,>(response: { data: { data: T } }) => response.data.data;

const loadAccountSets = async () => {
  accountSets.value = unwrap(await kingdeeFinanceApi.getAccountSets());
  if (!accountSetCode.value && accountSets.value.length) accountSetCode.value = accountSets.value[0].account_set_code;
};

const loadPeriods = async () => {
  if (!accountSetCode.value) return;
  periods.value = unwrap(await kingdeeFinanceApi.getPeriods(accountSetCode.value));
  if (!periods.value.some((item) => item.period === period.value)) period.value = periods.value.at(-1)?.period || "";
};

const loadStatements = async () => {
  if (!accountSetCode.value || !period.value) return;
  statement.value = unwrap(await kingdeeFinanceApi.getStatements({ account_set_code: accountSetCode.value, period: period.value, statement_type: statementType.value }));
};

const loadActiveView = async () => {
  loading.value = true;
  try {
    if (activeTab.value === "account-sets") await loadAccountSets();
    if (activeTab.value === "statements") await loadStatements();
    if (activeTab.value === "account-balances" && accountSetCode.value && period.value) balances.value = unwrap(await kingdeeFinanceApi.getAccountBalances({ account_set_code: accountSetCode.value, period: period.value, keyword: keyword.value || undefined, statement_type: balanceStatementType.value || undefined, statement_line_code: statementLineCode.value || undefined, page: page.value, page_size: 50 }));
    if (activeTab.value === "vouchers" && accountSetCode.value) vouchers.value = unwrap(await kingdeeFinanceApi.getVouchers({ account_set_code: accountSetCode.value, period: period.value || undefined, keyword: keyword.value || undefined, account_code: voucherAccountCode.value || undefined, page: page.value, page_size: 50 }));
    if (activeTab.value === "data-quality") {
      quality.value = unwrap(await kingdeeFinanceApi.getDataQuality(accountSetCode.value || undefined));
      batches.value = unwrap(await kingdeeFinanceApi.getImportBatches());
    }
  } catch (error) {
    ElMessage.error("历史财务数据加载失败");
  } finally {
    loading.value = false;
  }
};

const accountSetChanged = async () => { page.value = 1; statementLineCode.value = ""; balanceStatementType.value = ""; voucherAccountCode.value = ""; await loadPeriods(); await loadActiveView(); };
const search = () => { page.value = 1; statementLineCode.value = ""; balanceStatementType.value = ""; voucherAccountCode.value = ""; loadActiveView(); };
const changeTab = (name: string | number) => router.push(`/app/fin/history/${String(name)}`);
const openVoucher = async (row: VoucherListItem) => { voucherDetail.value = unwrap(await kingdeeFinanceApi.getVoucher(row.id)); voucherDrawer.value = true; };
const drillStatement = (row: { line_code: string }) => { statementLineCode.value = row.line_code; balanceStatementType.value = statementType.value; page.value = 1; router.push("/app/fin/history/account-balances"); };
const drillBalance = (row: AccountBalance) => { voucherAccountCode.value = row.account_code; page.value = 1; router.push("/app/fin/history/vouchers"); };

watch(() => route.meta.financeTab, async () => {
  activeTab.value = routeTab();
  page.value = 1;
  await loadActiveView();
});

onMounted(async () => {
  loading.value = true;
  try { await loadAccountSets(); await loadPeriods(); await loadActiveView(); } finally { loading.value = false; }
});
</script>

<style scoped>
.history-finance { min-width: 0; color: #1f2937; }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 8px; }
.page-header h1 { margin: 0; font-size: 24px; line-height: 1.3; letter-spacing: 0; }
.page-header p { margin: 4px 0 0; color: #6b7280; font-size: 13px; }
.history-tabs { margin-top: 4px; }
.filter-bar { display: grid; grid-template-columns: minmax(220px, 1.2fr) minmax(140px, .7fr) minmax(220px, 1fr) 40px; gap: 10px; align-items: center; margin: 14px 0; }
.table-section { min-height: 280px; margin-top: 14px; }
.statement-switch { margin-bottom: 14px; }
.quality-summary { display: grid; grid-template-columns: repeat(3, minmax(140px, 1fr)); border-top: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb; margin-bottom: 16px; }
.quality-summary div { padding: 16px 18px; border-right: 1px solid #e5e7eb; }
.quality-summary div:last-child { border-right: 0; }
.quality-summary span { display: block; color: #6b7280; font-size: 13px; }
.quality-summary strong { display: block; margin-top: 6px; font-size: 24px; letter-spacing: 0; }
.section-title { margin: 24px 0 10px; font-size: 16px; letter-spacing: 0; }
.voucher-meta { display: flex; gap: 14px; align-items: center; margin-bottom: 16px; }
code { font-family: Consolas, monospace; font-size: 12px; }
:deep(.el-table__row) { cursor: default; }
:deep(.el-pagination) { justify-content: flex-end; margin-top: 16px; }
@media (max-width: 760px) {
  .filter-bar { grid-template-columns: 1fr 1fr; }
  .filter-bar :deep(.el-input) { grid-column: 1 / -1; }
  .quality-summary { grid-template-columns: 1fr; }
  .quality-summary div { border-right: 0; border-bottom: 1px solid #e5e7eb; }
  .page-header { align-items: flex-start; }
}
</style>
