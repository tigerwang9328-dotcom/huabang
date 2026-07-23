<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">凭证汇总表</h3>
      <div style="display:flex;gap:8px;align-items:center">
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM" @change="load" style="width:150px" />
        <el-select v-model="statusFilter" style="width:120px" @change="load">
          <el-option label="全部状态" value="" />
          <el-option label="草稿" value="draft" />
          <el-option label="已审核" value="reviewed" />
          <el-option label="已过账" value="posted" />
        </el-select>
        <el-button :icon="Refresh" circle @click="load" />
      </div>
    </div>

    <!-- 统计行 -->
    <el-row :gutter="12" style="margin-bottom:16px">
      <el-col :span="6"><el-statistic title="凭证总数" :value="rows.length" /></el-col>
      <el-col :span="6"><el-statistic title="借方合计" :value="totalDebit" :precision="2" prefix="¥" /></el-col>
      <el-col :span="6"><el-statistic title="贷方合计" :value="totalCredit" :precision="2" prefix="¥" /></el-col>
      <el-col :span="6"><el-statistic title="已过账" :value="postedCount" suffix="张" /></el-col>
    </el-row>

    <el-table :data="rows" stripe border size="small" v-loading="loading"
      show-summary :summary-method="getSummary">
      <el-table-column prop="voucher_no" label="凭证号" width="150" />
      <el-table-column prop="voucher_date" label="日期" width="110" />
      <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
      <el-table-column prop="voucher_type" label="类型" width="90">
        <template #default="{row}">
          {{ { journal:'记账', receipt:'收款', payment:'付款' }[row.voucher_type] || row.voucher_type }}
        </template>
      </el-table-column>
      <el-table-column prop="total_debit" label="借方合计" width="130" align="right" :formatter="fmt" />
      <el-table-column prop="total_credit" label="贷方合计" width="130" align="right" :formatter="fmt" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{row}">
          <el-tag size="small"
            :type="row.status==='posted'?'success':row.status==='reviewed'?'warning':''">
            {{ { posted:'已过账', reviewed:'已审核', draft:'草稿', reversed:'已冲销' }[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length===0" description="本期暂无凭证" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue"
import { Refresh } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"
import dayjs from "dayjs"

const finStore = useFinanceStore()
const loading = ref(false)
const rows = ref<any[]>([])
const period = ref(dayjs().format("YYYY-MM"))
const statusFilter = ref("")

const fmt = (_r: any, _c: any, v: number) => v != null ? '¥' + Number(v).toLocaleString() : '—'
const totalDebit = computed(() => rows.value.reduce((s, r) => s + (r.total_debit || 0), 0))
const totalCredit = computed(() => rows.value.reduce((s, r) => s + (r.total_credit || 0), 0))
const postedCount = computed(() => rows.value.filter(r => r.status === 'posted').length)

function formatError(error: any) {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail.map((item: any) => item.msg || item.message).filter(Boolean).join("；") || "凭证汇总加载失败"
  return detail || error?.message || "凭证汇总加载失败"
}

function getSummary({ columns, data }: any) {
  return columns.map((c: any, i: number) => {
    if (i === 0) return '合计'
    if (c.property === 'total_debit') return '¥' + data.reduce((s: number, r: any) => s + (r.total_debit || 0), 0).toLocaleString()
    if (c.property === 'total_credit') return '¥' + data.reduce((s: number, r: any) => s + (r.total_credit || 0), 0).toLocaleString()
    return ''
  })
}

async function load() {
  if (!finStore.bookId || !period.value) return
  loading.value = true
  try {
    const params: any = { book_id: finStore.bookId, page_size: 100, period: period.value }
    if (statusFilter.value) params.status = statusFilter.value
    const qs = new URLSearchParams(params).toString()
    const d: any = await request.get(`/finance/vouchers?${qs}`)
    rows.value = d.rows || []
  } catch (error: any) {
    rows.value = []
    ElMessage.error(formatError(error))
  } finally {
    loading.value = false
  }
}

watch(() => finStore.bookId, () => {
  load()
})

watch(() => finStore.currentPeriod, (value) => {
  if (!value || value === period.value) return
  period.value = value
  load()
})

onMounted(async () => {
  await finStore.loadBooks()
  if (finStore.currentPeriod) period.value = finStore.currentPeriod
  await load()
})
</script>
