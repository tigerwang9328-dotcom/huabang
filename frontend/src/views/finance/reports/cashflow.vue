<template>
  <div class="cashflow-page">
    <div class="page-toolbar">
      <div class="toolbar-left">
        <h3 style="margin:0">现金流量表</h3>
      </div>
      <div class="toolbar-right">
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM"
          placeholder="选择期间" @change="load" style="width:140px" />
        <el-button plain :icon="Printer" @click="printPage">打印</el-button>
        <el-button plain :icon="Download" @click="exportExcel" :loading="exporting">导出</el-button>
      </div>
    </div>

    <div class="report-container" v-loading="loading" ref="reportRef">
      <div class="report-header">
        <div class="report-title">现金流量表</div>
        <div class="report-subtitle">
          编制单位：{{ store.currentBook?.company_name || '牧马人服饰' }}
          &emsp;期间：{{ period }}
          &emsp;单位：元
        </div>
      </div>

      <!-- 经营活动 -->
      <el-table :data="operating" border size="small" :show-header="!operating.length">
        <el-table-column label="项目" min-width="280">
          <template #default="{row}">
            <span :style="{ paddingLeft: (row.indent || 0) * 16 + 'px', fontWeight: row.bold ? 700 : 400 }">
              {{ row.item }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="行次" width="55" align="center">
          <template #default="{row}"><span>{{ row.line_no }}</span></template>
        </el-table-column>
        <el-table-column label="本期金额" width="150" align="right">
          <template #default="{row}">
            <span :class="row.bold ? 'bold-cell' : ''">{{ row.amount !== undefined ? fmtMoney(row.amount) : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本年累计" width="150" align="right">
          <template #default="{row}">
            <span :class="row.bold ? 'bold-cell' : ''">{{ row.ytd !== undefined ? fmtMoney(row.ytd) : '' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-summary" v-if="opTotal !== null">
        <span class="section-label">一、经营活动产生的现金流量净额</span>
        <span class="section-value" :class="opTotal >= 0 ? 'positive' : 'negative'">{{ fmtMoney(opTotal) }}</span>
      </div>

      <!-- 投资活动 -->
      <el-table :data="investing" border size="small" style="margin-top:8px">
        <el-table-column label="项目" min-width="280">
          <template #default="{row}">
            <span :style="{ paddingLeft: (row.indent || 0) * 16 + 'px', fontWeight: row.bold ? 700 : 400 }">{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="行次" width="55" align="center">
          <template #default="{row}"><span>{{ row.line_no }}</span></template>
        </el-table-column>
        <el-table-column label="本期金额" width="150" align="right">
          <template #default="{row}"><span :class="row.bold?'bold-cell':''">{{ row.amount !== undefined ? fmtMoney(row.amount) : '' }}</span></template>
        </el-table-column>
        <el-table-column label="本年累计" width="150" align="right">
          <template #default="{row}"><span :class="row.bold?'bold-cell':''">{{ row.ytd !== undefined ? fmtMoney(row.ytd) : '' }}</span></template>
        </el-table-column>
      </el-table>
      <div class="section-summary" v-if="invTotal !== null">
        <span class="section-label">二、投资活动产生的现金流量净额</span>
        <span class="section-value" :class="invTotal >= 0 ? 'positive' : 'negative'">{{ fmtMoney(invTotal) }}</span>
      </div>

      <!-- 筹资活动 -->
      <el-table :data="financing" border size="small" style="margin-top:8px">
        <el-table-column label="项目" min-width="280">
          <template #default="{row}">
            <span :style="{ paddingLeft: (row.indent || 0) * 16 + 'px', fontWeight: row.bold ? 700 : 400 }">{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="行次" width="55" align="center">
          <template #default="{row}"><span>{{ row.line_no }}</span></template>
        </el-table-column>
        <el-table-column label="本期金额" width="150" align="right">
          <template #default="{row}"><span :class="row.bold?'bold-cell':''">{{ row.amount !== undefined ? fmtMoney(row.amount) : '' }}</span></template>
        </el-table-column>
        <el-table-column label="本年累计" width="150" align="right">
          <template #default="{row}"><span :class="row.bold?'bold-cell':''">{{ row.ytd !== undefined ? fmtMoney(row.ytd) : '' }}</span></template>
        </el-table-column>
      </el-table>
      <div class="section-summary" v-if="finTotal !== null">
        <span class="section-label">三、筹资活动产生的现金流量净额</span>
        <span class="section-value" :class="finTotal >= 0 ? 'positive' : 'negative'">{{ fmtMoney(finTotal) }}</span>
      </div>

      <div class="net-total" v-if="netCash !== null">
        <span>四、现金及现金等价物净增加额</span>
        <span :class="netCash >= 0 ? 'positive' : 'negative'">{{ fmtMoney(netCash) }}</span>
      </div>

      <el-empty v-if="!loading && isEmpty" description="暂无现金流数据，请先录入并过账相关凭证" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue"
import { ElMessage } from "element-plus"
import { Printer, Download } from "@element-plus/icons-vue"
import dayjs from "dayjs"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"

const store = useFinanceStore()
const bookId = computed(() => store.bookId)
const period = ref(store.currentPeriod || dayjs().format("YYYY-MM"))
const loading = ref(false)
const exporting = ref(false)
const reportRef = ref<HTMLElement>()

const operating = ref<any[]>([])
const investing = ref<any[]>([])
const financing = ref<any[]>([])

const opTotal = computed(() => operating.value.length ? operating.value.reduce((s: number, r: any) => s + (r.amount || 0), 0) : null)
const invTotal = computed(() => investing.value.length ? investing.value.reduce((s: number, r: any) => s + (r.amount || 0), 0) : null)
const finTotal = computed(() => financing.value.length ? financing.value.reduce((s: number, r: any) => s + (r.amount || 0), 0) : null)
const netCash = computed(() => (opTotal.value ?? 0) + (invTotal.value ?? 0) + (finTotal.value ?? 0))
const isEmpty = computed(() => !operating.value.length && !investing.value.length && !financing.value.length)

const fmtMoney = (v: number) => {
  if (v === undefined || v === null) return ""
  const n = Number(v)
  return n < 0 ? `(${Math.abs(n).toLocaleString("zh-CN", { minimumFractionDigits: 2 })})` : n.toLocaleString("zh-CN", { minimumFractionDigits: 2 })
}

async function load() {
  loading.value = true
  try {
    const d: any = await request.get("/finance/cashflow-statement", {
      params: { book_id: bookId.value, period: period.value }
    })
    operating.value = d.operating || []
    investing.value = d.investing || []
    financing.value = d.financing || []
  } catch { ElMessage.error("加载失败") }
  finally { loading.value = false }
}

function printPage() {
  window.print()
}

async function exportExcel() {
  exporting.value = true
  try {
    const res = await request.get("/finance/export/cashflow-statement", {
      params: { book_id: bookId.value, period: period.value },
      responseType: "blob" as any,
    })
    const url = URL.createObjectURL(res as any)
    const a = document.createElement("a")
    a.href = url; a.download = `现金流量表_${period.value}.xlsx`
    a.click(); URL.revokeObjectURL(url)
  } catch { ElMessage.error("导出失败") }
  finally { exporting.value = false }
}

onMounted(async () => {
  if (!store.loaded) await store.loadBooks()
  period.value = store.currentPeriod || dayjs().format("YYYY-MM")
  await load()
})

watch(() => store.bookId, () => load())
watch(() => store.currentPeriod, (val) => {
  if (!val || val === period.value) return
  period.value = val
  load()
})
</script>

<style scoped>
.cashflow-page { display: flex; flex-direction: column; gap: 16px; }
.page-toolbar { display: flex; align-items: center; justify-content: space-between; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }

.report-container { background: #fff; border-radius: 12px; padding: 24px; }
.report-header { text-align: center; margin-bottom: 20px; }
.report-title { font-size: 18px; font-weight: 700; color: #1a1a1a; }
.report-subtitle { font-size: 12px; color: #666; margin-top: 6px; }

.section-summary {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 16px; background: #f8f9fc; border: 1px solid #e4e7ed;
  border-top: none; font-weight: 600;
}
.section-label { color: #1a1a1a; }
.section-value { font-size: 15px; }
.positive { color: #67c23a; }
.negative { color: #f56c6c; }

.net-total {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; margin-top: 12px;
  background: #f0f4ff; border-radius: 8px;
  font-size: 15px; font-weight: 700; color: #1a1a1a;
}

.bold-cell { font-weight: 700; }

@media print {
  .page-toolbar { display: none; }
}
</style>
