<template>
  <div class="member-page command-light-page">
    <section class="member-header">
      <div>
        <div class="eyebrow">协同 / 会员运营</div>
        <h1>会员运营</h1>
        <p>基于百胜小票会员线索、会员档案和回访名单，跟踪会员销售与触达状态。</p>
      </div>
      <div class="header-meta">
        <el-tag :type="statusTagType" effect="light" round>
          <span class="live-dot"></span>
          {{ statusText }}
        </el-tag>
        <span>最新小票日期：{{ summary.latest_ticket_date || "-" }}</span>
        <span>同步时间：{{ formatTime(summary.updated_at) }}</span>
      </div>
    </section>

    <el-alert
      v-if="!dataStatus.member_profile_synced"
      type="warning"
      show-icon
      :closable="false"
      title="会员档案暂未同步"
      description="当前先展示百胜小票中的会员线索；生日会员、沉睡会员、RFM分层需要会员档案同步后启用。"
    />

    <section class="summary-grid" v-loading="overviewLoading">
      <div class="metric-card" v-for="card in metricCards" :key="card.label">
        <div class="metric-label">{{ card.label }}</div>
        <div class="metric-value">{{ card.value }}</div>
        <div class="metric-sub">{{ card.sub }}</div>
      </div>
    </section>

    <section class="filter-band">
      <div class="filter-left">
        <el-radio-group v-model="preset" size="small" @change="applyPreset">
          <el-radio-button label="latest">最新日</el-radio-button>
          <el-radio-button label="last7">近7天</el-radio-button>
          <el-radio-button label="last30">近30天</el-radio-button>
          <el-radio-button label="custom">自定义</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          range-separator="至"
          :clearable="false"
          :disabled="preset !== 'custom'"
          size="small"
          @change="handleDateChange"
        />
        <el-input
          v-model="keyword"
          clearable
          size="small"
          class="keyword-input"
          :placeholder="['profile','assets','transactions'].includes(activeTab) ? '搜索会员编号/姓名/手机' : '搜索会员线索/门店'"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
      </div>
      <div class="filter-actions">
        <el-button size="small" :icon="Search" type="primary" @click="fetchActiveTab">查询</el-button>
        <el-button size="small" :icon="Refresh" :loading="activeLoading" @click="refresh">刷新</el-button>
      </div>
    </section>

    <section class="table-panel">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="VIP资产" name="assets">
          <el-table :data="assetRows" v-loading="assetLoading" border stripe size="small">
            <el-table-column prop="member_no" label="会员编号" min-width="130" />
            <el-table-column prop="member_name" label="会员" min-width="100" />
            <el-table-column prop="phone" label="手机号" width="125" />
            <el-table-column prop="register_store_name" label="注册门店" min-width="170" show-overflow-tooltip />
            <el-table-column prop="member_level" label="等级" width="90" />
            <el-table-column label="当前余额" width="125" sortable align="right"><template #default="{ row }"><strong :class="{ negative: row.current_balance < 0 }">{{ formatMoney(row.current_balance) }}</strong></template></el-table-column>
            <el-table-column label="累计消费" width="125" align="right"><template #default="{ row }">{{ formatMoney(row.total_amount) }}</template></el-table-column>
            <el-table-column prop="last_consume_date" label="最近消费" width="110" />
            <el-table-column label="状态" width="96"><template #default="{ row }"><el-tag :type="assetStatusType(row.balance_status)" size="small">{{ assetStatusName(row.balance_status) }}</el-tag></template></el-table-column>
          </el-table>
          <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next" :total="assetTotal" v-model:current-page="assetPage" v-model:page-size="assetPageSize" :page-sizes="[20,50,100,200]" @current-change="fetchAssets" @size-change="resetAssetPage" /></div>
        </el-tab-pane>

        <el-tab-pane label="余额变动" name="transactions">
          <el-table :data="transactionRows" v-loading="transactionLoading" border stripe size="small">
            <el-table-column prop="occurred_at" label="发生时间" width="160" />
            <el-table-column prop="member_no" label="会员编号" min-width="125" />
            <el-table-column prop="member_name" label="会员" min-width="100" />
            <el-table-column prop="store_name" label="门店" min-width="160" show-overflow-tooltip />
            <el-table-column label="类型" width="90"><template #default="{ row }">{{ transactionType(row.business_type) }}</template></el-table-column>
            <el-table-column label="变动前" width="110" align="right"><template #default="{ row }">{{ formatMoney(row.money_before) }}</template></el-table-column>
            <el-table-column label="变动金额" width="110" align="right"><template #default="{ row }"><strong :class="row.money_change < 0 ? 'negative' : 'positive'">{{ formatMoney(row.money_change) }}</strong></template></el-table-column>
            <el-table-column label="变动后" width="110" align="right"><template #default="{ row }">{{ formatMoney(row.money_after) }}</template></el-table-column>
            <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
          </el-table>
          <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next" :total="transactionTotal" v-model:current-page="transactionPage" v-model:page-size="transactionPageSize" :page-sizes="[20,50,100,200]" @current-change="fetchTransactions" @size-change="resetTransactionPage" /></div>
        </el-tab-pane>

        <el-tab-pane label="小票会员线索" name="pos">
          <el-table :data="posRows" v-loading="posLoading" border stripe size="small">
            <el-table-column type="index" label="排名" width="68" align="center" />
            <el-table-column prop="member_key" label="会员标识" min-width="130" />
            <el-table-column prop="last_store_name" label="最近门店" min-width="190" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.last_store_name }}</span>
                <span class="muted-code">{{ row.last_store_code }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="total_sales" label="销售额" width="120" sortable align="right">
              <template #default="{ row }">{{ formatMoney(row.total_sales) }}</template>
            </el-table-column>
            <el-table-column prop="total_actual" label="实收金额" width="120" sortable align="right">
              <template #default="{ row }">{{ formatMoney(row.total_actual) }}</template>
            </el-table-column>
            <el-table-column prop="order_count" label="订单数" width="90" sortable align="right" />
            <el-table-column prop="sales_qty" label="件数" width="90" sortable align="right">
              <template #default="{ row }">{{ formatQty(row.sales_qty) }}</template>
            </el-table-column>
            <el-table-column prop="avg_order_value" label="客单价" width="110" sortable align="right">
              <template #default="{ row }">{{ formatMoney(row.avg_order_value) }}</template>
            </el-table-column>
            <el-table-column prop="first_consume_date" label="首次消费" width="112" />
            <el-table-column prop="last_consume_date" label="最近消费" width="112" />
          </el-table>
          <div class="pagination-row">
            <el-pagination
              background
              layout="total, sizes, prev, pager, next, jumper"
              :total="posTotal"
              v-model:current-page="posPage"
              v-model:page-size="pageSize"
              :page-sizes="[20, 50, 100, 200]"
              @current-change="fetchPosMembers"
              @size-change="handlePageSizeChange"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="会员档案" name="profile">
          <el-table :data="profileRows" v-loading="profileLoading" border stripe size="small">
            <el-table-column prop="member_no" label="会员编号" min-width="130" />
            <el-table-column prop="member_name" label="会员姓名" min-width="110" />
            <el-table-column prop="phone" label="手机号" width="130" />
            <el-table-column prop="member_level" label="等级" width="100" />
            <el-table-column prop="register_store_name" label="注册门店" min-width="180" show-overflow-tooltip />
            <el-table-column prop="total_amount" label="累计消费" width="120" align="right">
              <template #default="{ row }">{{ formatMoney(row.total_amount) }}</template>
            </el-table-column>
            <el-table-column prop="total_count" label="消费次数" width="100" align="right" />
            <el-table-column prop="last_consume_date" label="最近消费" width="112" />
            <el-table-column prop="rfm_segment" label="分层" width="110" />
          </el-table>
          <el-empty v-if="!profileLoading && profileRows.length === 0" description="会员档案未同步，暂无档案数据" />
          <div class="pagination-row" v-if="profileTotal > 0">
            <el-pagination
              background
              layout="total, sizes, prev, pager, next, jumper"
              :total="profileTotal"
              v-model:current-page="profilePage"
              v-model:page-size="profilePageSize"
              :page-sizes="[20, 50, 100, 200]"
              @current-change="fetchProfiles"
              @size-change="handleProfilePageSizeChange"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="回访名单" name="visits">
          <el-table :data="visitRows" v-loading="visitLoading" border stripe size="small">
            <el-table-column prop="visit_date" label="回访日期" width="112" />
            <el-table-column prop="member_no" label="会员编号" min-width="130" />
            <el-table-column prop="member_name" label="会员姓名" min-width="110" />
            <el-table-column prop="store_name" label="建议门店" min-width="170" show-overflow-tooltip />
            <el-table-column prop="visit_reason" label="原因" width="110" />
            <el-table-column prop="priority" label="优先级" width="90" align="right" />
            <el-table-column prop="sleep_days" label="沉睡天数" width="100" align="right" />
            <el-table-column prop="visit_status" label="状态" width="100" />
            <el-table-column prop="ai_suggestion" label="建议话术" min-width="220" show-overflow-tooltip />
          </el-table>
          <el-empty v-if="!visitLoading && visitRows.length === 0" description="回访名单未生成，暂无回访数据" />
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh, Search } from "@element-plus/icons-vue";
import { memberApi } from "@/api/member";

type Preset = "latest" | "last7" | "last30" | "custom";
type TabName = "assets" | "transactions" | "pos" | "profile" | "visits";

const overviewLoading = ref(false);
const posLoading = ref(false);
const profileLoading = ref(false);
const visitLoading = ref(false);
const assetLoading = ref(false);
const transactionLoading = ref(false);
const activeTab = ref<TabName>("assets");
const preset = ref<Preset>("latest");
const keyword = ref("");
const dateRange = ref<[string, string]>(["", ""]);
const pageSize = ref(20);
const posPage = ref(1);
const posTotal = ref(0);
const profilePage = ref(1);
const profilePageSize = ref(20);
const profileTotal = ref(0);
const summary = ref<any>({});
const dataStatus = ref<any>({});
const posRows = ref<any[]>([]);
const profileRows = ref<any[]>([]);
const visitRows = ref<any[]>([]);
const assetOverview = ref<any>({});
const assetRows = ref<any[]>([]); const assetTotal = ref(0); const assetPage = ref(1); const assetPageSize = ref(20);
const transactionRows = ref<any[]>([]); const transactionTotal = ref(0); const transactionPage = ref(1); const transactionPageSize = ref(20);

function parseDate(value: string) {
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime()) ? new Date() : d;
}

function toDateString(d: Date) {
  const copy = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return copy.toISOString().slice(0, 10);
}

function shiftDate(value: string, days: number) {
  const d = parseDate(value);
  d.setDate(d.getDate() + days);
  return toDateString(d);
}

function formatMoney(value: any) {
  const n = Number(value || 0);
  if (Math.abs(n) >= 10000) return `¥${(n / 10000).toFixed(2)}万`;
  return `¥${Math.round(n).toLocaleString("zh-CN")}`;
}

function formatQty(value: any) {
  const n = Number(value || 0);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function formatPercent(value: any) {
  const n = Number(value || 0);
  return n ? `${(n * 100).toFixed(1)}%` : "0%";
}

function formatTime(value: any) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

const statusText = computed(() => (dataStatus.value.member_profile_synced ? "会员档案已同步" : "展示小票会员线索"));
const statusTagType = computed(() => (dataStatus.value.member_profile_synced ? "success" : "warning"));
const activeLoading = computed(() => {
  if (activeTab.value === "assets") return assetLoading.value;
  if (activeTab.value === "transactions") return transactionLoading.value;
  if (activeTab.value === "profile") return profileLoading.value;
  if (activeTab.value === "visits") return visitLoading.value;
  return posLoading.value;
});

const metricCards = computed(() => [
  { label: "VIP正余额", value: formatMoney(assetOverview.value.total_balance), sub: "百胜会员主档 CZ_DQJE" },
  { label: "有余额会员", value: Number(assetOverview.value.balance_member_count || 0).toLocaleString("zh-CN"), sub: `${assetOverview.value.negative_balance_count || 0} 人负余额单列` },
  { label: "90天沉睡余额", value: formatMoney(assetOverview.value.dormant_balance_90d), sub: `${assetOverview.value.dormant_member_90d || 0} 位会员` },
  { label: "近30天充值", value: formatMoney(assetOverview.value.recharge_30d), sub: `${assetOverview.value.recharge_member_30d || 0} 位充值会员` },
  { label: "会员档案数", value: Number(summary.value.profile_members || 0).toLocaleString("zh-CN"), sub: "dim_member" },
  { label: "会员销售额", value: formatMoney(summary.value.member_sales), sub: `占比 ${formatPercent(summary.value.member_sales_ratio)}` },
]);

async function fetchOverview() {
  overviewLoading.value = true;
  try {
    const [{ data }, { data: assetData }] = await Promise.all([memberApi.getOverview(), memberApi.getAssetOverview()]);
    if (!data?.success) {
      ElMessage.error(data?.message || "会员概览加载失败");
      return;
    }
    summary.value = data.data?.summary || {};
    dataStatus.value = data.data?.data_status || {};
    assetOverview.value = assetData?.data?.summary || {};
    if (!dateRange.value[0] && summary.value.latest_ticket_date) applyPreset();
  } catch (e: any) {
    ElMessage.error(e?.message || "会员概览加载失败");
  } finally {
    overviewLoading.value = false;
  }
}

async function fetchAssets() {
  assetLoading.value = true;
  try {
    const params: any = { page: assetPage.value, page_size: assetPageSize.value };
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await memberApi.listAssets(params);
    assetRows.value = data?.data?.items || []; assetTotal.value = data?.data?.total || 0;
  } finally { assetLoading.value = false; }
}

async function fetchTransactions() {
  transactionLoading.value = true;
  try {
    const params: any = { page: transactionPage.value, page_size: transactionPageSize.value };
    if (dateRange.value[0]) params.start_date = dateRange.value[0];
    if (dateRange.value[1]) params.end_date = dateRange.value[1];
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await memberApi.listAssetTransactions(params);
    transactionRows.value = data?.data?.items || []; transactionTotal.value = data?.data?.total || 0;
  } finally { transactionLoading.value = false; }
}

function resetAssetPage() { assetPage.value = 1; fetchAssets(); }
function resetTransactionPage() { transactionPage.value = 1; fetchTransactions(); }
function assetStatusName(value: string) { return ({ negative: "负余额", dormant: "沉睡", high: "高余额", normal: "正常" } as any)[value] || value; }
function assetStatusType(value: string) { return ({ negative: "danger", dormant: "warning", high: "success", normal: "info" } as any)[value] || "info"; }
function transactionType(value: string) { return ({ recharge: "充值", consume: "消费", refund: "退款" } as any)[value] || value; }

function applyPreset() {
  const anchor = summary.value.latest_ticket_date || toDateString(new Date());
  if (preset.value === "latest") dateRange.value = [anchor, anchor];
  if (preset.value === "last7") dateRange.value = [shiftDate(anchor, -6), anchor];
  if (preset.value === "last30") dateRange.value = [shiftDate(anchor, -29), anchor];
  if (preset.value !== "custom") fetchPosMembers();
}

function handleDateChange() {
  if (preset.value === "custom") fetchPosMembers();
}

async function fetchPosMembers() {
  posLoading.value = true;
  try {
    const params: any = {
      page: posPage.value,
      page_size: pageSize.value,
    };
    if (dateRange.value[0]) params.start_date = dateRange.value[0];
    if (dateRange.value[1]) params.end_date = dateRange.value[1];
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await memberApi.listPosMembers(params);
    if (!data?.success) {
      ElMessage.error(data?.message || "会员线索加载失败");
      return;
    }
    const payload = data.data || {};
    posRows.value = payload.items || [];
    posTotal.value = payload.total || 0;
    if (payload.date_range?.start_date && payload.date_range?.end_date) {
      dateRange.value = [payload.date_range.start_date, payload.date_range.end_date];
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "会员线索加载失败");
  } finally {
    posLoading.value = false;
  }
}

async function fetchProfiles() {
  profileLoading.value = true;
  try {
    const params: any = { page: profilePage.value, page_size: profilePageSize.value };
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await memberApi.listMembers(params);
    const payload = data?.success ? (data.data || {}) : {};
    profileRows.value = payload.items || [];
    profileTotal.value = payload.total || 0;
  } finally {
    profileLoading.value = false;
  }
}

async function fetchVisits() {
  visitLoading.value = true;
  try {
    const { data } = await memberApi.listVisits({ page: 1, page_size: 100 });
    visitRows.value = data?.success ? (data.data?.items || []) : [];
  } finally {
    visitLoading.value = false;
  }
}

function fetchActiveTab() {
  if (activeTab.value === "assets") return fetchAssets();
  if (activeTab.value === "transactions") return fetchTransactions();
  if (activeTab.value === "profile") return fetchProfiles();
  if (activeTab.value === "visits") return fetchVisits();
  return fetchPosMembers();
}

async function refresh() {
  await fetchOverview();
  await fetchActiveTab();
}

function handleTabChange() {
  fetchActiveTab();
}

function handleSearch() {
  if (activeTab.value === "assets") assetPage.value = 1;
  if (activeTab.value === "transactions") transactionPage.value = 1;
  if (activeTab.value === "profile") profilePage.value = 1;
  if (activeTab.value === "pos") posPage.value = 1;
  fetchActiveTab();
}

function handlePageSizeChange() {
  posPage.value = 1;
  fetchPosMembers();
}

function handleProfilePageSizeChange() {
  profilePage.value = 1;
  fetchProfiles();
}

onMounted(async () => {
  await fetchOverview();
  await fetchAssets();
});
</script>

<style scoped>
.member-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  color: #111827;
}

.member-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.eyebrow {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}

.member-header h1 {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
  font-weight: 800;
  letter-spacing: 0;
}

.member-header p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.header-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
  white-space: nowrap;
}

.live-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 6px;
  border-radius: 999px;
  background: #22c55e;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  min-height: 92px;
  padding: 14px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.metric-label {
  font-size: 12px;
  color: #64748b;
}

.metric-value {
  margin-top: 8px;
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.1;
}

.metric-sub {
  margin-top: 7px;
  color: #94a3b8;
  font-size: 12px;
}

.filter-band,
.table-panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.filter-band {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 12px;
}

.filter-left {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.keyword-input {
  width: 190px;
}

.filter-actions {
  display: flex;
  gap: 8px;
}

.table-panel {
  padding: 12px 14px 14px;
}

.muted-code {
  margin-left: 8px;
  color: #94a3b8;
  font-size: 12px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
.negative { color:#DC2626; }
.positive { color:#059669; }

@media (max-width: 1280px) {
  .summary-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .member-header,
  .filter-band {
    flex-direction: column;
    align-items: stretch;
  }

  .header-meta {
    align-items: flex-start;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
