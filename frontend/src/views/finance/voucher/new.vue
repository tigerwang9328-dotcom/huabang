<template>
  <div class="voucher-entry-page">
    <div class="page-head">
      <div>
        <h3>录凭证</h3>
        <p>账套：{{ finStore.currentBook?.book_name || "-" }}　期间：{{ finStore.currentPeriod || "-" }}　凭证号：{{ nextNo || "保存时生成" }}</p>
      </div>
      <div class="head-actions">
        <el-button :icon="RefreshLeft" @click="reloadAll">刷新</el-button>
        <el-button @click="router.push('/finance/voucher/list')">返回列表</el-button>
      </div>
    </div>

    <el-form :model="form" label-width="76px" class="voucher-form">
      <el-row :gutter="12">
        <el-col :xs="24" :sm="12" :md="4">
          <el-form-item label="凭证字">
            <el-select v-model="form.voucher_type" style="width:100%">
              <el-option label="记" value="记" />
              <el-option label="收" value="收" />
              <el-option label="付" value="付" />
              <el-option label="转" value="转" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :md="5">
          <el-form-item label="凭证日期">
            <el-date-picker v-model="form.voucher_date" type="date" value-format="YYYY-MM-DD" style="width:100%" @change="syncEmptyBizDate" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :md="5">
          <el-form-item label="来源">
            <el-select v-model="form.source_type" style="width:100%">
              <el-option label="手工录入" value="manual" />
              <el-option label="销售业务" value="sales" />
              <el-option label="退款业务" value="refund" />
              <el-option label="费用报销" value="expense" />
              <el-option label="资金收付" value="cash" />
              <el-option label="调整分录" value="adjust" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :md="5">
          <el-form-item label="来源单号">
            <el-input v-model="form.source_ref" placeholder="业务单/批次号" clearable />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :md="5">
          <el-form-item label="模板">
            <el-select v-model="selectedTemplateId" filterable clearable placeholder="选择后套用" style="width:100%" @change="applyTemplate">
              <el-option v-for="tpl in templates" :key="tpl.id" :label="tpl.template_name || tpl.name" :value="tpl.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="总摘要">
        <el-input v-model="form.summary" maxlength="200" show-word-limit placeholder="例如：确认店铺销售收入、支付推广费、计提退款成本" />
      </el-form-item>
    </el-form>

    <div class="toolbar">
      <el-button type="primary" plain :icon="Plus" @click="addBlankLine">添加分录</el-button>
      <el-button :icon="CopyDocument" @click="copyLastLine">复制上一行</el-button>
      <el-button @click="addReceiptPair">收款分录</el-button>
      <el-button @click="addPaymentPair">付款分录</el-button>
      <el-button @click="balanceLastLine">自动找平</el-button>
      <div class="totals">
        <span>借方 <b>{{ money(totalDebit) }}</b></span>
        <span>贷方 <b>{{ money(totalCredit) }}</b></span>
        <span>差额 <b :class="{ danger: !balanced }">{{ money(balanceDiff) }}</b></span>
        <el-tag size="small" :type="balanced ? 'success' : 'danger'">{{ balanced ? '已平衡' : '未平衡' }}</el-tag>
      </div>
    </div>

    <el-table :data="form.lines" border size="small" class="entry-table" :max-height="520" row-key="key">
      <el-table-column type="index" label="#" width="42" fixed />
      <el-table-column label="业务日期" width="118" fixed>
        <template #default="{ row }"><el-date-picker v-model="row.biz_date" type="date" value-format="YYYY-MM-DD" size="small" style="width:102px" /></template>
      </el-table-column>
      <el-table-column label="摘要" width="150" fixed>
        <template #default="{ row }"><el-input v-model="row.summary" size="small" placeholder="行摘要" /></template>
      </el-table-column>
      <el-table-column label="会计科目" width="220" fixed>
        <template #default="{ row }">
          <el-select v-model="row.account_id" filterable clearable size="small" placeholder="编码/名称" style="width:100%" @change="onAccountChange(row)">
            <el-option v-for="a in accounts" :key="a.id" :label="`${a.account_code} ${a.account_name}`" :value="a.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="店铺" width="132">
        <template #default="{ row }">
          <el-select v-model="row.store_id" filterable clearable size="small" placeholder="店铺" style="width:100%">
            <el-option v-for="s in stores" :key="s.id" :label="storeLabel(s)" :value="s.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="客户" width="128"><template #default="{ row }"><aux-select v-model="row.customer_id" :items="auxItems.customer" placeholder="客户" /></template></el-table-column>
      <el-table-column label="供应商" width="128"><template #default="{ row }"><aux-select v-model="row.supplier_id" :items="auxItems.supplier" placeholder="供应商" /></template></el-table-column>
      <el-table-column label="部门" width="116"><template #default="{ row }"><aux-select v-model="row.department_id" :items="auxItems.department" placeholder="部门" /></template></el-table-column>
      <el-table-column label="员工" width="116"><template #default="{ row }"><aux-select v-model="row.employee_id" :items="auxItems.employee" placeholder="员工" /></template></el-table-column>
      <el-table-column label="项目" width="118"><template #default="{ row }"><el-input v-model="row.project_code" size="small" placeholder="项目编码" /></template></el-table-column>
      <el-table-column label="业务单号" width="136"><template #default="{ row }"><el-input v-model="row.order_no" size="small" placeholder="订单/退款/费用单" /></template></el-table-column>
      <el-table-column label="借方金额" width="126" align="right" fixed="right">
        <template #default="{ row }"><el-input-number v-model="row.debit_amount" :min="0" :precision="2" :controls="false" size="small" style="width:106px" @focus="row.credit_amount = 0" /></template>
      </el-table-column>
      <el-table-column label="贷方金额" width="126" align="right" fixed="right">
        <template #default="{ row }"><el-input-number v-model="row.credit_amount" :min="0" :precision="2" :controls="false" size="small" style="width:106px" @focus="row.debit_amount = 0" /></template>
      </el-table-column>
      <el-table-column label="操作" width="76" fixed="right" align="center">
        <template #default="{ row, $index }">
          <el-button link :icon="CopyDocument" @click="duplicateLine(row)" />
          <el-button link type="danger" :icon="Delete" :disabled="form.lines.length <= 2" @click="removeLine($index)" />
        </template>
      </el-table-column>
    </el-table>

    <div class="footer-bar">
      <el-radio-group v-model="form.status">
        <el-radio-button label="draft">保存草稿</el-radio-button>
        <el-radio-button label="reviewed">保存并审核</el-radio-button>
      </el-radio-group>
      <div class="footer-actions">
        <el-button @click="router.push('/finance/voucher/list')">取消</el-button>
        <el-button type="primary" :icon="DocumentChecked" :loading="saving" @click="save">保存凭证</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from "vue"
import { CopyDocument, Delete, DocumentChecked, Plus, RefreshLeft } from "@element-plus/icons-vue"
import { ElMessage, ElOption, ElSelect } from "element-plus"
import { useRouter } from "vue-router"
import dayjs from "dayjs"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"

const router = useRouter()
const finStore = useFinanceStore()
const saving = ref(false)
const accounts = ref<any[]>([])
const stores = ref<any[]>([])
const templates = ref<any[]>([])
const selectedTemplateId = ref<number | null>(null)
const nextNo = ref("")
let lineSeed = 1

const auxItems = reactive<Record<string, any[]>>({ customer: [], supplier: [], department: [], employee: [] })

const AuxSelect = defineComponent({
  name: "AuxSelect",
  props: { modelValue: { type: Number, default: null }, items: { type: Array, default: () => [] }, placeholder: { type: String, default: "选择" } },
  emits: ["update:modelValue"],
  setup(props, { emit }) {
    return () => h(ElSelect, { modelValue: props.modelValue, filterable: true, clearable: true, size: "small", placeholder: props.placeholder, style: "width:100%", "onUpdate:modelValue": (v: number | null) => emit("update:modelValue", v) }, () => (props.items as any[]).map((item) => h(ElOption, { key: item.id, label: auxLabel(item), value: item.id })))
  },
})

function newLine(seed: Record<string, any> = {}) {
  return { key: `line-${lineSeed++}`, biz_date: seed.biz_date || dayjs().format("YYYY-MM-DD"), summary: seed.summary || "", account_id: seed.account_id ?? null, account_code: seed.account_code || "", store_id: seed.store_id ?? null, customer_id: seed.customer_id ?? null, supplier_id: seed.supplier_id ?? null, department_id: seed.department_id ?? null, employee_id: seed.employee_id ?? null, project_code: seed.project_code || "", order_no: seed.order_no || "", debit_amount: Number(seed.debit_amount || 0), credit_amount: Number(seed.credit_amount || 0) }
}

const form = reactive({ voucher_type: "记", voucher_date: dayjs().format("YYYY-MM-DD"), source_type: "manual", source_ref: "", summary: "", status: "draft", lines: [newLine(), newLine()] })
const validLines = computed(() => form.lines.filter((l) => l.account_id && (Number(l.debit_amount) > 0 || Number(l.credit_amount) > 0)))
const totalDebit = computed(() => validLines.value.reduce((sum, l) => sum + Number(l.debit_amount || 0), 0))
const totalCredit = computed(() => validLines.value.reduce((sum, l) => sum + Number(l.credit_amount || 0), 0))
const balanceDiff = computed(() => totalDebit.value - totalCredit.value)
const balanced = computed(() => Math.abs(balanceDiff.value) < 0.005 && totalDebit.value > 0)

function money(value: number) { return `¥${Number(value || 0).toFixed(2)}` }
function auxLabel(item: any) { return `${item.item_code ? item.item_code + " " : ""}${item.item_name}` }
function storeLabel(store: any) { return `${store.platform_name ? store.platform_name + " / " : ""}${store.store_name}` }
function addBlankLine() { form.lines.push(newLine({ biz_date: form.voucher_date, summary: form.summary })) }
function duplicateLine(row: any) { const { key, ...rest } = row; form.lines.push(newLine({ ...rest, debit_amount: 0, credit_amount: 0 })) }
function copyLastLine() { duplicateLine(form.lines[form.lines.length - 1]) }
function removeLine(index: number) { if (form.lines.length > 2) form.lines.splice(index, 1) }
function addReceiptPair() { form.voucher_type = "收"; form.lines.push(newLine({ biz_date: form.voucher_date, summary: form.summary || "收到款项" }), newLine({ biz_date: form.voucher_date, summary: form.summary || "确认收款对应科目" })) }
function addPaymentPair() { form.voucher_type = "付"; form.lines.push(newLine({ biz_date: form.voucher_date, summary: form.summary || "支付款项" }), newLine({ biz_date: form.voucher_date, summary: form.summary || "确认付款资金科目" })) }

function balanceLastLine() {
  const target = [...form.lines].reverse().find((line) => line.account_id)
  if (!target) { ElMessage.warning("请先选择需要找平的科目"); return }
  const others = form.lines.filter((line) => line !== target)
  const diff = others.reduce((s, l) => s + Number(l.debit_amount || 0), 0) - others.reduce((s, l) => s + Number(l.credit_amount || 0), 0)
  target.debit_amount = diff < 0 ? Math.abs(diff) : 0
  target.credit_amount = diff > 0 ? diff : 0
}

function syncEmptyBizDate() { form.lines.forEach((line) => { if (!line.biz_date) line.biz_date = form.voucher_date }) }
function onAccountChange(row: any) { const account = accounts.value.find((a) => a.id === row.account_id); row.account_code = account?.account_code || "" }
function remapLineAccounts() {
  form.lines.forEach((line) => {
    if (!line.account_code) return
    const account = accounts.value.find((a) => a.account_code === line.account_code)
    line.account_id = account?.id ?? null
  })
}
async function loadAccounts() { const data: any = await request.get(`/finance/accounts?book_id=${finStore.bookId}`); accounts.value = data.accounts || [] }
async function loadStores() { const data: any = await request.get("/stores?include_inactive=false"); stores.value = data.stores || data.rows || data || [] }
async function loadTemplates() { const data: any = await request.get(`/finance/voucher-templates?book_id=${finStore.bookId}`); templates.value = data.templates || data.rows || [] }
async function loadNextNo() { const data: any = await request.get(`/finance/vouchers/next-no?book_id=${finStore.bookId}`); nextNo.value = data.next_no || "" }
function auxName(key: string) { return ({ customer: "客户", supplier: "供应商", department: "部门", employee: "员工" } as Record<string, string>)[key] }

async function loadAuxItems() {
  const data: any = await request.get(`/finance/aux/categories?book_id=${finStore.bookId}`)
  const categories = data.categories || []
  await Promise.all(Object.keys(auxItems).map(async (key) => {
    const category = categories.find((c: any) => c.category_code === key || c.category_name?.includes(auxName(key)))
    if (!category) return
    const itemsData: any = await request.get(`/finance/aux/items?category_id=${category.id}`)
    auxItems[key] = itemsData.items || []
  }))
}

async function reloadAll() {
  try { await finStore.loadBooks(); await Promise.all([loadAccounts(), loadStores(), loadTemplates(), loadAuxItems(), loadNextNo()]) }
  catch (error: any) { ElMessage.error(error?.response?.data?.detail || "基础资料加载失败") }
}

watch(() => finStore.bookId, async () => {
  await reloadAll()
  remapLineAccounts()
})

function findAccount(line: any) {
  return accounts.value.find((a) => a.account_code === line.account_code) || accounts.value.find((a) => line.account_name && a.account_name?.includes(line.account_name)) || accounts.value.find((a) => line.account_code && a.account_code?.startsWith(line.account_code))
}

function applyTemplate(templateId: number | null) {
  const template = templates.value.find((tpl) => tpl.id === templateId)
  if (!template) return
  form.voucher_type = template.voucher_type || form.voucher_type
  form.summary = template.summary || template.description || template.template_name || template.name || form.summary
  const templateLines = template.lines || []
  if (templateLines.length) {
    form.lines.splice(0, form.lines.length, ...templateLines.map((line: any) => {
      const account = findAccount(line)
      return newLine({
        biz_date: form.voucher_date,
        summary: line.summary || form.summary,
        account_id: account?.id ?? null,
        account_code: account?.account_code || line.account_code || "",
        store_id: line.store_id ?? null,
        customer_id: line.customer_id ?? null,
        supplier_id: line.supplier_id ?? null,
        department_id: line.department_id ?? null,
        employee_id: line.employee_id ?? null,
        project_code: line.project_code || "",
        order_no: line.order_no || "",
        debit_amount: line.direction === "debit" ? Number(line.amount || 0) : Number(line.debit_amount || 0),
        credit_amount: line.direction === "credit" ? Number(line.amount || 0) : Number(line.credit_amount || 0),
      })
    }))
  }
}

function validate() {
  if (!form.voucher_date) return "请选择凭证日期"
  if (!form.voucher_type) return "请选择凭证字"
  if (validLines.value.length < 2) return "至少需要2条有效分录"
  if (!balanced.value) return "借贷不平衡，无法保存"
  if (validLines.value.find((line) => Number(line.debit_amount) > 0 && Number(line.credit_amount) > 0)) return "同一分录行不能同时填写借方和贷方金额"
  if (validLines.value.find((line) => !line.summary && !form.summary)) return "请填写总摘要或每行摘要"
  return ""
}

function buildPayload() {
  return { voucher_type: form.voucher_type, voucher_date: form.voucher_date, source_type: form.source_type, source_ref: form.source_ref || null, summary: form.summary || null, status: form.status, lines: validLines.value.map((line) => ({ account_id: line.account_id, account_code: line.account_code || undefined, debit_amount: Number(line.debit_amount || 0), credit_amount: Number(line.credit_amount || 0), summary: line.summary || form.summary, biz_date: line.biz_date || form.voucher_date, customer_id: line.customer_id || null, supplier_id: line.supplier_id || null, employee_id: line.employee_id || null, department_id: line.department_id || null, project_code: line.project_code || null, store_id: line.store_id || null, order_no: line.order_no || null })) }
}

async function save() {
  const message = validate()
  if (message) { ElMessage.error(message); return }
  saving.value = true
  try { await request.post(`/finance/vouchers?book_id=${finStore.bookId}`, buildPayload()); ElMessage.success("凭证已保存"); router.push("/finance/voucher/list") }
  catch (error: any) { ElMessage.error(error?.response?.data?.detail || "保存失败") }
  finally { saving.value = false }
}

onMounted(async () => {
  await reloadAll()
  if (finStore.currentPeriod) { form.voucher_date = `${finStore.currentPeriod}-01`; syncEmptyBizDate() }
})
</script>

<style scoped>
.voucher-entry-page { padding: 18px 20px 24px; }
.page-head, .toolbar, .footer-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.page-head { margin-bottom: 14px; }
.page-head h3 { margin: 0 0 6px; font-size: 20px; font-weight: 650; color: #1f2937; }
.page-head p { margin: 0; font-size: 13px; color: #6b7280; }
.head-actions, .footer-actions { display: flex; gap: 8px; }
.voucher-form { padding: 14px 14px 2px; margin-bottom: 12px; background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; }
.toolbar { margin: 10px 0; flex-wrap: wrap; }
.totals { display: flex; align-items: center; gap: 14px; margin-left: auto; font-size: 13px; color: #4b5563; }
.totals b { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #111827; }
.totals .danger { color: #dc2626; }
.entry-table { width: 100%; background: #fff; }
.footer-bar { margin-top: 14px; padding-top: 12px; border-top: 1px solid #e5e7eb; }
:deep(.entry-table .el-input-number .el-input__inner) { text-align: right; }
@media (max-width: 900px) {
  .voucher-entry-page { padding: 12px; }
  .page-head, .footer-bar { align-items: flex-start; flex-direction: column; }
  .totals { width: 100%; margin-left: 0; flex-wrap: wrap; }
}
</style>
