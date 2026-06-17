<template>
  <div class="page-container">
    <div class="page-header"><h2>财务利润中心</h2></div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="费用补录" name="expense">
        <el-card>
          <el-form :model="expenseForm" label-width="110px" style="max-width:560px">
            <el-form-item label="费用日期" required>
              <el-date-picker v-model="expenseForm.expense_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
            <el-form-item label="关联门店">
              <el-input v-model="expenseForm.store_code" placeholder="留空=公司级费用" />
            </el-form-item>
            <el-form-item label="费用类型" required>
              <el-select v-model="expenseForm.expense_type" style="width:100%">
                <el-option label="租金" value="rent" />
                <el-option label="人工" value="labor" />
                <el-option label="水电" value="utilities" />
                <el-option label="物流" value="logistics" />
                <el-option label="管理费用" value="admin" />
                <el-option label="其他" value="other" />
              </el-select>
            </el-form-item>
            <el-form-item label="费用金额" required>
              <el-input-number v-model="expenseForm.expense_amount" :min="0.01" :precision="2" style="width:100%" />
            </el-form-item>
            <el-form-item label="数据类型">
              <el-radio-group v-model="expenseForm.data_type">
                <el-radio value="estimate">预估值（估算）</el-radio>
                <el-radio value="actual">财务核准（实际）</el-radio>
              </el-radio-group>
              <div style="font-size:11px;color:#e6a23c;margin-top:4px" v-if="expenseForm.data_type === 'estimate'">
                ⚠️ 预估值不作为正式财务数据，利润中会标注"预估"
              </div>
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="expenseForm.description" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitExpense" :loading="submitting">提交录入</el-button>
              <el-tag :type="expenseForm.data_type === 'actual' ? 'success' : 'warning'" style="margin-left:8px">
                {{ expenseForm.data_type === 'actual' ? '财务核准' : '预估值' }}
              </el-tag>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="现金补录" name="cash">
        <el-card>
          <el-form :model="cashForm" label-width="110px" style="max-width:560px">
            <el-form-item label="记录日期" required>
              <el-date-picker v-model="cashForm.record_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
            <el-form-item label="账户类型">
              <el-select v-model="cashForm.account_type" style="width:100%">
                <el-option label="银行账户" value="bank" />
                <el-option label="现金" value="cash" />
              </el-select>
            </el-form-item>
            <el-form-item label="账户名称">
              <el-input v-model="cashForm.account_name" placeholder="如：工商银行基本户" />
            </el-form-item>
            <el-form-item label="余额" required>
              <el-input-number v-model="cashForm.balance" :precision="2" style="width:100%" />
            </el-form-item>
            <el-form-item label="是否核准">
              <el-switch v-model="cashForm.is_verified" active-text="已财务核准" inactive-text="待核准" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitCash" :loading="submitting">提交录入</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="现金安全天数" name="cash_safety">
        <el-card v-loading="loadingCash">
          <div v-if="cashSafety">
            <el-row :gutter="16">
              <el-col :span="6">
                <el-statistic title="现金余额合计" :value="cashSafety.total_cash_balance || 0" prefix="¥" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="日均支出(近30天)" :value="cashSafety.daily_avg_expense_30d || 0" prefix="¥" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="现金安全天数" :value="cashSafety.cash_safety_days || 0" suffix="天" />
              </el-col>
              <el-col :span="6">
                <div style="padding-top:12px">
                  <el-tag
                    :type="cashSafety.risk_level === 'critical' ? 'danger' : cashSafety.risk_level === 'warning' ? 'warning' : 'success'"
                    style="font-size:14px; padding:8px 16px"
                  >
                    {{ cashSafety.risk_level === 'critical' ? '危险' : cashSafety.risk_level === 'warning' ? '预警' : '安全' }}
                  </el-tag>
                </div>
              </el-col>
            </el-row>
            <p style="color:#999;font-size:12px;margin-top:16px">{{ cashSafety.note }}</p>
          </div>
          <el-empty v-else description="暂无现金数据，请先补录" />
          <el-button @click="loadCashSafety" style="margin-top:8px" size="small">刷新</el-button>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="预估vs核准对比" name="comparison">
        <el-card v-loading="loadingComparison">
          <div v-if="comparison">
            <el-alert
              title="预估与财务核准利润差异对比"
              type="info"
              description="预估值来自未核准的费用录入；核准值来自财务已核准数据。差异过大时需排查。"
              show-icon
              style="margin-bottom:16px"
            />
            <el-table :data="comparison" stripe size="small">
              <el-table-column prop="stat_date" label="日期" width="120" />
              <el-table-column prop="estimated_profit" label="预估利润" :formatter="fmtMoney" />
              <el-table-column prop="actual_profit" label="核准利润" :formatter="fmtActual" />
              <el-table-column prop="difference" label="差异" :formatter="fmtDiff" />
              <el-table-column prop="difference_pct" label="差异率" :formatter="fmtDiffPct" />
            </el-table>
          </div>
          <el-empty v-else description="暂无对比数据" />
          <el-button @click="loadComparison" style="margin-top:8px" size="small">刷新</el-button>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { financeApi } from '@/api/finance'
import { ElMessage } from 'element-plus'

const activeTab = ref('expense')
const submitting = ref(false)
const loadingCash = ref(false)
const loadingComparison = ref(false)
const cashSafety = ref<any>(null)
const comparison = ref<any>(null)

const expenseForm = reactive({
  expense_date: '', store_code: '', expense_type: '', expense_amount: 0,
  data_type: 'estimate', description: ''
})
const cashForm = reactive({
  record_date: '', account_type: 'bank', account_name: '', balance: 0, is_verified: false
})

const fmtMoney = (row: any) => row.estimated_profit != null ? `¥${Number(row.estimated_profit).toFixed(0)}` : '--'
const fmtActual = (row: any) => row.actual_profit != null ? `¥${Number(row.actual_profit).toFixed(0)}` : '--'
const fmtDiff = (row: any) => {
  if (row.difference == null) return '--'
  const v = Number(row.difference)
  return (v >= 0 ? '+' : '') + `¥${v.toFixed(0)}`
}
const fmtDiffPct = (row: any) => row.difference_pct != null ? `${(Number(row.difference_pct) * 100).toFixed(1)}%` : '--'

const submitExpense = async () => {
  if (!expenseForm.expense_date || !expenseForm.expense_type || !expenseForm.expense_amount) {
    return ElMessage.warning('请填写必填项')
  }
  submitting.value = true
  try {
    await financeApi.createExpense(expenseForm)
    ElMessage.success('费用录入成功（' + (expenseForm.data_type === 'actual' ? '财务核准' : '预估值') + '）')
  } finally {
    submitting.value = false
  }
}

const submitCash = async () => {
  if (!cashForm.record_date || !cashForm.balance) return ElMessage.warning('请填写必填项')
  submitting.value = true
  try {
    await financeApi.createCash(cashForm)
    ElMessage.success('现金余额录入成功')
    loadCashSafety()
  } finally {
    submitting.value = false
  }
}

const loadCashSafety = async () => {
  loadingCash.value = true
  try {
    const res = await financeApi.getCashSafety()
    cashSafety.value = res.data.data
  } catch {} finally {
    loadingCash.value = false
  }
}

const loadComparison = async () => {
  loadingComparison.value = true
  try {
    const res = await financeApi.getProfitComparison()
    comparison.value = res.data.data
  } catch {} finally {
    loadingComparison.value = false
  }
}

onMounted(() => {
  loadCashSafety()
  loadComparison()
})
</script>

<style scoped>
.page-container { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 18px; color: #333; }
</style>
