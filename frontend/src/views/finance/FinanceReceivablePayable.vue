<template>
  <div class="fc-receivable-payable">
    <el-tabs v-model="activeTab" class="fc-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="应收单" name="receivable" />
      <el-tab-pane label="应付单" name="payable" />
      <el-tab-pane label="结算核销" name="settlement" />
      <el-tab-pane label="账龄分析" name="aging" />
    </el-tabs>

    <!-- 应收单 / 应付单 Tab -->
    <template v-if="activeTab === 'receivable' || activeTab === 'payable'">
      <div class="fc-card">
        <div class="fc-toolbar">
          <div class="fc-toolbar-left">
            <el-select
              v-model="docBookId"
              placeholder="选择账套"
              clearable
              filterable
              style="width: 200px"
              @change="fetchDocs"
            >
              <el-option v-for="b in books" :key="b.id" :label="b.name" :value="b.id" />
            </el-select>
            <el-select
              v-model="docStatus"
              placeholder="选择状态"
              clearable
              style="width: 160px"
              @change="fetchDocs"
            >
              <el-option label="草稿" value="draft" />
              <el-option label="已确认" value="confirmed" />
              <el-option label="已结算" value="settled" />
              <el-option label="已关闭" value="closed" />
            </el-select>
            <el-button type="primary" @click="openDocDialog()">
              {{ activeTab === 'receivable' ? '新建应收单' : '新建应付单' }}
            </el-button>
          </div>
          <div class="fc-toolbar-right">
            <el-button @click="fetchDocs" :icon="'Refresh'">刷新</el-button>
          </div>
        </div>

        <el-table
          v-loading="docLoading"
          :data="docData"
          border
          stripe
          max-height="calc(100vh - 320px)"
        >
          <el-table-column prop="doc_no" label="单据号" width="160" show-overflow-tooltip />
          <el-table-column prop="aux_item_name" label="往来单位" min-width="180" show-overflow-tooltip />
          <el-table-column prop="biz_date" label="业务日期" width="120" align="center" />
          <el-table-column prop="due_date" label="到期日" width="120" align="center" />
          <el-table-column label="原币金额" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.original_amount) }}
            </template>
          </el-table-column>
          <el-table-column label="已结算" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.settled_amount) }}
            </template>
          </el-table-column>
          <el-table-column label="未结算" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.unsettled_amount) }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="docStatusTag(row.status)" size="small">
                {{ docStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="viewDocDetail(row)">
                详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="fc-pagination">
          <el-pagination
            v-model:current-page="docPage"
            v-model:page-size="docPageSize"
            :total="docTotal"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            @change="fetchDocs"
          />
        </div>
      </div>
    </template>

    <!-- 结算核销 Tab -->
    <template v-if="activeTab === 'settlement'">
      <div class="fc-card">
        <div class="fc-toolbar">
          <div class="fc-toolbar-left">
            <el-select
              v-model="settlementBookId"
              placeholder="选择账套"
              clearable
              filterable
              style="width: 200px"
              @change="fetchSettlements"
            >
              <el-option v-for="b in books" :key="b.id" :label="b.name" :value="b.id" />
            </el-select>
            <el-button type="primary" @click="openSettlementDialog()">
              新建结算
            </el-button>
          </div>
          <div class="fc-toolbar-right">
            <el-button @click="fetchSettlements" :icon="'Refresh'">刷新</el-button>
          </div>
        </div>

        <el-table
          v-loading="settlementLoading"
          :data="settlementData"
          border
          stripe
          max-height="calc(100vh - 320px)"
        >
          <el-table-column label="结算类型" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.settlement_type === 'receipt' ? 'success' : 'danger'" size="small">
                {{ row.settlement_type === 'receipt' ? '收款' : '付款' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="related_doc_no" label="关联单据" width="160" show-overflow-tooltip />
          <el-table-column prop="settlement_date" label="结算日期" width="120" align="center" />
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.amount) }}
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
        </el-table>

        <div class="fc-pagination">
          <el-pagination
            v-model:current-page="settlementPage"
            v-model:page-size="settlementPageSize"
            :total="settlementTotal"
            layout="total, sizes, prev, pager, next"
            @change="fetchSettlements"
          />
        </div>
      </div>
    </template>

    <!-- 账龄分析 Tab -->
    <template v-if="activeTab === 'aging'">
      <div class="fc-card">
        <div class="fc-toolbar">
          <div class="fc-toolbar-left">
            <el-select
              v-model="agingBookId"
              placeholder="选择账套"
              clearable
              filterable
              style="width: 200px"
              @change="fetchAging"
            >
              <el-option v-for="b in books" :key="b.id" :label="b.name" :value="b.id" />
            </el-select>
            <el-date-picker
              v-model="agingDate"
              type="date"
              placeholder="截止日期"
              value-format="YYYY-MM-DD"
              style="width: 180px"
              @change="fetchAging"
            />
          </div>
          <div class="fc-toolbar-right">
            <el-button @click="fetchAging" :icon="'Refresh'">刷新</el-button>
          </div>
        </div>

        <el-table
          v-loading="agingLoading"
          :data="agingData"
          border
          stripe
          max-height="calc(100vh - 320px)"
        >
          <el-table-column prop="aux_item_name" label="往来单位" min-width="180" show-overflow-tooltip />
          <el-table-column label="总金额" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.total_amount) }}
            </template>
          </el-table-column>
          <el-table-column label="30天内" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.within_30_days) }}
            </template>
          </el-table-column>
          <el-table-column label="31-90天" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.days_31_90) }}
            </template>
          </el-table-column>
          <el-table-column label="91-180天" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.days_91_180) }}
            </template>
          </el-table-column>
          <el-table-column label="180天以上" width="150" align="right">
            <template #default="{ row }">
              {{ formatAmount(row.over_180_days) }}
            </template>
          </el-table-column>
        </el-table>

        <div class="fc-pagination">
          <el-pagination
            v-model:current-page="agingPage"
            v-model:page-size="agingPageSize"
            :total="agingTotal"
            layout="total, sizes, prev, pager, next"
            @change="fetchAging"
          />
        </div>
      </div>
    </template>

    <!-- 应收/应付单 新建弹窗 -->
    <el-dialog
      v-model="docDialogVisible"
      :title="activeTab === 'receivable' ? (docForm.id ? '编辑应收单' : '新建应收单') : (docForm.id ? '编辑应付单' : '新建应付单')"
      width="560px"
      destroy-on-close
    >
      <el-form ref="docFormRef" :model="docForm" label-width="100px">
        <el-form-item label="单据号" prop="doc_no">
          <el-input v-model="docForm.doc_no" placeholder="请输入单据号" />
        </el-form-item>
        <el-form-item label="往来单位" prop="aux_item_id">
          <el-select
            v-model="docForm.aux_item_id"
            placeholder="请选择往来单位"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="item in auxItems"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="业务日期" prop="biz_date">
          <el-date-picker
            v-model="docForm.biz_date"
            type="date"
            placeholder="选择业务日期"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="到期日" prop="due_date">
          <el-date-picker
            v-model="docForm.due_date"
            type="date"
            placeholder="选择到期日"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="金额" prop="amount">
          <el-input-number
            v-model="docForm.amount"
            :min="0"
            :precision="2"
            :controls="false"
            style="width: 100%"
            placeholder="请输入金额"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="docDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="docSaving" @click="saveDoc">保存</el-button>
      </template>
    </el-dialog>

    <!-- 结算核销 新建弹窗 -->
    <el-dialog
      v-model="settlementDialogVisible"
      title="新建结算"
      width="560px"
      destroy-on-close
    >
      <el-form ref="settlementFormRef" :model="settlementForm" label-width="100px">
        <el-form-item label="结算类型" prop="settlement_type">
          <el-select v-model="settlementForm.settlement_type" placeholder="选择结算类型" style="width: 100%">
            <el-option label="收款" value="receipt" />
            <el-option label="付款" value="payment" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联单据" prop="related_doc_id">
          <el-select
            v-model="settlementForm.related_doc_id"
            placeholder="选择应收/应付单据"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="doc in relatedDocs"
              :key="doc.id"
              :label="`${doc.doc_no} (${doc.aux_item_name || ''})`"
              :value="doc.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="金额" prop="amount">
          <el-input-number
            v-model="settlementForm.amount"
            :min="0"
            :precision="2"
            :controls="false"
            style="width: 100%"
            placeholder="请输入结算金额"
          />
        </el-form-item>
        <el-form-item label="原因" prop="reason">
          <el-input
            v-model="settlementForm.reason"
            type="textarea"
            :rows="2"
            placeholder="请输入结算原因"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="settlementDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="settlementSaving" @click="saveSettlement">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { financeCenterApi } from "@/api/financeCenter"

const activeTab = ref('receivable')

// ============ 公共数据 ============
const books = ref<any[]>([])
const auxItems = ref<any[]>([])

// ============ 应收/应付单 ============
const docBookId = ref<number | null>(null)
const docStatus = ref<string | null>(null)
const docData = ref<any[]>([])
const docLoading = ref(false)
const docPage = ref(1)
const docPageSize = ref(20)
const docTotal = ref(0)
const docDialogVisible = ref(false)
const docSaving = ref(false)
const docFormRef = ref()
const docForm = ref<any>({
  id: null,
  doc_no: '',
  aux_item_id: null,
  biz_date: '',
  due_date: '',
  amount: 0,
})

// ============ 结算核销 ============
const settlementBookId = ref<number | null>(null)
const settlementData = ref<any[]>([])
const settlementLoading = ref(false)
const settlementPage = ref(1)
const settlementPageSize = ref(20)
const settlementTotal = ref(0)
const settlementDialogVisible = ref(false)
const settlementSaving = ref(false)
const settlementFormRef = ref()
const settlementForm = ref<any>({
  settlement_type: 'receipt',
  related_doc_id: null,
  amount: 0,
  reason: '',
})
const relatedDocs = ref<any[]>([])

// ============ 账龄分析 ============
const agingBookId = ref<number | null>(null)
const agingDate = ref<string>('')
const agingData = ref<any[]>([])
const agingLoading = ref(false)
const agingPage = ref(1)
const agingPageSize = ref(20)
const agingTotal = ref(0)

// ============ 工具函数 ============
function formatAmount(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function docStatusLabel(status: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    confirmed: '已确认',
    settled: '已结算',
    closed: '已关闭',
  }
  return map[status] || status
}

function docStatusTag(status: string): string {
  const map: Record<string, string> = {
    draft: 'info',
    confirmed: 'warning',
    settled: 'success',
    closed: '',
  }
  return map[status] || 'info'
}

// ============ 数据加载 ============
async function loadBooks() {
  try {
    const res = await financeCenterApi.listBooks()
    books.value = (res.data as any)?.data || []
  } catch {
    ElMessage.error('加载账套列表失败')
  }
}

async function loadAuxItems() {
  try {
    const res = await financeCenterApi.listAuxItems({})
    auxItems.value = (res.data as any)?.data || []
  } catch {
    // 非关键数据
  }
}

async function fetchDocs() {
  docLoading.value = true
  try {
    const api = activeTab.value === 'receivable'
      ? financeCenterApi.listReceivables
      : financeCenterApi.listPayables
    const res = await api({
      book_id: docBookId.value || undefined,
      status: docStatus.value || undefined,
      page: docPage.value,
      page_size: docPageSize.value,
    })
    const data = (res.data as any)?.data || {}
    docData.value = data.items || data.list || data || []
    docTotal.value = data.total || 0
  } catch {
    ElMessage.error('加载单据列表失败')
  } finally {
    docLoading.value = false
  }
}

async function fetchSettlements() {
  settlementLoading.value = true
  try {
    const res = await financeCenterApi.listSettlements({
      book_id: settlementBookId.value || undefined,
      page: settlementPage.value,
      page_size: settlementPageSize.value,
    })
    const data = (res.data as any)?.data || {}
    settlementData.value = data.items || data.list || data || []
    settlementTotal.value = data.total || 0
  } catch {
    ElMessage.error('加载结算列表失败')
  } finally {
    settlementLoading.value = false
  }
}

async function fetchAging() {
  if (!agingBookId.value) return
  agingLoading.value = true
  try {
    const res = await financeCenterApi.agingAnalysis({
      book_id: agingBookId.value,
      as_of_date: agingDate.value || undefined,
      page: agingPage.value,
      page_size: agingPageSize.value,
    })
    const data = (res.data as any)?.data || {}
    agingData.value = data.items || data.list || data || []
    agingTotal.value = data.total || 0
  } catch {
    ElMessage.error('加载账龄分析失败')
  } finally {
    agingLoading.value = false
  }
}

// ============ 应收/应付单操作 ============
function openDocDialog(row?: any) {
  if (row) {
    docForm.value = { ...row }
  } else {
    docForm.value = {
      id: null,
      doc_no: '',
      aux_item_id: null,
      biz_date: '',
      due_date: '',
      amount: 0,
    }
  }
  docDialogVisible.value = true
}

async function saveDoc() {
  docSaving.value = true
  try {
    const api = activeTab.value === 'receivable'
      ? financeCenterApi.createReceivable
      : financeCenterApi.createPayable
    await api({
      ...docForm.value,
      book_id: docBookId.value,
    })
    ElMessage.success('保存成功')
    docDialogVisible.value = false
    fetchDocs()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    docSaving.value = false
  }
}

function viewDocDetail(row: any) {
  openDocDialog(row)
}

// ============ 结算操作 ============
async function openSettlementDialog() {
  settlementForm.value = {
    settlement_type: 'receipt',
    related_doc_id: null,
    amount: 0,
    reason: '',
  }
  try {
    const res = await financeCenterApi.listReceivables({
      book_id: settlementBookId.value || undefined,
      page: 1,
      page_size: 200,
    })
    const data = (res.data as any)?.data || {}
    relatedDocs.value = data.items || data.list || data || []
  } catch {
    relatedDocs.value = []
  }
  settlementDialogVisible.value = true
}

async function saveSettlement() {
  settlementSaving.value = true
  try {
    await financeCenterApi.createSettlement({
      ...settlementForm.value,
      book_id: settlementBookId.value,
    })
    ElMessage.success('结算成功')
    settlementDialogVisible.value = false
    fetchSettlements()
  } catch {
    ElMessage.error('结算失败')
  } finally {
    settlementSaving.value = false
  }
}

// ============ Tab 切换 ============
function handleTabChange(tab: string) {
  if (tab === 'receivable' || tab === 'payable') {
    fetchDocs()
  } else if (tab === 'settlement') {
    fetchSettlements()
  } else if (tab === 'aging') {
    fetchAging()
  }
}

onMounted(() => {
  loadBooks()
  loadAuxItems()
})
</script>

<script lang="ts">
export default { name: 'FinanceReceivablePayable' }
</script>

<style scoped>
.fc-receivable-payable {
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
</style>