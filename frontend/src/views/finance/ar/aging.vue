<template>
  <div>
    <div style="display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
      <el-radio-group v-model="mode" @change="load">
        <el-radio-button value="receivable">应收账龄</el-radio-button>
        <el-radio-button value="payable">应付账龄</el-radio-button>
      </el-radio-group>
      <el-date-picker v-model="asOf" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD"
        placeholder="基准日（默认今天）" clearable style="width:160px" @change="load" />
      <el-button @click="load" :loading="loading">刷新</el-button>
    </div>

    <!-- 汇总卡片 -->
    <el-row :gutter="12" style="margin-bottom:16px" v-if="data">
      <el-col :span="4"><el-card shadow="never" class="kpi-card">
        <div class="kpi-label">未结余额合计</div>
        <div class="kpi-value" :style="{ color: mode === 'receivable' ? '#f56c6c' : '#e6a23c' }">
          {{ fmt(data.total_balance) }}
        </div>
      </el-card></el-col>
      <el-col :span="4" v-for="(label, key) in bucketKeys" :key="key">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-label">{{ label }}</div>
          <div class="kpi-value" :style="{ color: bucketColor(key) }">
            {{ fmt(data.buckets?.[label] || 0) }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 账龄明细表 -->
    <el-table v-if="data" :data="detailRows" stripe border size="small" v-loading="loading"
      row-key="name" default-expand-all>
      <el-table-column :label="mode === 'receivable' ? '客户' : '供应商'" prop="name" min-width="160">
        <template #default="{ row }">
          <span :style="{ fontWeight: row._type === 'group' ? '600' : 'normal' }">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单号" prop="order_no" width="140" />
      <el-table-column label="单据日期" prop="order_date" width="100" />
      <el-table-column label="账龄(天)" prop="days" width="80" align="right" />
      <el-table-column label="0-30天" width="110" align="right">
        <template #default="{ row }">{{ row['0-30天'] != null ? fmt(row['0-30天']) : '' }}</template>
      </el-table-column>
      <el-table-column label="31-60天" width="110" align="right">
        <template #default="{ row }">{{ row['31-60天'] != null ? fmt(row['31-60天']) : '' }}</template>
      </el-table-column>
      <el-table-column label="61-90天" width="110" align="right">
        <template #default="{ row }">{{ row['61-90天'] != null ? fmt(row['61-90天']) : '' }}</template>
      </el-table-column>
      <el-table-column label="91-120天" width="110" align="right">
        <template #default="{ row }">{{ row['91-120天'] != null ? fmt(row['91-120天']) : '' }}</template>
      </el-table-column>
      <el-table-column label="120天以上" width="110" align="right">
        <template #default="{ row }">{{ row['120天以上'] != null ? fmt(row['120天以上']) : '' }}</template>
      </el-table-column>
      <el-table-column label="合计" width="120" align="right">
        <template #default="{ row }">
          <span style="font-weight:600">{{ row.total_balance != null ? fmt(row.total_balance) : (row.balance != null ? fmt(row.balance) : '') }}</span>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !data" description="暂无数据，请先新建应收/应付单据" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const loading = ref(false)
const mode = ref<'receivable' | 'payable'>('receivable')
const asOf = ref('')
const data = ref<any>(null)

const fmt = (v: number) => '¥' + (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const bucketKeys: Record<string, string> = {
  '0-30天': '0-30天', '31-60天': '31-60天', '61-90天': '61-90天',
  '91-120天': '91-120天', '120天以上': '120天以上',
}

function bucketColor(key: string) {
  const map: Record<string, string> = {
    '0-30天': '#67c23a', '31-60天': '#e6a23c',
    '61-90天': '#f56c6c', '91-120天': '#c0392b', '120天以上': '#7f1d1d',
  }
  return map[key] || '#303133'
}

// 将 API 返回的按客户/供应商分组数据展开为带 children 的 tree 结构
const detailRows = computed(() => {
  if (!data.value) return []
  const key = mode.value === 'receivable' ? 'customers' : 'suppliers'
  const nameKey = mode.value === 'receivable' ? 'customer_name' : 'supplier_name'
  const groups = data.value[key] || []
  const result: any[] = []
  for (const g of groups) {
    result.push({
      _type: 'group',
      name: g[nameKey],
      total_balance: g.total_balance,
      '0-30天': g['0-30天'],
      '31-60天': g['31-60天'],
      '61-90天': g['61-90天'],
      '91-120天': g['91-120天'],
      '120天以上': g['120天以上'],
    })
    for (const ord of (g.orders || [])) {
      const bucketRow: any = {
        _type: 'order',
        name: '',
        order_no: ord.order_no,
        order_date: ord.order_date,
        days: ord.days,
        balance: ord.balance,
      }
      bucketRow[ord.bucket] = ord.balance
      result.push(bucketRow)
    }
  }
  return result
})

async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams({ book_id: String(finStore.bookId) })
    if (asOf.value) params.set('as_of', asOf.value)
    const url = `/finance/aging/${mode.value}?${params}`
    data.value = await request.get(url)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.kpi-card { text-align: center; }
.kpi-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.kpi-value { font-size: 18px; font-weight: 700; }
</style>
