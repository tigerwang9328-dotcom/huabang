<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">资产负债表</h3>
      <div style="display:flex;gap:8px">
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM"
          placeholder="选择期间" @change="load" style="width:150px" />
        <el-button :icon="Printer" @click="window.print()">打印</el-button>
      </div>
    </div>

    <el-table :data="rows" stripe border size="small" v-loading="loading"
      :row-class-name="rowClass">
      <el-table-column prop="item" label="资产" min-width="200">
        <template #default="{row}">
          <span :style="row.is_total ? 'font-weight:700' : ''">{{ row.item }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="line_no" label="行次" width="55" align="center" />
      <el-table-column prop="closing_balance" label="期末余额" width="150" align="right">
        <template #default="{row}">
          <span :style="row.is_total ? 'font-weight:700' : ''">{{ fmtVal(row.closing_balance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="opening_balance" label="年初余额" width="150" align="right">
        <template #default="{row}">
          <span :style="row.is_total ? 'font-weight:700' : ''">{{ fmtVal(row.opening_balance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="liability_item" label="负债及所有者权益" min-width="200">
        <template #default="{row}">
          <span v-if="row.liability_item" :style="row.is_total ? 'font-weight:700' : ''">
            {{ row.liability_item }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="liability_line" label="行次" width="55" align="center" />
      <el-table-column prop="liability_closing" label="期末余额" width="150" align="right">
        <template #default="{row}">
          <span v-if="row.liability_item" :style="row.is_total ? 'font-weight:700' : ''">
            {{ fmtVal(row.liability_closing) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="liability_opening" label="年初余额" width="150" align="right">
        <template #default="{row}">
          <span v-if="row.liability_item" :style="row.is_total ? 'font-weight:700' : ''">
            {{ fmtVal(row.liability_opening) }}
          </span>
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
    const d: any = await request.get(`/finance/reports/balance-sheet?book_id=${finStore.bookId}&period=${period.value}`)
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
:deep(.summary-row td) { background: #f5f7fa !important; font-weight: 700; }
</style>
