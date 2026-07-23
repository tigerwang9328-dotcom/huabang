<template>
  <div class="finance-page">
    <!-- 顶部工具栏 -->
    <div class="page-toolbar">
      <div class="toolbar-left">
        <el-date-picker v-model="month" type="month" value-format="YYYY-MM" placeholder="选择月份"
          style="width:150px" @change="loadAll" />
        <el-button type="primary" :icon="Refresh" @click="loadAll" :loading="loading">刷新</el-button>
      </div>
      <div class="toolbar-right">
        <el-button plain @click="showAddReceipt = true">+ 记录回款</el-button>
        <el-button plain @click="showAddFee = true">+ 录入费用</el-button>
      </div>
    </div>

    <!-- KPI 卡片 -->
    <div class="kpi-grid" v-loading="loading">
      <div class="kpi-card" v-for="k in kpis" :key="k.key" :class="'kpi-' + k.theme">
        <div class="kpi-icon">{{ k.icon }}</div>
        <div class="kpi-body">
          <div class="kpi-label">{{ k.label }}</div>
          <div class="kpi-value" :class="{ negative: k.negative }">{{ k.value }}</div>
        </div>
      </div>
    </div>

    <!-- 图表行 -->
    <div class="chart-row">
      <el-card class="chart-card">
        <template #header><span class="card-title">📈 财务趋势</span></template>
        <div ref="trendChartEl" style="height:300px" />
      </el-card>
      <el-card class="chart-card chart-card-sm">
        <template #header><span class="card-title">📊 费用结构</span></template>
        <div ref="pieChartEl" style="height:300px" />
      </el-card>
    </div>

    <!-- 店铺利润排行 -->
    <el-card class="data-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">🏆 店铺利润排行 TOP20</span>
        </div>
      </template>
      <el-table :data="ranking" stripe size="small" v-loading="loading" max-height="360">
        <el-table-column type="index" label="#" width="45" />
        <el-table-column prop="store_name" label="店铺" min-width="200" show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column prop="sales" label="实发金额" width="120" align="right" :formatter="fmtMoney" />
        <el-table-column prop="refund" label="当期实退金额" width="130" align="right" :formatter="fmtMoney" />
        <el-table-column prop="cogs" label="实发成本" width="110" align="right" :formatter="fmtMoney" />
        <el-table-column prop="gross_profit" label="销售毛利" width="110" align="right" :formatter="fmtMoney" />
        <el-table-column prop="profit_rate" label="利润率" width="90" align="right">
          <template #default="{ row }">
            <span :style="{ color: row.profit_rate < 0 ? '#f56c6c' : row.profit_rate > 20 ? '#67c23a' : '#909399' }">
              {{ row.profit_rate }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 费用明细 + 风险预警并排 -->
    <div class="bottom-row">
      <!-- 费用明细 -->
      <el-card class="data-card">
        <template #header>
          <div class="card-header">
            <span class="card-title">💰 费用明细</span>
            <el-select v-model="feeType" style="width:120px" @change="loadFees" size="small">
              <el-option label="全部" value="" />
              <el-option label="广告" value="ad" />
              <el-option label="物流" value="logistics" />
              <el-option label="佣金" value="commission" />
              <el-option label="人工" value="labor" />
              <el-option label="包材" value="packing" />
              <el-option label="其他" value="other" />
            </el-select>
          </div>
        </template>
        <el-table :data="fees" stripe size="small" max-height="300">
          <el-table-column prop="fee_date" label="日期" width="100" />
          <el-table-column prop="fee_type" label="类型" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="feeTagType(row.fee_type)">{{ feeLabel(row.fee_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="150" show-overflow-tooltip />
          <el-table-column prop="amount" label="金额" width="110" align="right" :formatter="fmtMoney" />
        </el-table>
        <el-empty v-if="fees.length === 0" description="暂无费用" :image-size="60" />
      </el-card>

      <!-- 风险预警 -->
      <el-card class="data-card">
        <template #header><span class="card-title">⚠️ 风险预警</span></template>
        <el-table :data="alerts" stripe size="small" max-height="300">
          <el-table-column prop="biz_date" label="日期" width="100" />
          <el-table-column prop="alert_level" label="级别" width="70">
            <template #default="{ row }">
              <el-tag size="small" :type="row.alert_level === 'danger' ? 'danger' : 'warning'">
                {{ row.alert_level === 'danger' ? '严重' : '警告' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="预警内容" min-width="200" show-overflow-tooltip />
          <el-table-column prop="store_name" label="店铺" width="120" show-overflow-tooltip />
        </el-table>
        <el-empty v-if="alerts.length === 0" description="暂无预警" :image-size="60" />
      </el-card>
    </div>

    <!-- 记录回款弹窗 -->
    <el-dialog v-model="showAddReceipt" title="记录回款" width="440px" destroy-on-close>
      <el-form :model="receiptForm" label-width="80px">
        <el-form-item label="日期"><el-date-picker v-model="receiptForm.receipt_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="平台"><el-input v-model="receiptForm.platform" /></el-form-item>
        <el-form-item label="店铺"><el-input v-model="receiptForm.store_name" /></el-form-item>
        <el-form-item label="金额"><el-input-number v-model="receiptForm.amount" :precision="2" :min="0" style="width:100%" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="receiptForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddReceipt = false">取消</el-button>
        <el-button type="primary" @click="saveReceipt">确定</el-button>
      </template>
    </el-dialog>

    <!-- 录入费用弹窗 -->
    <el-dialog v-model="showAddFee" title="录入费用" width="440px" destroy-on-close>
      <el-form :model="feeForm" label-width="80px">
        <el-form-item label="日期"><el-date-picker v-model="feeForm.fee_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="feeForm.fee_type" style="width:100%">
            <el-option label="广告投放" value="ad" />
            <el-option label="快递物流" value="logistics" />
            <el-option label="平台佣金" value="commission" />
            <el-option label="人工成本" value="labor" />
            <el-option label="包材费用" value="packing" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="feeForm.description" /></el-form-item>
        <el-form-item label="店铺"><el-input v-model="feeForm.store_name" placeholder="可选" /></el-form-item>
        <el-form-item label="金额"><el-input-number v-model="feeForm.amount" :precision="2" :min="0" style="width:100%" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="feeForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddFee = false">取消</el-button>
        <el-button type="primary" @click="saveFee">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue"
import { ElMessage } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import * as echarts from "echarts"
import dayjs from "dayjs"
import {
  getFinanceOverview, getFinanceTrend, getStoreRanking,
  getFees, getRiskAlerts, createReceipt, createFee,
} from "@/api/finance"

const loading = ref(false)
const month = ref(dayjs().format("YYYY-MM"))
const feeType = ref("")

// KPI
const kpis = ref<any[]>([])

// 数据
const ranking = ref<any[]>([])
const fees = ref<any[]>([])
const alerts = ref<any[]>([])

// 弹窗
const showAddReceipt = ref(false)
const showAddFee = ref(false)
const receiptForm = ref<any>({ receipt_date: dayjs().format("YYYY-MM-DD"), platform: "", store_name: "", amount: 0, remark: "" })
const feeForm = ref<any>({ fee_date: dayjs().format("YYYY-MM-DD"), fee_type: "other", description: "", store_name: "", amount: 0, remark: "" })

// 图表
const trendChartEl = ref<HTMLDivElement>()
const pieChartEl = ref<HTMLDivElement>()
let trendChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null

// 费用标签映射
const feeLabels: Record<string, string> = { ad: "广告", logistics: "物流", commission: "佣金", labor: "人工", packing: "包材", other: "其他" }
const feeColors: Record<string, string> = { ad: "danger", logistics: "warning", commission: "", labor: "info", packing: "success", other: "" }
const feeLabel = (t: string) => feeLabels[t] || t
const feeTagType = (t: string) => feeColors[t] || "info"

// 金额格式化
const fmtMoney = (_r: any, _c: any, v: number) => v != null ? `¥${Number(v).toLocaleString()}` : "—"

// ── 加载数据 ──
async function loadAll() {
  loading.value = true
  try {
    const [overview, trend, rank, feeList, alertList]: any[] = await Promise.all([
      getFinanceOverview(month.value).catch(() => null),
      getFinanceTrend(month.value).catch(() => []),
      getStoreRanking(month.value).catch(() => []),
      getFees(month.value, feeType.value || undefined).catch(() => []),
      getRiskAlerts(false, 20).catch(() => []),
    ])

    // KPI
    if (overview) {
      const o = overview
      kpis.value = [
        { key: "sales",     icon: "💵", label: "实发金额",   value: `¥${Number(o.total_sales).toLocaleString()}`,     theme: "blue" },
        { key: "receipt",   icon: "💳", label: "回款金额",   value: `¥${Number(o.total_receipt).toLocaleString()}`,   theme: "green" },
        { key: "refund",    icon: "↩️", label: "当期实退金额", value: `¥${Number(o.total_refund).toLocaleString()}`,  theme: "red",   negative: true },
        { key: "ad",        icon: "📢", label: "广告费用",   value: `¥${Number(o.total_ad_cost).toLocaleString()}`,   theme: "orange" },
        { key: "logistics", icon: "🚚", label: "物流费用",   value: `¥${Number(o.total_logistics).toLocaleString()}`, theme: "orange" },
        { key: "packing",   icon: "📦", label: "包材费用",   value: `¥${Number(o.total_pack_cost).toLocaleString()}`, theme: "orange" },
        { key: "labor",     icon: "👥", label: "人工成本",   value: `¥${Number(o.total_labor_cost).toLocaleString()}`,theme: "purple" },
        { key: "gross",     icon: "📈", label: "销售毛利",   value: `¥${Number(o.gross_profit).toLocaleString()}`,    theme: o.gross_profit >= 0 ? "green" : "red", negative: o.gross_profit < 0 },
        { key: "net",       icon: "💰", label: "净利",       value: `¥${Number(o.net_profit).toLocaleString()}`,      theme: o.net_profit >= 0 ? "green" : "red", negative: o.net_profit < 0 },
        { key: "rate",      icon: "📊", label: "净利率",     value: `${o.profit_rate}%`,                              theme: o.profit_rate >= 0 ? "green" : "red" },
        { key: "cashflow",  icon: "🏦", label: "现金流净额", value: `¥${Number(o.cashflow_net).toLocaleString()}`,    theme: o.cashflow_net >= 0 ? "green" : "red" },
      ]

      // 费用饼图
      renderPieChart(o)
    }

    ranking.value = rank || []
    fees.value = feeList || []
    alerts.value = alertList || []

    // 趋势图
    await nextTick()
    renderTrendChart(trend || [])
  } finally {
    loading.value = false
  }
}

async function loadFees() {
  fees.value = await getFees(month.value, feeType.value || undefined).catch(() => []) as any[] || []
}

// ── 趋势图 ──
function renderTrendChart(data: any[]) {
  if (!trendChartEl.value) return
  if (!trendChart) trendChart = echarts.init(trendChartEl.value)
  trendChart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["销售额", "费用", "经营利润"] },
    grid: { left: 60, right: 20, top: 40, bottom: 30 },
    xAxis: { type: "category", data: data.map(d => d.period) },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => v >= 10000 ? (v/10000).toFixed(0)+"万" : String(v) } },
    series: [
      { name: "销售额",   type: "bar",  data: data.map(d => d.sales),  itemStyle: { color: "#5b8ff9" } },
      { name: "费用",     type: "bar",  data: data.map(d => d.cost),   itemStyle: { color: "#f56c6c" } },
      { name: "经营利润", type: "line", data: data.map(d => d.profit), smooth: true, itemStyle: { color: "#67c23a" }, lineStyle: { width: 3 } },
    ],
  })
}

function renderPieChart(o: any) {
  if (!pieChartEl.value) return
  if (!pieChart) pieChart = echarts.init(pieChartEl.value)
  const items = [
    { name: "广告", value: o.total_ad_cost },
    { name: "物流", value: o.total_logistics },
    { name: "包材", value: o.total_pack_cost },
    { name: "人工", value: o.total_labor_cost },
  ].filter(i => i.value > 0)

  if (items.length === 0) {
    pieChart.setOption({ title: { text: "暂无费用数据", left: "center", top: "center", textStyle: { color: "#999", fontSize: 14 } }, series: [] })
    return
  }
  pieChart.setOption({
    tooltip: { trigger: "item", formatter: "{b}: ¥{c} ({d}%)" },
    legend: { bottom: 10 },
    series: [{ type: "pie", radius: ["35%", "65%"], data: items, label: { formatter: "{b}\n{d}%" } }],
  })
}

// ── 保存 ──
async function saveReceipt() {
  try { await createReceipt(receiptForm.value); ElMessage.success("回款已记录"); showAddReceipt.value = false; loadAll() }
  catch { ElMessage.error("保存失败") }
}

async function saveFee() {
  try { await createFee(feeForm.value); ElMessage.success("费用已录入"); showAddFee.value = false; loadAll() }
  catch { ElMessage.error("保存失败") }
}

onMounted(() => loadAll())
</script>

<style scoped>
.finance-page { display: flex; flex-direction: column; gap: 18px; }

.page-toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }

/* KPI 卡片 - 11个自适应网格 */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px;
}
.kpi-card {
  background: #fff; border-radius: 14px; padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04); border: 1px solid #f0f0f0;
  display: flex; align-items: center; gap: 12px; transition: all 0.15s;
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.kpi-icon { font-size: 22px; width: 42px; height: 42px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.kpi-blue .kpi-icon   { background: #eef3ff; }
.kpi-green .kpi-icon  { background: #e8f8ee; }
.kpi-red .kpi-icon    { background: #fef0f0; }
.kpi-orange .kpi-icon { background: #fef6e8; }
.kpi-purple .kpi-icon { background: #f3f0ff; }
.kpi-label { font-size: 11px; color: #999; margin-bottom: 4px; }
.kpi-value { font-size: 17px; font-weight: 700; color: #1a1a1a; }
.kpi-value.negative { color: #f56c6c; }

/* 图表行 */
.chart-row { display: grid; grid-template-columns: 2fr 1fr; gap: 18px; }
.chart-card { border-radius: 14px; }
.chart-card-sm { min-width: 280px; }
.card-title { font-size: 14px; font-weight: 600; }

/* 底部行 */
.bottom-row { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.data-card { border-radius: 14px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

@media (max-width: 1200px) {
  .chart-row { grid-template-columns: 1fr; }
  .bottom-row { grid-template-columns: 1fr; }
}
</style>
