<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <h3 style="margin:0">税金明细表</h3>
        <p style="margin:4px 0 0;color:#909399;font-size:12px">双视角：账簿凭证视角（2221科目）+ 税务台账视角</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <el-date-picker v-model="period" type="month" format="YYYY-MM" value-format="YYYY-MM"
          placeholder="选择期间" style="width:140px" @change="load" />
        <el-button type="primary" @click="load" :loading="loading">刷新</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" type="card">
      <!-- Tab A: 账簿视角 -->
      <el-tab-pane label="账簿视角（凭证驱动）" name="ledger">
        <div style="margin:12px 0;color:#909399;font-size:12px">
          数据来源：fin_ledger_balances，2221「应交税费」科目及子科目，当期发生额与余额
        </div>

        <!-- 汇总 -->
        <el-row :gutter="12" style="margin-bottom:16px" v-if="ledger">
          <el-col :span="8">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">期间</div>
              <div class="kpi-value primary">{{ period }}</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">涉税科目数</div>
              <div class="kpi-value">{{ ledger.rows.length }} 个</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">应交税费余额合计</div>
              <div class="kpi-value danger">{{ fmt(ledger.total_balance) }}</div>
            </el-card>
          </el-col>
        </el-row>

        <el-card shadow="never">
          <el-table :data="ledger ? ledger.rows : []" stripe border v-loading="loading">
            <el-table-column prop="account_code" label="科目编码" width="120" />
            <el-table-column prop="account_name" label="科目名称" min-width="180" />
            <el-table-column prop="period_debit" label="本期借方（缴纳）" width="140" align="right">
              <template #default="{ row }">{{ fmt(row.period_debit) }}</template>
            </el-table-column>
            <el-table-column prop="period_credit" label="本期贷方（计提）" width="140" align="right">
              <template #default="{ row }">
                <span style="color:#f56c6c">{{ fmt(row.period_credit) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="balance" label="期末余额（待缴）" width="140" align="right">
              <template #default="{ row }">
                <span :style="{ color: row.balance > 0 ? '#e6a23c' : '#67c23a', fontWeight: '600' }">
                  {{ fmt(row.balance) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- Tab B: 税务台账视角 -->
      <el-tab-pane label="税务台账（手工录入）" name="tax_records">
        <div style="margin:12px 0;color:#909399;font-size:12px">
          数据来源：税务模块手工录入的 fin_tax_records，按税种汇总应纳税额与已缴/待缴
        </div>

        <!-- 汇总 -->
        <el-row :gutter="12" style="margin-bottom:16px" v-if="taxRecords">
          <el-col :span="8">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">税种数</div>
              <div class="kpi-value">{{ taxRecords.rows.length }} 种</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">应纳税额合计</div>
              <div class="kpi-value primary">{{ fmt(taxRecords.total_tax_amount) }}</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">未缴税款合计</div>
              <div class="kpi-value danger">{{ fmt(taxRecords.total_unpaid) }}</div>
            </el-card>
          </el-col>
        </el-row>

        <el-card shadow="never">
          <el-table :data="taxRecords ? taxRecords.rows : []" stripe border v-loading="loading">
            <el-table-column prop="tax_name" label="税种名称" min-width="160" />
            <el-table-column prop="tax_type" label="税种类型" width="120">
              <template #default="{ row }">
                <el-tag size="small" type="info">{{ row.tax_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="tax_amount" label="应纳税额" width="130" align="right">
              <template #default="{ row }">{{ fmt(row.tax_amount) }}</template>
            </el-table-column>
            <el-table-column prop="paid_amount" label="已缴" width="130" align="right">
              <template #default="{ row }">
                <span style="color:#67c23a">{{ fmt(row.paid_amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="unpaid_amount" label="待缴" width="130" align="right">
              <template #default="{ row }">
                <span :style="{ color: row.unpaid_amount > 0 ? '#f56c6c' : '#909399', fontWeight: row.unpaid_amount > 0 ? '600' : 'normal' }">
                  {{ fmt(row.unpaid_amount) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-empty v-if="taxRecords && taxRecords.rows.length === 0 && !loading"
          description="本期暂无税务台账记录，请前往税务模块录入" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const loading = ref(false)
const period = ref(finStore.currentPeriod || new Date().toISOString().slice(0, 7))
const activeTab = ref('ledger')
const ledger = ref<any>(null)
const taxRecords = ref<any>(null)

const fmt = (v: number) => '¥' + (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

async function load() {
  if (!period.value) return
  loading.value = true
  try {
    const res: any = await request.get(`/finance/reports/tax-detail?book_id=${finStore.bookId}&period=${period.value}`)
    ledger.value = res.ledger_view
    taxRecords.value = res.tax_records_view
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
.kpi-card { text-align: center; }
.kpi-label { color: #909399; font-size: 12px; margin-bottom: 6px; }
.kpi-value { font-size: 20px; font-weight: 700; color: #303133; }
.kpi-value.primary { color: #409eff; }
.kpi-value.danger { color: #f56c6c; }
</style>
