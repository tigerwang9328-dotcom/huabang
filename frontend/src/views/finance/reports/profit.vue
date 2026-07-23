<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">利润表</h3>
      <div style="display:flex;gap:8px;align-items:center">
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM"
          placeholder="选择期间" @change="load" style="width:150px" />
        <el-button :icon="Printer" @click="window.print()">打印</el-button>
      </div>
    </div>

    <el-table :data="rows" stripe border size="small" v-loading="loading"
      :row-class-name="rowClass">
      <el-table-column prop="item" label="项目" min-width="240">
        <template #default="{row}">
          <span :style="row.is_total ? 'font-weight:700' : ''">{{ row.item }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="line_no" label="行次" width="60" align="center" />
      <el-table-column prop="current_period" label="本期金额" width="150" align="right">
        <template #default="{row}">
          <span :style="row.is_total ? 'font-weight:700' : ''">{{ fmtVal(row.current_period) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="ytd" label="本年累计" width="150" align="right">
        <template #default="{row}">
          <span :style="row.is_total ? 'font-weight:700' : ''">{{ fmtVal(row.ytd) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length===0" description="暂无数据，请先录入并过账凭证" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from "vue"
import { Printer } from "@element-plus/icons-vue"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"
import dayjs from "dayjs"

const finStore = useFinanceStore()
const loading = ref(false), rows = ref<any[]>([])
const period = ref(dayjs().format("YYYY-MM"))

const fmtVal = (v: number) => v != null ? '¥' + Number(v).toLocaleString() : '—'
const rowClass = ({ row }: any) => row.is_total ? 'summary-row' : ''

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/reports/profit-loss?book_id=${finStore.bookId}&period=${period.value}`)
    rows.value = d.rows || []
  } finally { loading.value = false }
}

onMounted(async () => {
  await finStore.loadBooks()
  if (finStore.currentPeriod) period.value = finStore.currentPeriod
  load()
})

watch(() => finStore.bookId, () => load())
watch(() => finStore.currentPeriod, (val) => {
  if (!val || val === period.value) return
  period.value = val
  load()
})
</script>

<style scoped>
:deep(.summary-row td) { background: #f5f7fa !important; }
</style>
