<template>
  <div class="tax-page">
    <!-- 顶部 KPI -->
    <div class="tax-kpi-row">
      <div class="tax-kpi" v-for="k in kpis" :key="k.key" :class="k.cls">
        <div class="kpi-icon">{{ k.icon }}</div>
        <div class="kpi-body">
          <div class="kpi-label">{{ k.label }}</div>
          <div class="kpi-value">{{ k.value }}</div>
        </div>
      </div>
    </div>

    <!-- 风险预警 -->
    <el-alert v-for="a in taxAlerts" :key="a.id" :title="a.message"
      :type="a.level === 'danger' ? 'error' : 'warning'"
      show-icon style="margin-bottom:8px" :closable="false">
      <template #default>
        {{ a.tax_name }} · {{ a.period }} · 应缴 ¥{{ fmtNum(a.tax_amount) }} · 未缴 ¥{{ fmtNum(a.outstanding) }}
        <span v-if="a.due_date">· 截止 {{ a.due_date }}</span>
      </template>
    </el-alert>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" class="tax-tabs">
      <!-- Tab1: 税务台账 -->
      <el-tab-pane label="税务台账" name="records">
        <div class="toolbar">
          <div class="toolbar-left">
            <el-date-picker v-model="filterYear" type="year" value-format="YYYY"
              placeholder="年份" style="width:110px" @change="loadRecords" />
            <el-select v-model="filterStatus" style="width:110px" @change="loadRecords" clearable placeholder="状态">
              <el-option label="待缴" value="pending" />
              <el-option label="部分" value="partial" />
              <el-option label="已缴" value="paid" />
            </el-select>
          </div>
          <div class="toolbar-right">
            <el-button type="primary" @click="openAddRecord">+ 录入税款</el-button>
          </div>
        </div>

        <el-table :data="records" stripe border size="small" v-loading="loadingRecords">
          <el-table-column prop="period" label="期间" width="90" />
          <el-table-column prop="tax_name" label="税种" min-width="140" />
          <el-table-column prop="tax_base" label="计税依据" width="120" align="right"
            :formatter="(_r,_c,v)=>'¥'+fmtNum(v)" />
          <el-table-column prop="tax_amount" label="应纳税额" width="120" align="right"
            :formatter="(_r,_c,v)=>'¥'+fmtNum(v)" />
          <el-table-column prop="paid_amount" label="已缴" width="100" align="right"
            :formatter="(_r,_c,v)=>'¥'+fmtNum(v)" />
          <el-table-column prop="outstanding" label="未缴" width="100" align="right">
            <template #default="{row}">
              <span :class="row.outstanding > 0 ? 'text-danger' : 'text-ok'">
                ¥{{ fmtNum(row.outstanding) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="due_date" label="申报截止" width="110" />
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{row}">
              <el-tag size="small"
                :type="row.status==='paid'?'success':row.status==='partial'?'warning':'danger'">
                {{ { pending:'待缴', partial:'部分缴', paid:'已缴' }[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template #default="{row}">
              <el-button size="small" link type="primary"
                @click="openPay(row)" v-if="row.status !== 'paid'">缴税</el-button>
              <el-button size="small" link @click="openEditRecord(row)">编辑</el-button>
              <el-button size="small" link type="danger"
                @click="deleteRecord(row)" v-if="row.status === 'pending'">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab2: 年度汇总 -->
      <el-tab-pane label="年度汇总" name="summary">
        <div class="toolbar">
          <el-date-picker v-model="filterYear" type="year" value-format="YYYY"
            placeholder="年份" style="width:110px" @change="loadSummary" />
          <el-button type="primary" plain @click="loadSummary" style="margin-left:8px">刷新</el-button>
        </div>
        <el-table :data="summaryRows" stripe border size="small" v-loading="loadingSummary"
          show-summary :summary-method="getSummary">
          <el-table-column prop="tax_name" label="税种" min-width="160" />
          <el-table-column prop="tax_category" label="类别" width="100">
            <template #default="{row}">
              <el-tag size="small" :type="catColor(row.tax_category)">{{ catLabel(row.tax_category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="period_count" label="期数" width="70" align="center" />
          <el-table-column prop="total_amount" label="应缴合计" width="130" align="right"
            :formatter="(_r,_c,v)=>'¥'+fmtNum(v)" />
          <el-table-column prop="total_paid" label="已缴合计" width="130" align="right"
            :formatter="(_r,_c,v)=>'¥'+fmtNum(v)" />
          <el-table-column prop="outstanding" label="未缴余额" width="130" align="right">
            <template #default="{row}">
              <span :class="row.outstanding > 0 ? 'text-danger' : 'text-ok'">
                ¥{{ fmtNum(row.outstanding) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab3: 税种配置 -->
      <el-tab-pane label="税种配置" name="types">
        <div class="toolbar">
          <el-button type="primary" @click="openAddType">+ 新增税种</el-button>
        </div>
        <el-table :data="taxTypes" stripe border size="small" v-loading="loadingTypes">
          <el-table-column prop="tax_code" label="税码" width="90" />
          <el-table-column prop="tax_name" label="税种名称" min-width="160" />
          <el-table-column prop="tax_category" label="类别" width="100">
            <template #default="{row}">
              <el-tag size="small" :type="catColor(row.tax_category)">{{ catLabel(row.tax_category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="tax_rate_pct" label="税率" width="90" align="center" />
          <el-table-column prop="period_type" label="申报周期" width="90" align="center">
            <template #default="{row}">{{ { month:'月报', quarter:'季报', year:'年报' }[row.period_type] }}</template>
          </el-table-column>
          <el-table-column prop="is_active" label="启用" width="70" align="center">
            <template #default="{row}">
              <el-tag size="small" :type="row.is_active?'success':'info'">{{ row.is_active?'启用':'停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{row}">
              <el-button size="small" link @click="openEditType(row)">编辑</el-button>
              <el-button size="small" link :type="row.is_active?'danger':'success'"
                @click="toggleType(row)">{{ row.is_active?'停用':'启用' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 录入税款 dialog -->
    <el-dialog v-model="showRecordDlg" :title="editRecord?.id ? '编辑税款' : '录入税款'" width="480px" destroy-on-close>
      <el-form :model="recordForm" label-width="90px" :rules="recordRules" ref="recordFormRef">
        <el-form-item label="税种" prop="tax_type_id">
          <el-select v-model="recordForm.tax_type_id" style="width:100%" placeholder="请选择" @change="autoCalcTax">
            <el-option v-for="t in taxTypes.filter(t=>t.is_active)" :key="t.id" :label="t.tax_name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="期间" prop="period">
          <el-date-picker v-model="recordForm.period" type="month" value-format="YYYY-MM"
            style="width:100%" placeholder="YYYY-MM" />
        </el-form-item>
        <el-form-item label="计税依据">
          <el-input-number v-model="recordForm.tax_base" :min="0" :precision="2" style="width:100%" @change="autoCalcTax" />
        </el-form-item>
        <el-form-item label="应纳税额" prop="tax_amount">
          <el-input-number v-model="recordForm.tax_amount" :min="0" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="申报截止">
          <el-date-picker v-model="recordForm.due_date" type="date" value-format="YYYY-MM-DD"
            style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="recordForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRecordDlg=false">取消</el-button>
        <el-button type="primary" @click="saveRecord" :loading="savingRecord">保存</el-button>
      </template>
    </el-dialog>

    <!-- 缴税 dialog -->
    <el-dialog v-model="showPayDlg" title="缴税确认" width="380px" destroy-on-close>
      <el-form :model="payForm" label-width="80px">
        <el-form-item label="税种">
          <el-input :value="payTarget?.tax_name" disabled />
        </el-form-item>
        <el-form-item label="应缴">
          <el-input :value="'¥' + fmtNum(payTarget?.tax_amount)" disabled />
        </el-form-item>
        <el-form-item label="缴纳金额">
          <el-input-number v-model="payForm.paid_amount" :min="0" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="缴税日期">
          <el-date-picker v-model="payForm.paid_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPayDlg=false">取消</el-button>
        <el-button type="primary" @click="savePay" :loading="savingPay">确认缴税</el-button>
      </template>
    </el-dialog>

    <!-- 税种 dialog -->
    <el-dialog v-model="showTypeDlg" :title="editType?.id ? '编辑税种' : '新增税种'" width="420px" destroy-on-close>
      <el-form :model="typeForm" label-width="90px">
        <el-form-item label="税码">
          <el-input v-model="typeForm.tax_code" :disabled="!!editType?.id" placeholder="如 VAT" />
        </el-form-item>
        <el-form-item label="税种名称">
          <el-input v-model="typeForm.tax_name" />
        </el-form-item>
        <el-form-item label="税率(%)">
          <el-input-number v-model="typeForm.tax_rate_pct" :min="0" :max="100" :precision="4" style="width:100%" />
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="typeForm.tax_category" style="width:100%">
            <el-option label="增值税" value="vat" />
            <el-option label="企业所得税" value="income" />
            <el-option label="个人所得税" value="individual" />
            <el-option label="城建税" value="urban" />
            <el-option label="印花税" value="stamp" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="申报周期">
          <el-select v-model="typeForm.period_type" style="width:100%">
            <el-option label="月报" value="month" />
            <el-option label="季报" value="quarter" />
            <el-option label="年报" value="year" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTypeDlg=false">取消</el-button>
        <el-button type="primary" @click="saveType" :loading="savingType">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import dayjs from "dayjs"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"

const store = useFinanceStore()
const bookId = computed(() => store.bookId)

const activeTab = ref("records")
const filterYear = ref(dayjs().format("YYYY"))
const filterStatus = ref("")

// ── Data ──
const records = ref<any[]>([])
const summaryRows = ref<any[]>([])
const taxTypes = ref<any[]>([])
const taxAlerts = ref<any[]>([])
const loadingRecords = ref(false)
const loadingSummary = ref(false)
const loadingTypes = ref(false)

// ── KPI ──
const kpis = computed(() => {
  const total = summaryRows.value.reduce((s: number, r: any) => s + (r.total_amount || 0), 0)
  const paid = summaryRows.value.reduce((s: number, r: any) => s + (r.total_paid || 0), 0)
  const outstanding = total - paid
  return [
    { key: "total", icon: "🧾", label: `${filterYear.value}年应缴合计`, value: `¥${fmtNum(total)}`, cls: "kpi-blue" },
    { key: "paid", icon: "✅", label: "已缴合计", value: `¥${fmtNum(paid)}`, cls: "kpi-green" },
    { key: "outstanding", icon: "⚠️", label: "未缴余额", value: `¥${fmtNum(outstanding)}`, cls: outstanding > 0 ? "kpi-red" : "kpi-green" },
    { key: "alert", icon: "🔔", label: "待处理预警", value: `${taxAlerts.value.length} 条`, cls: taxAlerts.value.length > 0 ? "kpi-red" : "kpi-gray" },
  ]
})

// ── Dialog State ──
const showRecordDlg = ref(false)
const showPayDlg = ref(false)
const showTypeDlg = ref(false)
const editRecord = ref<any>(null)
const editType = ref<any>(null)
const payTarget = ref<any>(null)
const savingRecord = ref(false)
const savingPay = ref(false)
const savingType = ref(false)
const recordFormRef = ref()

const recordForm = ref<any>({
  tax_type_id: null, period: dayjs().format("YYYY-MM"),
  tax_base: 0, tax_amount: 0, due_date: "", remark: "",
})
const recordRules = {
  tax_type_id: [{ required: true, message: "请选择税种" }],
  period: [{ required: true, message: "请选择期间" }],
  tax_amount: [{ required: true, message: "请输入应纳税额" }],
}
const payForm = ref<any>({ paid_amount: 0, paid_date: dayjs().format("YYYY-MM-DD") })
const typeForm = ref<any>({
  tax_code: "", tax_name: "", tax_rate_pct: 0,
  tax_category: "vat", period_type: "month",
})

// ── Helpers ──
const fmtNum = (v: number) => v != null ? Number(v).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "0.00"

const catLabel = (c: string) => ({ vat: "增值税", income: "所得税", individual: "个税", urban: "城建税", stamp: "印花税", other: "其他" }[c] || c)
const catColor = (c: string) => ({ vat: "", income: "danger", individual: "warning", urban: "info", stamp: "success", other: "" }[c] || "")

function autoCalcTax() {
  const t = taxTypes.value.find((t: any) => t.id === recordForm.value.tax_type_id)
  const base = Number(recordForm.value.tax_base || 0)
  const rate = Number(t?.tax_rate || 0)
  if (!t || base <= 0) return
  recordForm.value.tax_amount = Math.round(base * rate * 100) / 100
}

function getSummary({ columns, data }: any) {
  const total = (field: string) => data.reduce((s: number, r: any) => s + (r[field] || 0), 0)
  return columns.map((_: any, i: number) => {
    if (i === 0) return "合计"
    if (i === 3) return `¥${fmtNum(total("total_amount"))}`
    if (i === 4) return `¥${fmtNum(total("total_paid"))}`
    if (i === 5) return `¥${fmtNum(total("outstanding"))}`
    return ""
  })
}

// ── Load ──
async function loadRecords() {
  loadingRecords.value = true
  try {
    const d: any = await request.get("/finance/tax/records", {
      params: { book_id: bookId.value, year: filterYear.value, status: filterStatus.value || undefined, page_size: 100 }
    })
    records.value = d.rows || []
  } finally { loadingRecords.value = false }
}

async function loadSummary() {
  loadingSummary.value = true
  try {
    const d: any = await request.get("/finance/tax/summary", {
      params: { book_id: bookId.value, year: filterYear.value }
    })
    summaryRows.value = d.rows || []
  } finally { loadingSummary.value = false }
}

async function loadTypes() {
  loadingTypes.value = true
  try {
    const d: any = await request.get("/finance/tax/types", { params: { book_id: bookId.value } })
    taxTypes.value = d.rows || []
  } finally { loadingTypes.value = false }
}

async function loadAlerts() {
  try {
    const d: any = await request.get("/finance/tax/alerts", { params: { book_id: bookId.value } })
    taxAlerts.value = d.alerts || []
  } catch {}
}

// ── Record CRUD ──
function openAddRecord() {
  editRecord.value = null
  recordForm.value = { tax_type_id: null, period: dayjs().format("YYYY-MM"), tax_base: 0, tax_amount: 0, due_date: "", remark: "" }
  showRecordDlg.value = true
}
function openEditRecord(row: any) {
  editRecord.value = row
  recordForm.value = { tax_type_id: row.tax_type_id, period: row.period, tax_base: row.tax_base, tax_amount: row.tax_amount, due_date: row.due_date, remark: row.remark }
  showRecordDlg.value = true
}
async function saveRecord() {
  await recordFormRef.value?.validate()
  savingRecord.value = true
  try {
    await request.post(`/finance/tax/records?book_id=${bookId.value}`, recordForm.value)
    ElMessage.success("已保存")
    showRecordDlg.value = false
    loadRecords(); loadSummary()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败") }
  finally { savingRecord.value = false }
}
async function deleteRecord(row: any) {
  await ElMessageBox.confirm(`确认删除 ${row.tax_name} ${row.period} 的税款记录？`)
  await request.delete(`/finance/tax/records/${row.id}?book_id=${bookId.value}`)
  ElMessage.success("已删除"); loadRecords(); loadSummary()
}

// ── Pay ──
function openPay(row: any) {
  payTarget.value = row
  payForm.value = { paid_amount: row.outstanding, paid_date: dayjs().format("YYYY-MM-DD") }
  showPayDlg.value = true
}
async function savePay() {
  savingPay.value = true
  try {
    await request.put(`/finance/tax/records/${payTarget.value.id}/paid?book_id=${bookId.value}`, payForm.value)
    ElMessage.success("缴税记录已更新")
    showPayDlg.value = false
    loadRecords(); loadSummary(); loadAlerts()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "操作失败") }
  finally { savingPay.value = false }
}

// ── Type CRUD ──
function openAddType() {
  editType.value = null
  typeForm.value = { tax_code: "", tax_name: "", tax_rate_pct: 0, tax_category: "vat", period_type: "month" }
  showTypeDlg.value = true
}
function openEditType(row: any) {
  editType.value = row
  typeForm.value = { tax_code: row.tax_code, tax_name: row.tax_name, tax_rate_pct: row.tax_rate * 100, tax_category: row.tax_category, period_type: row.period_type }
  showTypeDlg.value = true
}
async function toggleType(row: any) {
  await request.put(`/finance/tax/types/${row.id}?book_id=${bookId.value}`, { is_active: !row.is_active })
  ElMessage.success("已更新"); loadTypes()
}
async function saveType() {
  savingType.value = true
  try {
    const payload = { ...typeForm.value, tax_rate: typeForm.value.tax_rate_pct / 100 }
    if (editType.value?.id) {
      await request.put(`/finance/tax/types/${editType.value.id}?book_id=${bookId.value}`, payload)
    } else {
      await request.post(`/finance/tax/types?book_id=${bookId.value}`, payload)
    }
    ElMessage.success("已保存"); showTypeDlg.value = false; loadTypes()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败") }
  finally { savingType.value = false }
}

onMounted(async () => {
  if (!store.loaded) await store.loadBooks()
  await Promise.all([loadTypes(), loadAlerts()])
  await Promise.all([loadRecords(), loadSummary()])
})
</script>

<style scoped>
.tax-page { display: flex; flex-direction: column; gap: 16px; }

.tax-kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.tax-kpi {
  background: #fff; border-radius: 12px; padding: 14px 16px;
  display: flex; align-items: center; gap: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05); border: 1px solid #f0f0f0;
}
.kpi-icon { font-size: 22px; width: 40px; height: 40px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center; }
.kpi-blue .kpi-icon  { background: #eef3ff; }
.kpi-green .kpi-icon { background: #e8f8ee; }
.kpi-red .kpi-icon   { background: #fef0f0; }
.kpi-gray .kpi-icon  { background: #f5f5f5; }
.kpi-label { font-size: 11px; color: #999; margin-bottom: 2px; }
.kpi-value { font-size: 17px; font-weight: 700; color: #1a1a1a; }

.tax-tabs { background: #fff; border-radius: 12px; padding: 16px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.toolbar-left { display: flex; gap: 8px; }

.text-danger { color: #f56c6c; font-weight: 600; }
.text-ok     { color: #67c23a; }

@media (max-width: 1100px) {
  .tax-kpi-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
