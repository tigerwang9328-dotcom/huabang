<template>
  <div class="fc-cashier">
    <el-tabs v-model="activeTab" class="fc-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="现金账户" name="accounts" />
      <el-tab-pane label="银行流水" name="transactions" />
      <el-tab-pane label="银行对账" name="reconciliation" />
    </el-tabs>

    <!-- 现金账户 Tab -->
    <template v-if="activeTab === 'accounts'">
      <div class="fc-card">
        <div class="fc-toolbar">
          <div class="fc-toolbar-left">
            <el-button type="primary" @click="openAccountDialog()">
              新建账户
            </el-button>
          </div>
          <div class="fc-toolbar-right">
            <el-button @click="fetchAccounts" :icon="'Refresh'">刷新</el-button>
          </div>
        </div>

        <el-table
          v-loading="accountLoading"
          :data="accountData"
          border
          stripe
          max-height="calc(100vh - 300px)"
        >
          <el-table-column prop="account_code" label="账户编码" width="130" show-overflow-tooltip />
          <el-table-column prop="account_name" label="账户名称" min-width="180" show-overflow-tooltip />
          <el-table-column label="账户类型" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.account_type === 'bank' ? 'primary' : 'success'" size="small">
                {{ row.account_type === 'bank' ? '银行' : '现金' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="bank_name" label="银行名称" width="140" show-overflow-tooltip />
          <el-table-column label="账号" width="180" show-overflow-tooltip>
            <template #default="{ row }">
              {{ maskAccount(row.account_number) }}
            </template>
          </el-table-column>
          <el-table-column prop="currency" label="币种" width="80" align="center" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === 'active' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openAccountDialog(row)">
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="fc-pagination">
          <el-pagination
            v-model:current-page="accountPage"
            v-model:page-size="accountPageSize"
            :total="accountTotal"
            layout="total, sizes, prev, pager, next"
            @change="fetchAccounts"
          />
        </div>
      </div>
    </template>

    <!-- 银行流水 Tab -->
    <template v-if="activeTab === 'transactions'">
      <div class="fc-card">
        <div class="fc-toolbar">
          <div class="fc-toolbar-left">
            <el-select
              v-model="txnAccountId"
              placeholder="选择现金账户"
              clearable
              filterable
              style="width: 200px"
              @change="fetchTransactions"
            >
              <el-option
                v-for="a in accountOptions"
                :key="a.id"
                :label="`${a.account_code} - ${a.account_name}`"
                :value="a.id"
              />
            </el-select>
            <el-date-picker
              v-model="txnDateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              style="width: 270px"
              @change="fetchTransactions"
            />
            <el-button type="primary" @click="openTxnDialog()">
              录入流水
            </el-button>
          </div>
          <div class="fc-toolbar-right">
            <el-button @click="fetchTransactions" :icon="'Refresh'">刷新</el-button>
          </div>
        </div>

        <el-table
          v-loading="txnLoading"
          :data="txnData"
          border
          stripe
          max-height="calc(100vh - 320px)"
        >
          <el-table-column prop="date" label="日期" width="120" align="center" />
          <el-table-column label="方向" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.direction === 'in' ? 'success' : 'danger'" size="small">
                {{ row.direction === 'in' ? '收入' : '支出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">
              <span :style="{ color: row.direction === 'in' ? '#16a34a' : '#dc2626' }">
                {{ formatAmount(row.amount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="counterparty_name" label="对方名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="reference_no" label="参考号" width="160" show-overflow-tooltip />
          <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
          <el-table-column prop="source" label="来源" width="100" align="center" />
        </el-table>

        <div class="fc-pagination">
          <el-pagination
            v-model:current-page="txnPage"
            v-model:page-size="txnPageSize"
            :total="txnTotal"
            layout="total, sizes, prev, pager, next"
            @change="fetchTransactions"
          />
        </div>
      </div>
    </template>

    <!-- 银行对账 Tab -->
    <template v-if="activeTab === 'reconciliation'">
      <div class="fc-card">
        <div class="fc-toolbar">
          <div class="fc-toolbar-left">
            <el-select
              v-model="reconAccountId"
              placeholder="选择现金账户"
              clearable
              filterable
              style="width: 220px"
              @change="onReconAccountChange"
            >
              <el-option
                v-for="a in accountOptions"
                :key="a.id"
                :label="`${a.account_code} - ${a.account_name}`"
                :value="a.id"
              />
            </el-select>
            <el-select
              v-model="reconPeriodId"
              placeholder="选择期间"
              clearable
              filterable
              style="width: 200px"
              @change="fetchReconTransactions"
            >
              <el-option
                v-for="p in periods"
                :key="p.id"
                :label="p.label"
                :value="p.id"
              />
            </el-select>
          </div>
          <div class="fc-toolbar-right">
            <el-button @click="fetchReconTransactions" :icon="'Refresh'">刷新</el-button>
          </div>
        </div>

        <div class="fc-recon-balance-row">
          <div class="fc-recon-balance-item">
            <span class="fc-recon-balance-label">银行对账单余额</span>
            <el-input-number
              v-model="bankBalance"
              :min="0"
              :precision="2"
              :controls="false"
              style="width: 200px"
              placeholder="请输入余额"
            />
          </div>
          <div class="fc-recon-balance-item">
            <span class="fc-recon-balance-label">账面余额</span>
            <span class="fc-recon-balance-value">{{ formatAmount(bookBalance) }}</span>
          </div>
          <div class="fc-recon-balance-item">
            <span class="fc-recon-balance-label">差异</span>
            <span
              class="fc-recon-balance-value"
              :style="{ color: balanceDiff !== 0 ? '#dc2626' : '#16a34a' }"
            >
              {{ formatAmount(balanceDiff) }}
            </span>
          </div>
        </div>

        <el-table
          ref="reconTableRef"
          v-loading="reconLoading"
          :data="reconTxnData"
          border
          stripe
          max-height="calc(100vh - 480px)"
          @selection-change="onReconSelectionChange"
        >
          <el-table-column type="selection" width="50" />
          <el-table-column prop="date" label="日期" width="120" align="center" />
          <el-table-column label="方向" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.direction === 'in' ? 'success' : 'danger'" size="small">
                {{ row.direction === 'in' ? '收入' : '支出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.amount) }}
            </template>
          </el-table-column>
          <el-table-column prop="counterparty_name" label="对方名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="reference_no" label="参考号" width="160" show-overflow-tooltip />
          <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.reconciled ? 'success' : 'info'" size="small">
                {{ row.reconciled ? '已对账' : '未对账' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <div class="fc-recon-footer">
          <el-button
            type="primary"
            :disabled="selectedTxnIds.length === 0"
            :loading="reconRunning"
            @click="runReconciliation"
          >
            对账 (已选 {{ selectedTxnIds.length }} 笔)
          </el-button>
        </div>
      </div>
    </template>

    <!-- 现金账户 新建/编辑弹窗 -->
    <el-dialog
      v-model="accountDialogVisible"
      :title="accountForm.id ? '编辑账户' : '新建账户'"
      width="560px"
      destroy-on-close
    >
      <el-form ref="accountFormRef" :model="accountForm" label-width="100px">
        <el-form-item label="账户编码" prop="account_code">
          <el-input v-model="accountForm.account_code" placeholder="请输入账户编码" />
        </el-form-item>
        <el-form-item label="账户名称" prop="account_name">
          <el-input v-model="accountForm.account_name" placeholder="请输入账户名称" />
        </el-form-item>
        <el-form-item label="账户类型" prop="account_type">
          <el-select v-model="accountForm.account_type" placeholder="选择账户类型" style="width: 100%">
            <el-option label="银行" value="bank" />
            <el-option label="现金" value="cash" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联科目" prop="account_id">
          <el-select
            v-model="accountForm.account_id"
            placeholder="选择银行科目"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="a in chartAccounts"
              :key="a.id"
              :label="`${a.code} - ${a.name}`"
              :value="a.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="银行名称" prop="bank_name">
          <el-input v-model="accountForm.bank_name" placeholder="请输入银行名称" />
        </el-form-item>
        <el-form-item label="账号" prop="account_number">
          <el-input v-model="accountForm.account_number" placeholder="请输入账号" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="accountSaving" @click="saveAccount">保存</el-button>
      </template>
    </el-dialog>

    <!-- 银行流水 录入弹窗 -->
    <el-dialog
      v-model="txnDialogVisible"
      title="录入流水"
      width="560px"
      destroy-on-close
    >
      <el-form ref="txnFormRef" :model="txnForm" label-width="100px">
        <el-form-item label="现金账户" prop="cash_account_id">
          <el-select
            v-model="txnForm.cash_account_id"
            placeholder="选择现金账户"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="a in accountOptions"
              :key="a.id"
              :label="`${a.account_code} - ${a.account_name}`"
              :value="a.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="日期" prop="date">
          <el-date-picker
            v-model="txnForm.date"
            type="date"
            placeholder="选择日期"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="方向" prop="direction">
          <el-select v-model="txnForm.direction" placeholder="选择方向" style="width: 100%">
            <el-option label="收入" value="in" />
            <el-option label="支出" value="out" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额" prop="amount">
          <el-input-number
            v-model="txnForm.amount"
            :min="0"
            :precision="2"
            :controls="false"
            style="width: 100%"
            placeholder="请输入金额"
          />
        </el-form-item>
        <el-form-item label="对方名称" prop="counterparty_name">
          <el-input v-model="txnForm.counterparty_name" placeholder="请输入对方名称" />
        </el-form-item>
        <el-form-item label="参考号" prop="reference_no">
          <el-input v-model="txnForm.reference_no" placeholder="请输入参考号" />
        </el-form-item>
        <el-form-item label="摘要" prop="summary">
          <el-input
            v-model="txnForm.summary"
            type="textarea"
            :rows="2"
            placeholder="请输入摘要"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="txnDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="txnSaving" @click="saveTransaction">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { financeCenterApi, type FinBook } from "@/api/financeCenter"

const activeTab = ref('accounts')

// ============ 公共数据 ============
const selectedBookId = ref<number>(0)
const bookList = ref<FinBook[]>([])
const accountOptions = ref<any[]>([])
const chartAccounts = ref<any[]>([])
const periods = ref<any[]>([])

// ============ 现金账户 ============
const accountData = ref<any[]>([])
const accountLoading = ref(false)
const accountPage = ref(1)
const accountPageSize = ref(20)
const accountTotal = ref(0)
const accountDialogVisible = ref(false)
const accountSaving = ref(false)
const accountFormRef = ref()
const accountForm = ref<any>({
  id: null,
  account_code: '',
  account_name: '',
  account_type: 'bank',
  account_id: null,
  bank_name: '',
  account_number: '',
})

// ============ 银行流水 ============
const txnAccountId = ref<number | null>(null)
const txnDateRange = ref<string[]>([])
const txnData = ref<any[]>([])
const txnLoading = ref(false)
const txnPage = ref(1)
const txnPageSize = ref(20)
const txnTotal = ref(0)
const txnDialogVisible = ref(false)
const txnSaving = ref(false)
const txnFormRef = ref()
const txnForm = ref<any>({
  cash_account_id: null,
  date: '',
  direction: 'in',
  amount: 0,
  counterparty_name: '',
  reference_no: '',
  summary: '',
})

// ============ 银行对账 ============
const reconAccountId = ref<number | null>(null)
const reconPeriodId = ref<number | null>(null)
const reconTxnData = ref<any[]>([])
const reconLoading = ref(false)
const reconRunning = ref(false)
const bankBalance = ref<number>(0)
const selectedTxnIds = ref<number[]>([])
const reconTableRef = ref()

const bookBalance = computed(() => {
  return reconTxnData.value
    .filter((r: any) => r.reconciled)
    .reduce((acc: number, r: any) => {
      return acc + (r.direction === 'in' ? Number(r.amount) || 0 : -(Number(r.amount) || 0))
    }, 0)
})

const balanceDiff = computed(() => {
  return (bankBalance.value || 0) - bookBalance.value
})

// ============ 工具函数 ============
function formatAmount(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function maskAccount(accountNumber: string | null | undefined): string {
  if (!accountNumber) return '—'
  if (accountNumber.length <= 4) return '****'
  return '****' + accountNumber.slice(-4)
}

// ============ 数据加载 ============
async function loadBooks() {
  try {
    const res = await financeCenterApi.listBooks()
    bookList.value = (res.data as any)?.data || []
    if (bookList.value.length > 0 && !selectedBookId.value) {
      selectedBookId.value = bookList.value[0].id
    }
  } catch { /* 非关键 */ }
}

async function loadAccounts() {
  try {
    const res = await financeCenterApi.listCashAccounts({ book_id: selectedBookId.value, page: 1, page_size: 200 })
    const data = (res.data as any)?.data || []
    const list = data.items || data.list || data || []
    accountOptions.value = list
  } catch {
    // 非关键
  }
}

async function loadChartAccounts() {
  try {
    const res = await financeCenterApi.listAccounts({ book_id: selectedBookId.value })
    chartAccounts.value = (res.data as any)?.data || []
  } catch {
    // 非关键
  }
}

async function fetchAccounts() {
  accountLoading.value = true
  try {
    const res = await financeCenterApi.listCashAccounts({
      book_id: selectedBookId.value,
      page: accountPage.value,
      page_size: accountPageSize.value,
    })
    const data = (res.data as any)?.data || {}
    accountData.value = data.items || data.list || data || []
    accountTotal.value = data.total || 0
  } catch {
    ElMessage.error('加载账户列表失败')
  } finally {
    accountLoading.value = false
  }
}

async function fetchTransactions() {
  txnLoading.value = true
  try {
    const params: any = {
      page: txnPage.value,
      page_size: txnPageSize.value,
    }
    if (txnAccountId.value) params.cash_account_id = txnAccountId.value
    if (txnDateRange.value && txnDateRange.value.length === 2) {
      params.start_date = txnDateRange.value[0]
      params.end_date = txnDateRange.value[1]
    }
    const res = await financeCenterApi.listBankTransactions({ book_id: selectedBookId.value, ...params })
    const data = (res.data as any)?.data || {}
    txnData.value = data.items || data.list || data || []
    txnTotal.value = data.total || 0
  } catch {
    ElMessage.error('加载银行流水失败')
  } finally {
    txnLoading.value = false
  }
}

async function fetchReconTransactions() {
  if (!reconAccountId.value) return
  reconLoading.value = true
  try {
    const params: any = {
      cash_account_id: reconAccountId.value,
      page: 1,
      page_size: 500,
    }
    if (reconPeriodId.value) params.period_id = reconPeriodId.value
    const res = await financeCenterApi.listBankTransactions({ book_id: selectedBookId.value, ...params })
    const data = (res.data as any)?.data || {}
    reconTxnData.value = data.items || data.list || data || []
  } catch {
    ElMessage.error('加载对账流水失败')
  } finally {
    reconLoading.value = false
  }
}

async function onReconAccountChange() {
  periods.value = []
  reconPeriodId.value = null
  bankBalance.value = 0
  selectedTxnIds.value = []
  reconTxnData.value = []
  if (!reconAccountId.value) return
  try {
    const res = await financeCenterApi.listPeriods({ book_id: selectedBookId.value })
    periods.value = (res.data as any)?.data || []
  } catch {
    // 非关键
  }
}
// ============ 现金账户操作 ============
function openAccountDialog(row?: any) {
  if (row) {
    accountForm.value = { ...row }
  } else {
    accountForm.value = {
      id: null,
      account_code: '',
      account_name: '',
      account_type: 'bank',
      account_id: null,
      bank_name: '',
      account_number: '',
    }
  }
  accountDialogVisible.value = true
}

async function saveAccount() {
  accountSaving.value = true
  try {
    await financeCenterApi.upsertCashAccount(accountForm.value)
    ElMessage.success('保存成功')
    accountDialogVisible.value = false
    fetchAccounts()
    loadAccounts()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    accountSaving.value = false
  }
}

// ============ 银行流水操作 ============
function openTxnDialog() {
  txnForm.value = {
    cash_account_id: txnAccountId.value,
    date: '',
    direction: 'in',
    amount: 0,
    counterparty_name: '',
    reference_no: '',
    summary: '',
  }
  txnDialogVisible.value = true
}

async function saveTransaction() {
  txnSaving.value = true
  try {
    await financeCenterApi.createBankTransaction(txnForm.value)
    ElMessage.success('录入成功')
    txnDialogVisible.value = false
    fetchTransactions()
  } catch {
    ElMessage.error('录入失败')
  } finally {
    txnSaving.value = false
  }
}

// ============ 银行对账操作 ============
function onReconSelectionChange(rows: any[]) {
  selectedTxnIds.value = rows.map((r: any) => r.id)
}

async function runReconciliation() {
  if (selectedTxnIds.value.length === 0) {
    ElMessage.warning('请先选择需要对账的流水')
    return
  }
  reconRunning.value = true
  try {
    await financeCenterApi.createReconciliation({
      cash_account_id: reconAccountId.value,
      period_id: reconPeriodId.value,
      transaction_ids: selectedTxnIds.value,
      bank_balance: bankBalance.value,
    })
    ElMessage.success('对账完成')
    selectedTxnIds.value = []
    fetchReconTransactions()
  } catch {
    ElMessage.error('对账失败')
  } finally {
    reconRunning.value = false
  }
}

// ============ Tab 切换 ============
function handleTabChange(tab: string) {
  if (tab === 'accounts') {
    fetchAccounts()
  } else if (tab === 'transactions') {
    fetchTransactions()
  } else if (tab === 'reconciliation') {
    // 手动触发
  }
}

onMounted(async () => {
  await loadBooks()
  if (selectedBookId.value) {
    fetchAccounts()
    loadAccounts()
    loadChartAccounts()
  }
})
</script>

<script lang="ts">
export default { name: 'FinanceCashier' }
</script>

<style scoped>
.fc-cashier {
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
.fc-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.fc-recon-balance-row {
  display: flex;
  align-items: center;
  gap: 40px;
  padding: 16px;
  margin-bottom: 16px;
  background: #f5f6f8;
  border-radius: 8px;
  flex-wrap: wrap;
}
.fc-recon-balance-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.fc-recon-balance-label {
  font-size: 14px;
  color: #606266;
  white-space: nowrap;
}
.fc-recon-balance-value {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
}
.fc-recon-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>