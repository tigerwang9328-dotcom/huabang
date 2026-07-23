<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <h3 style="margin:0">应付明细台账</h3>
        <p style="margin:4px 0 0;color:#909399;font-size:12px">按供应商分组展示每笔应付单，含运行余额与账龄</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <el-date-picker v-model="filters.period" type="month" format="YYYY-MM" value-format="YYYY-MM"
          placeholder="期间（空=全部）" style="width:150px" clearable />
        <el-input v-model="filters.supplier_name" placeholder="供应商名称" style="width:160px" clearable />
        <el-select v-model="filters.status" placeholder="状态" style="width:120px" clearable>
          <el-option label="未付清" value="open" />
          <el-option label="部分付清" value="partial" />
          <el-option label="已付清" value="closed" />
        </el-select>
        <el-button type="primary" @click="load" :loading="loading">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </div>

    <!-- 汇总卡片 -->
    <el-row :gutter="12" style="margin-bottom:16px" v-if="summary">
      <el-col :span="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-label">应付总额</div>
          <div class="kpi-value primary">{{ fmt(summary.total_amount) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-label">已付款</div>
          <div class="kpi-value success">{{ fmt(summary.total_paid) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-label">未付余额</div>
          <div class="kpi-value danger">{{ fmt(summary.total_balance) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-label">单据笔数</div>
          <div class="kpi-value">{{ summary.order_count }} 笔</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 供应商余额汇总 -->
    <el-card shadow="never" style="margin-bottom:16px" v-if="bySupplier.length">
      <template #header>
        <span style="font-weight:600">供应商余额排行（TOP {{ Math.min(bySupplier.length, 10) }}）</span>
      </template>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        <el-tag v-for="s in bySupplier.slice(0,10)" :key="s.supplier_name"
          :type="s.balance > 0 ? 'danger' : 'success'" size="large">
          {{ s.supplier_name }}：{{ fmt(s.balance) }}
        </el-tag>
      </div>
    </el-card>

    <!-- 明细表格 -->
    <el-card shadow="never">
      <el-table :data="rows" stripe border v-loading="loading" row-key="id"
        :default-sort="{ prop: 'supplier_name', order: 'ascending' }">
        <el-table-column prop="supplier_name" label="供应商" width="140" fixed />
        <el-table-column prop="order_no" label="单号" width="160" />
        <el-table-column prop="order_date" label="单据日期" width="100" />
        <el-table-column prop="period" label="期间" width="80" />
        <el-table-column prop="total_amount" label="应付金额" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.total_amount) }}</template>
        </el-table-column>
        <el-table-column prop="paid_amount" label="已付款" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.paid_amount) }}</template>
        </el-table-column>
        <el-table-column prop="balance" label="余额" width="120" align="right">
          <template #default="{ row }">
            <span :style="{ color: row.balance > 0 ? '#f56c6c' : '#67c23a' }">{{ fmt(row.balance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="supplier_balance" label="供应商累计余额" width="140" align="right">
          <template #default="{ row }">
            <span style="color:#e6a23c;font-weight:600">{{ fmt(row.supplier_balance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="days_outstanding" label="账龄(天)" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="agingType(row.days_outstanding)" size="small">{{ row.days_outstanding }}天</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const loading = ref(false)
const rows = ref<any[]>([])
const summary = ref<any>(null)
const bySupplier = ref<any[]>([])

const filters = ref({ period: '', supplier_name: '', status: '' })

const fmt = (v: number) => '¥' + (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const agingType = (d: number) => d <= 30 ? 'success' : d <= 60 ? 'warning' : d <= 90 ? '' : 'danger'
const statusType = (s: string) => ({ open: 'warning', partial: '', closed: 'success' }[s] || 'info')
const statusLabel = (s: string) => ({ open: '未付清', partial: '部分付清', closed: '已付清' }[s] || s)

async function load() {
  loading.value = true
  try {
    const params: any = { book_id: finStore.bookId }
    if (filters.value.period) params.period = filters.value.period
    if (filters.value.supplier_name) params.supplier_name = filters.value.supplier_name
    if (filters.value.status) params.status = filters.value.status
    const qs = new URLSearchParams(params).toString()
    const res: any = await request.get(`/finance/reports/payable-detail?${qs}`)
    rows.value = res.rows
    summary.value = res.summary
    bySupplier.value = res.by_supplier
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.value = { period: '', supplier_name: '', status: '' }
  load()
}

onMounted(load)
</script>

<style scoped>
.kpi-card { text-align: center; }
.kpi-label { color: #909399; font-size: 12px; margin-bottom: 6px; }
.kpi-value { font-size: 20px; font-weight: 700; color: #303133; }
.kpi-value.primary { color: #409eff; }
.kpi-value.success { color: #67c23a; }
.kpi-value.danger { color: #f56c6c; }
</style>
