<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <h3 style="margin:0">费用明细表</h3>
        <p style="margin:4px 0 0;color:#909399;font-size:12px">按费用科目展示当期发生额，借-贷=净费用</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <el-date-picker v-model="period" type="month" format="YYYY-MM" value-format="YYYY-MM"
          placeholder="选择期间" style="width:140px" @change="load" />
        <el-switch v-model="showAll" active-text="含零行" inactive-text="仅有发生额" @change="toggleView" />
        <el-button type="primary" @click="load" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 汇总 -->
    <el-card shadow="never" style="margin-bottom:16px" v-if="data">
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="kpi-label">期间</div>
          <div class="kpi-value primary">{{ data.period }}</div>
        </el-col>
        <el-col :span="6">
          <div class="kpi-label">有发生额科目数</div>
          <div class="kpi-value">{{ data.rows.length }} 个</div>
        </el-col>
        <el-col :span="6">
          <div class="kpi-label">净费用合计</div>
          <div class="kpi-value danger">{{ fmt(data.total_net) }}</div>
        </el-col>
        <el-col :span="6">
          <div class="kpi-label">费用科目总数</div>
          <div class="kpi-value">{{ data.all_rows.length }} 个</div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 明细表格 -->
    <el-card shadow="never">
      <el-table :data="displayRows" stripe border v-loading="loading"
        :summary-method="getSummary" show-summary>
        <el-table-column prop="account_code" label="科目编码" width="120" />
        <el-table-column prop="account_name" label="科目名称" min-width="160" />
        <el-table-column prop="period_debit" label="本期借方" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-active': row.period_debit > 0 }">{{ fmt(row.period_debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="period_credit" label="本期贷方" width="130" align="right">
          <template #default="{ row }">
            <span style="color:#67c23a">{{ fmt(row.period_credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="net_amount" label="净费用" width="130" align="right">
          <template #default="{ row }">
            <span :style="{ color: row.net_amount > 0 ? '#f56c6c' : row.net_amount < 0 ? '#67c23a' : '#909399', fontWeight: '600' }">
              {{ fmt(row.net_amount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末余额" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.closing_balance) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const loading = ref(false)
const data = ref<any>(null)
const showAll = ref(false)
const period = ref(finStore.currentPeriod || new Date().toISOString().slice(0, 7))

const fmt = (v: number) => '¥' + (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const displayRows = computed(() => {
  if (!data.value) return []
  return showAll.value ? data.value.all_rows : data.value.rows
})

function toggleView() { /* displayRows computed reacts automatically */ }

function getSummary({ columns, data: tableData }: any) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums.push('合计'); return }
    if (['period_debit', 'period_credit', 'net_amount', 'closing_balance'].includes(col.property)) {
      const total = tableData.reduce((acc: number, r: any) => acc + (r[col.property] || 0), 0)
      sums.push(fmt(total))
    } else {
      sums.push('')
    }
  })
  return sums
}

async function load() {
  if (!period.value) return
  loading.value = true
  try {
    const res: any = await request.get(`/finance/reports/expense-detail?book_id=${finStore.bookId}&period=${period.value}`)
    data.value = res
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
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
.kpi-label { color: #909399; font-size: 12px; margin-bottom: 4px; }
.kpi-value { font-size: 18px; font-weight: 700; color: #303133; }
.kpi-value.primary { color: #409eff; }
.kpi-value.danger { color: #f56c6c; }
.text-active { color: #f56c6c; }
</style>
