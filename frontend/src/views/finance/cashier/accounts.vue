<template>
  <div>
    <!-- 页面标题 -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h3 style="margin:0;font-size:18px;font-weight:700;color:var(--text-1)">出纳管理</h3>
      <el-button @click="refresh" :loading="loading">
        <el-icon style="margin-right:4px"><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <el-tabs v-model="activeTab">

      <!-- ════════════════ Tab 1：资金账户 ════════════════ -->
      <el-tab-pane label="资金账户" name="accounts">

        <!-- KPI 卡片 -->
        <el-row :gutter="12" style="margin-bottom:20px">
          <el-col :span="4">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">账户总数</div>
              <div class="kpi-value">{{ stats.account_count }} 个</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">总余额</div>
              <div class="kpi-value primary">{{ fmt(stats.total_balance) }}</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">今日流入</div>
              <div class="kpi-value success">{{ fmt(stats.today_in) }}</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">今日流出</div>
              <div class="kpi-value danger">{{ fmt(stats.today_out) }}</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">本月流入</div>
              <div class="kpi-value success">{{ fmt(stats.month_in) }}</div>
            </el-card>
          </el-col>
          <el-col :span="4">
            <el-card shadow="never" class="kpi-card">
              <div class="kpi-label">本月流出</div>
              <div class="kpi-value danger">{{ fmt(stats.month_out) }}</div>
            </el-card>
          </el-col>
        </el-row>

        <!-- 账户列表 -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <span style="font-size:14px;font-weight:600;color:var(--text-1)">资金账户列表</span>
          <div style="display:flex;gap:8px">
            <el-button @click="openFlowDialog()">新增明细</el-button>
            <el-button type="primary" @click="openAccountDialog()">新增账户</el-button>
          </div>
        </div>

        <el-table :data="accounts" stripe border v-loading="loading">
          <el-table-column prop="account_name" label="账户名称" min-width="150" />
          <el-table-column prop="account_type" label="类型" width="100">
            <template #default="{ row }">
              <el-tag :type="typeColor(row.account_type)" size="small">{{ typeLabel(row.account_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default>—</template>
          </el-table-column>
          <el-table-column prop="balance" label="当前余额" width="130" align="right">
            <template #default="{ row }">
              <span style="font-weight:600;color:var(--text-1)">{{ fmt(row.balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最近更新" width="110" align="center">
            <template #default>{{ todayStr }}</template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="viewAccountFlows(row)">查看流水</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && accounts.length === 0" description="暂无资金账户，请先新增账户" />
      </el-tab-pane>

      <!-- ════════════════ Tab 2：日记账 ════════════════ -->
      <el-tab-pane label="日记账" name="journal">
        <div style="display:flex;gap:8px;margin-bottom:16px;align-items:center">
          <el-select v-model="flowAccountId" placeholder="全部账户" clearable style="width:180px"
            @change="loadFlows">
            <el-option v-for="a in accounts" :key="a.id" :label="a.account_name" :value="a.id" />
          </el-select>
          <el-button @click="loadFlows" :loading="flowLoading">查询</el-button>
          <el-button type="primary" @click="openFlowDialog()">新增明细</el-button>
        </div>

        <el-table :data="flows" stripe border v-loading="flowLoading" max-height="520">
          <el-table-column prop="flow_date" label="日期" width="110" />
          <el-table-column label="账户" width="140">
            <template #default="{ row }">{{ getAccountName(row.cash_account_id) }}</template>
          </el-table-column>
          <el-table-column label="收入" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row.flow_type === 'in'" style="color:#67c23a;font-weight:600">{{ fmt(row.amount) }}</span>
              <span v-else style="color:#c0c4cc">—</span>
            </template>
          </el-table-column>
          <el-table-column label="支出" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row.flow_type === 'out'" style="color:#f56c6c;font-weight:600">{{ fmt(row.amount) }}</span>
              <span v-else style="color:#c0c4cc">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="category" label="类别" width="110" show-overflow-tooltip />
          <el-table-column prop="counterpart" label="对方" width="130" show-overflow-tooltip />
          <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
        </el-table>

        <div v-if="flows.length" style="display:flex;justify-content:flex-end;gap:24px;margin-top:10px;font-size:13px;color:#606266">
          <span>合计流入：<b style="color:#67c23a">{{ fmt(flowStats.total_in) }}</b></span>
          <span>合计流出：<b style="color:#f56c6c">{{ fmt(flowStats.total_out) }}</b></span>
        </div>
        <el-empty v-if="!flowLoading && flows.length === 0" description="暂无日记账记录" />
      </el-tab-pane>

      <!-- ════════════════ Tab 3：收支汇总 ════════════════ -->
      <el-tab-pane label="收支汇总" name="summary">
        <el-row :gutter="16" style="margin-bottom:16px">
          <el-col :span="8">
            <el-card shadow="never" class="summary-card">
              <div class="summary-label">本月总流入</div>
              <div class="summary-value success">{{ fmt(stats.month_in) }}</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="summary-card">
              <div class="summary-label">本月总流出</div>
              <div class="summary-value danger">{{ fmt(stats.month_out) }}</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="summary-card">
              <div class="summary-label">本月净流入</div>
              <div class="summary-value"
                :class="stats.month_in - stats.month_out >= 0 ? 'success' : 'danger'">
                {{ fmt(stats.month_in - stats.month_out) }}
              </div>
            </el-card>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-card shadow="never" class="summary-card">
              <div class="summary-label">今日流入</div>
              <div class="summary-value success">{{ fmt(stats.today_in) }}</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="summary-card">
              <div class="summary-label">今日流出</div>
              <div class="summary-value danger">{{ fmt(stats.today_out) }}</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" class="summary-card">
              <div class="summary-label">账户总余额</div>
              <div class="summary-value primary">{{ fmt(stats.total_balance) }}</div>
            </el-card>
          </el-col>
        </el-row>
        <div style="margin-top:24px;padding:20px;background:#f8f9fa;border-radius:8px;color:#909399;font-size:13px;text-align:center">
          按科目/类别的收支分类明细图表功能建设中，敬请期待
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ════════════════ 新增账户 Dialog ════════════════ -->
    <el-dialog v-model="showAccountDialog" title="新增账户" width="480px" destroy-on-close>
      <el-form :model="accountForm" label-width="90px">
        <el-form-item label="账户名称" required>
          <el-input v-model="accountForm.account_name" placeholder="如：工商银行基本账户" />
        </el-form-item>
        <el-form-item label="账户类型">
          <el-select v-model="accountForm.account_type" style="width:100%">
            <el-option label="银行账户" value="bank" />
            <el-option label="支付宝" value="alipay" />
            <el-option label="微信支付" value="wechat" />
            <el-option label="现金" value="cash" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="开户行/平台">
          <el-input v-model="accountForm.bank_name" placeholder="银行名称或平台名称（选填）" />
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="accountForm.account_no" placeholder="银行账号或账户标识（选填）" />
        </el-form-item>
        <el-form-item label="期初余额">
          <el-input-number v-model="accountForm.balance" :min="0" :precision="2" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAccountDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAccount" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- ════════════════ 新增明细 Dialog ════════════════ -->
    <el-dialog v-model="showFlowDialog" title="新增收支明细" width="480px" destroy-on-close>
      <el-form :model="flowForm" label-width="90px">
        <el-form-item label="账户" required>
          <el-select v-model="flowForm.cash_account_id" style="width:100%" placeholder="请选择账户">
            <el-option v-for="a in accounts" :key="a.id" :label="a.account_name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期" required>
          <el-date-picker v-model="flowForm.flow_date" type="date" value-format="YYYY-MM-DD"
            style="width:100%" placeholder="选择日期" />
        </el-form-item>
        <el-form-item label="收支类型" required>
          <el-radio-group v-model="flowForm.flow_type">
            <el-radio value="in">收入</el-radio>
            <el-radio value="out">支出</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input-number v-model="flowForm.amount" :min="0.01" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="flowForm.category" style="width:100%" clearable placeholder="选择类别（选填）">
            <el-option label="销售回款" value="销售回款" />
            <el-option label="供应商付款" value="供应商付款" />
            <el-option label="工资发放" value="工资发放" />
            <el-option label="房租" value="房租" />
            <el-option label="税费" value="税费" />
            <el-option label="贷款" value="贷款" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="对方">
          <el-input v-model="flowForm.counterpart" placeholder="交易对手名称（选填）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="flowForm.remark" type="textarea" :rows="2" placeholder="备注（选填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFlowDialog = false">取消</el-button>
        <el-button type="primary" @click="saveFlow" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'
import dayjs from 'dayjs'

const finStore = useFinanceStore()
const loading   = ref(false)
const flowLoading = ref(false)
const saving    = ref(false)
const activeTab = ref('accounts')

const todayStr  = dayjs().format('YYYY-MM-DD')

// ── 数据 ──
const accounts = ref<any[]>([])
const flows    = ref<any[]>([])
const flowStats = ref({ total_in: 0, total_out: 0 })
const stats = ref({
  account_count: 0,
  total_balance: 0,
  today_in: 0,
  today_out: 0,
  month_in: 0,
  month_out: 0,
})

// ── 筛选 ──
const flowAccountId = ref<number | null>(null)

// ── 对话框状态 ──
const showAccountDialog = ref(false)
const showFlowDialog    = ref(false)

const defaultAccountForm = () => ({
  account_name: '',
  account_type: 'bank',
  bank_name: '',
  account_no: '',
  balance: 0,
})
const defaultFlowForm = () => ({
  cash_account_id: null as number | null,
  flow_date: dayjs().format('YYYY-MM-DD'),
  flow_type: 'out' as 'in' | 'out',
  amount: 0,
  category: '',
  counterpart: '',
  remark: '',
})
const accountForm = ref(defaultAccountForm())
const flowForm    = ref(defaultFlowForm())

// ── 格式化 ──
const fmt = (v: number) =>
  '¥' + (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// ── 账户类型 ──
const typeLabel = (t: string) =>
  ({ bank: '银行', alipay: '支付宝', wechat: '微信支付', cash: '现金', other: '其他' }[t] || t)
const typeColor = (t: string) =>
  ({ bank: '', alipay: 'primary', wechat: 'success', cash: 'warning', other: 'info' }[t] || 'info') as any

const getAccountName = (id: number) =>
  accounts.value.find(a => a.id === id)?.account_name || String(id)

// ── API 调用 ──
async function loadAccounts() {
  loading.value = true
  try {
    const res: any = await request.get(`/finance/cashier/accounts?book_id=${finStore.bookId}`)
    accounts.value = res.rows || []
  } catch {
    ElMessage.error('加载账户失败')
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res: any = await request.get(`/finance/cashier/stats?book_id=${finStore.bookId}`)
    stats.value = res
  } catch {
    // stats 加载失败不阻塞页面
  }
}

async function loadFlows() {
  flowLoading.value = true
  try {
    let url = `/finance/cashier/flows?book_id=${finStore.bookId}&limit=200`
    if (flowAccountId.value) url += `&account_id=${flowAccountId.value}`
    const res: any = await request.get(url)
    flows.value = res.rows || []
    flowStats.value = { total_in: res.total_in || 0, total_out: res.total_out || 0 }
  } catch {
    ElMessage.error('加载流水失败')
  } finally {
    flowLoading.value = false
  }
}

async function refresh() {
  await Promise.all([loadAccounts(), loadStats(), loadFlows()])
}

// ── 打开弹窗 ──
function openAccountDialog() {
  accountForm.value = defaultAccountForm()
  showAccountDialog.value = true
}
function openFlowDialog(account?: any) {
  flowForm.value = defaultFlowForm()
  if (account) flowForm.value.cash_account_id = account.id
  showFlowDialog.value = true
}
function viewAccountFlows(row: any) {
  flowAccountId.value = row.id
  activeTab.value = 'journal'
  loadFlows()
}

// ── 保存账户 ──
async function saveAccount() {
  if (!accountForm.value.account_name.trim()) {
    ElMessage.warning('请填写账户名称')
    return
  }
  saving.value = true
  try {
    await request.post(
      `/finance/cashier/accounts?book_id=${finStore.bookId}`,
      accountForm.value,
    )
    ElMessage.success('账户已创建')
    showAccountDialog.value = false
    await Promise.all([loadAccounts(), loadStats()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  } finally {
    saving.value = false
  }
}

// ── 保存流水 ──
async function saveFlow() {
  if (!flowForm.value.cash_account_id) { ElMessage.warning('请选择账户'); return }
  if (!flowForm.value.flow_date)        { ElMessage.warning('请选择日期'); return }
  if (flowForm.value.amount <= 0)       { ElMessage.warning('金额必须大于0'); return }
  saving.value = true
  try {
    await request.post(
      `/finance/cashier/flows?book_id=${finStore.bookId}`,
      flowForm.value,
    )
    ElMessage.success('明细已录入')
    showFlowDialog.value = false
    await Promise.all([loadAccounts(), loadStats(), loadFlows()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '录入失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadAccounts()
  await Promise.all([loadStats(), loadFlows()])
})
</script>

<style scoped>
.kpi-card { text-align: center; }
.kpi-label {
  font-size: 12px; color: var(--text-4, #9ca3af); margin-bottom: 6px; white-space: nowrap;
}
.kpi-value {
  font-size: 20px; font-weight: 700; color: var(--text-1, #1e293b);
}
.kpi-value.primary { color: #409eff; }
.kpi-value.success { color: #67c23a; }
.kpi-value.danger  { color: #f56c6c; }

.summary-card { text-align: center; margin-bottom: 16px; }
.summary-label {
  font-size: 13px; color: var(--text-4, #9ca3af); margin-bottom: 8px;
}
.summary-value {
  font-size: 24px; font-weight: 700; color: var(--text-1, #1e293b);
}
.summary-value.primary { color: #409eff; }
.summary-value.success { color: #67c23a; }
.summary-value.danger  { color: #f56c6c; }
</style>
