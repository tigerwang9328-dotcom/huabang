<template>
  <div class="fc-finance-reports">
    <el-tabs v-model="activeTab" class="fc-tabs">
      <el-tab-pane label="资产负债表" name="balance_sheet" />
      <el-tab-pane label="利润表" name="income_statement" />
      <el-tab-pane label="现金流量表" name="cash_flow" />
    </el-tabs>

    <div class="fc-card">
      <div class="fc-toolbar">
        <div class="fc-toolbar-left">
          <el-select
            v-model="bookId"
            placeholder="选择账套"
            clearable
            filterable
            style="width: 220px"
            @change="handleBookChange"
          >
            <el-option
              v-for="b in books"
              :key="b.id"
              :label="b.name"
              :value="b.id"
            />
          </el-select>
          <el-select
            v-model="periodId"
            placeholder="选择期间"
            clearable
            filterable
            style="width: 220px"
          >
            <el-option
              v-for="p in periods"
              :key="p.id"
              :label="p.label"
              :value="p.id"
            />
          </el-select>
          <el-button type="primary" :loading="generating" @click="generateReport">
            生成报表
          </el-button>
        </div>
        <div class="fc-toolbar-right">
          <el-tag
            v-if="statementData"
            :type="statusTagType"
            size="large"
          >
            {{ statusLabel }}
          </el-tag>
        </div>
      </div>

      <el-alert
        v-if="issues.length > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #title>
          <span>映射/数据问题 ({{ issues.length }} 条)</span>
        </template>
        <div class="fc-issues-list">
          <div v-for="(item, idx) in issues" :key="idx" class="fc-issue-item">
            <span class="fc-issue-line">{{ item.line_code }}</span>
            <span>{{ item.line_name }}</span>
            <el-tag size="small" :type="item.severity === 'error' ? 'danger' : 'warning'">
              {{ item.message }}
            </el-tag>
          </div>
        </div>
      </el-alert>

      <el-table
        v-loading="loading"
        :data="lineItems"
        border
        stripe
        show-summary
        :summary-method="getSummaries"
        :default-sort="{ prop: 'line_code', order: 'ascending' }"
        max-height="calc(100vh - 340px)"
        highlight-current-row
      >
        <el-table-column prop="line_code" label="行次" width="100" align="center" />
        <el-table-column prop="line_name" label="项目" min-width="220" show-overflow-tooltip />
        <el-table-column label="期末金额" width="180" align="right">
          <template #default="{ row }">
            <span :class="{ 'fc-amount-zero': row.current_amount === 0 }">
              {{ formatAmount(row.current_amount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="年初金额" width="180" align="right">
          <template #default="{ row }">
            <span :class="{ 'fc-amount-zero': row.year_to_date_amount === 0 }">
              {{ formatAmount(row.year_to_date_amount) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!statementData && !loading" class="fc-empty">
        <el-empty description="请选择账套和期间，点击【生成报表】" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { financeCenterApi } from "@/api/financeCenter"

const activeTab = ref('balance_sheet')
const bookId = ref<number | null>(null)
const periodId = ref<number | null>(null)
const books = ref<any[]>([])
const periods = ref<any[]>([])
const statementData = ref<any>(null)
const lineItems = ref<any[]>([])
const issues = ref<any[]>([])
const loading = ref(false)
const generating = ref(false)

const statusLabel = computed(() => {
  if (!statementData.value) return '未生成'
  const map: Record<string, string> = {
    ready: '已生成',
    pending_mapping: '待映射',
    pending_data: '待数据',
  }
  return map[statementData.value.status] || statementData.value.status
})

const statusTagType = computed(() => {
  if (!statementData.value) return 'info'
  const map: Record<string, string> = {
    ready: 'success',
    pending_mapping: 'warning',
    pending_data: 'danger',
  }
  return map[statementData.value.status] || 'info'
})

function formatAmount(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getSummaries(param: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  param.columns.forEach((col, idx) => {
    if (idx === 0) {
      sums[0] = '合计'
    } else if (idx === 1) {
      sums[1] = ''
    } else if (idx === 2) {
      const total = param.data.reduce((acc, row) => acc + (Number(row.current_amount) || 0), 0)
      sums[2] = formatAmount(total)
    } else if (idx === 3) {
      const total = param.data.reduce((acc, row) => acc + (Number(row.year_to_date_amount) || 0), 0)
      sums[3] = formatAmount(total)
    }
  })
  return sums
}

async function loadBooks() {
  try {
    const res = await financeCenterApi.listBooks()
    books.value = (res.data as any)?.data || []
    if (books.value.length === 1) {
      bookId.value = books.value[0].id
      handleBookChange()
    }
  } catch {
    ElMessage.error('加载账套列表失败')
  }
}

async function handleBookChange() {
  periods.value = []
  periodId.value = null
  statementData.value = null
  issues.value = []
  lineItems.value = []
  if (!bookId.value) return
  try {
    const res = await financeCenterApi.listPeriods({ book_id: bookId.value })
    periods.value = (res.data as any)?.data || []
  } catch {
    ElMessage.error('加载期间列表失败')
  }
}

async function generateReport() {
  if (!bookId.value || !periodId.value) {
    ElMessage.warning('请先选择账套和期间')
    return
  }
  generating.value = true
  try {
    const res = await financeCenterApi.generateStatement({
      book_id: bookId.value,
      period_id: periodId.value,
      statement_type: activeTab.value,
    })
    const data = (res.data as any)?.data || {}
    statementData.value = data
    lineItems.value = data.line_items || []
    issues.value = data.issues || []
    ElMessage.success('报表生成成功')
  } catch {
    ElMessage.error('报表生成失败')
  } finally {
    generating.value = false
  }
}

async function loadStatement() {
  if (!bookId.value || !periodId.value) return
  loading.value = true
  try {
    const res = await financeCenterApi.getStatement({
      book_id: bookId.value,
      period_id: periodId.value,
      statement_type: activeTab.value,
    })
    const data = (res.data as any)?.data || {}
    statementData.value = data
    lineItems.value = data.line_items || []
    issues.value = data.issues || []
  } catch {
    // 未生成时不报错
  } finally {
    loading.value = false
  }
}

watch(activeTab, () => {
  if (statementData.value) {
    generateReport()
  } else {
    loadStatement()
  }
})

onMounted(() => {
  loadBooks()
})
</script>

<script lang="ts">
import { watch } from 'vue'
export default { name: 'FinanceReports' }
</script>

<style scoped>
.fc-finance-reports {
  padding: 0;
}
.fc-tabs {
  margin-bottom: 16px;
}
.fc-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.fc-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}
.fc-toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.fc-toolbar-right {
  display: flex;
  align-items: center;
}
.fc-issues-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.fc-issue-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.fc-issue-line {
  font-weight: 600;
  color: #2563eb;
  min-width: 48px;
}
.fc-amount-zero {
  color: #c0c4cc;
}
.fc-empty {
  padding: 60px 0;
}
</style>