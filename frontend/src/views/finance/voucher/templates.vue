<template>
  <div>
    <div class="template-head">
      <h3>凭证模板</h3>
      <el-button type="primary" @click="openCreate">新建模板</el-button>
    </div>

    <el-table :data="rows" stripe border size="small" v-loading="loading">
      <el-table-column prop="name" label="模板名称" min-width="160" />
      <el-table-column prop="voucher_type" label="凭证字" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="typeColor(row.voucher_type)">{{ row.voucher_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="220" show-overflow-tooltip />
      <el-table-column label="分录行数" width="90">
        <template #default="{ row }">{{ (row.lines || []).length }}</template>
      </el-table-column>
      <el-table-column prop="created_by" label="创建人" width="90" />
      <el-table-column prop="created_at" label="创建时间" width="160" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length === 0" description="暂无模板，常用分录可保存为模板复用" />

    <el-dialog v-model="showDialog" :title="editId ? '编辑模板' : '新建凭证模板'" width="1180px" top="6vh">
      <el-form :model="form" label-width="80px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="模板名称">
              <el-input v-model="form.name" placeholder="如 销售收款" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="凭证字">
              <el-select v-model="form.voucher_type" style="width:100%">
                <el-option value="记" label="记账凭证" />
                <el-option value="收" label="收款凭证" />
                <el-option value="付" label="付款凭证" />
                <el-option value="转" label="转账凭证" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="行数">
              <el-input :model-value="form.lines.length" disabled />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="摘要">
          <el-input v-model="form.summary" placeholder="默认摘要（可在使用时修改）" />
        </el-form-item>
      </el-form>

      <div class="lines-box">
        <div class="lines-toolbar">
          <span>分录明细</span>
          <div>
            <el-button size="small" @click="copyLastLine">复制上一行</el-button>
            <el-button size="small" type="primary" plain @click="addLine">添加行</el-button>
          </div>
        </div>
        <el-table :data="form.lines" border size="small" max-height="420" row-key="key">
          <el-table-column type="index" label="#" width="42" fixed />
          <el-table-column label="摘要" width="150" fixed>
            <template #default="{ row }"><el-input v-model="row.summary" size="small" placeholder="行摘要" /></template>
          </el-table-column>
          <el-table-column label="会计科目" width="220" fixed>
            <template #default="{ row }">
              <el-select v-model="row.account_code" filterable clearable size="small" placeholder="编码/名称" style="width:100%" @change="onAccountChange(row)">
                <el-option v-for="a in accounts" :key="a.id" :label="`${a.account_code} ${a.account_name}`" :value="a.account_code" />
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
          <el-table-column label="客户" width="128">
            <template #default="{ row }"><aux-select v-model="row.customer_id" :items="auxItems.customer" placeholder="客户" /></template>
          </el-table-column>
          <el-table-column label="供应商" width="128">
            <template #default="{ row }"><aux-select v-model="row.supplier_id" :items="auxItems.supplier" placeholder="供应商" /></template>
          </el-table-column>
          <el-table-column label="部门" width="116">
            <template #default="{ row }"><aux-select v-model="row.department_id" :items="auxItems.department" placeholder="部门" /></template>
          </el-table-column>
          <el-table-column label="员工" width="116">
            <template #default="{ row }"><aux-select v-model="row.employee_id" :items="auxItems.employee" placeholder="员工" /></template>
          </el-table-column>
          <el-table-column label="项目" width="118">
            <template #default="{ row }"><el-input v-model="row.project_code" size="small" placeholder="项目编码" /></template>
          </el-table-column>
          <el-table-column label="业务单号" width="136">
            <template #default="{ row }"><el-input v-model="row.order_no" size="small" placeholder="订单/退款/费用单" /></template>
          </el-table-column>
          <el-table-column label="借方金额" width="126" align="right" fixed="right">
            <template #default="{ row }"><el-input-number v-model="row.debit_amount" :min="0" :precision="2" :controls="false" size="small" style="width:106px" @focus="row.credit_amount = 0" /></template>
          </el-table-column>
          <el-table-column label="贷方金额" width="126" align="right" fixed="right">
            <template #default="{ row }"><el-input-number v-model="row.credit_amount" :min="0" :precision="2" :controls="false" size="small" style="width:106px" @focus="row.debit_amount = 0" /></template>
          </el-table-column>
          <el-table-column label="操作" width="64" fixed="right" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" :disabled="form.lines.length <= 2" @click="removeLine($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { defineComponent, h, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, ElOption, ElSelect } from 'element-plus'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const loading = ref(false)
const saving = ref(false)
const rows = ref<any[]>([])
const accounts = ref<any[]>([])
const stores = ref<any[]>([])
const showDialog = ref(false)
const editId = ref<number | null>(null)
let lineSeed = 1

const auxItems = reactive<Record<string, any[]>>({ customer: [], supplier: [], department: [], employee: [] })

const AuxSelect = defineComponent({
  name: 'AuxSelect',
  props: { modelValue: { type: Number, default: null }, items: { type: Array, default: () => [] }, placeholder: { type: String, default: '选择' } },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h(ElSelect, { modelValue: props.modelValue, filterable: true, clearable: true, size: 'small', placeholder: props.placeholder, style: 'width:100%', 'onUpdate:modelValue': (v: number | null) => emit('update:modelValue', v) }, () => (props.items as any[]).map((item) => h(ElOption, { key: item.id, label: auxLabel(item), value: item.id })))
  },
})

function newLine(seed: Record<string, any> = {}) {
  return {
    key: `tpl-line-${lineSeed++}`,
    summary: seed.summary || '',
    account_code: seed.account_code || '',
    account_name: seed.account_name || '',
    store_id: seed.store_id ?? null,
    customer_id: seed.customer_id ?? null,
    supplier_id: seed.supplier_id ?? null,
    department_id: seed.department_id ?? null,
    employee_id: seed.employee_id ?? null,
    project_code: seed.project_code || '',
    order_no: seed.order_no || '',
    debit_amount: Number(seed.debit_amount || 0),
    credit_amount: Number(seed.credit_amount || 0),
  }
}

const defaultForm = () => ({
  name: '',
  voucher_type: '记',
  summary: '',
  lines: [newLine(), newLine()],
})
const form = ref<any>(defaultForm())

function typeColor(t: string) {
  return { '记': '', '收': 'success', '付': 'danger', '转': 'warning' }[t] || ''
}

function auxLabel(item: any) {
  return `${item.item_code ? item.item_code + ' ' : ''}${item.item_name}`
}

function storeLabel(store: any) {
  return `${store.platform_name ? store.platform_name + ' / ' : ''}${store.store_name}`
}

function onAccountChange(row: any) {
  const account = accounts.value.find((a) => a.account_code === row.account_code)
  row.account_name = account?.account_name || ''
}

function addLine() {
  form.value.lines.push(newLine())
}

function copyLastLine() {
  const last = form.value.lines[form.value.lines.length - 1]
  form.value.lines.push(newLine(last))
}

function removeLine(i: number) {
  if (form.value.lines.length > 2) form.value.lines.splice(i, 1)
}

function openCreate() {
  editId.value = null
  form.value = defaultForm()
  showDialog.value = true
}

function openEdit(row: any) {
  editId.value = row.id
  form.value = {
    name: row.name,
    voucher_type: row.voucher_type,
    summary: row.summary || '',
    lines: (row.lines || []).map((l: any) => newLine(l)),
  }
  if (!form.value.lines.length) form.value.lines = [newLine(), newLine()]
  showDialog.value = true
}

function buildPayload() {
  return {
    name: form.value.name,
    voucher_type: form.value.voucher_type,
    summary: form.value.summary,
    lines: form.value.lines.map(({ key, ...line }: any) => ({
      ...line,
      debit_amount: Number(line.debit_amount || 0),
      credit_amount: Number(line.credit_amount || 0),
    })),
  }
}

function validate() {
  if (!form.value.name) return '模板名称不能为空'
  if (form.value.lines.length < 2) return '至少需要2条分录'
  const invalid = form.value.lines.find((line: any) => Number(line.debit_amount) > 0 && Number(line.credit_amount) > 0)
  if (invalid) return '同一分录行不能同时填写借方和贷方金额'
  return ''
}

async function save() {
  const message = validate()
  if (message) return ElMessage.warning(message)
  saving.value = true
  try {
    const url = editId.value
      ? `/finance/voucher-templates/${editId.value}`
      : `/finance/voucher-templates?book_id=${finStore.bookId}`
    const method = editId.value ? 'put' : 'post'
    await (request as any)[method](url, buildPayload())
    ElMessage.success('已保存')
    showDialog.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function del(row: any) {
  await ElMessageBox.confirm(`确定删除模板「${row.name}」？`, '提示', { type: 'warning' })
  await request.delete(`/finance/voucher-templates/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

async function loadAccounts() {
  const d: any = await request.get(`/finance/accounts?book_id=${finStore.bookId}`)
  accounts.value = d.accounts || []
}

async function loadStores() {
  const d: any = await request.get('/stores?include_inactive=false')
  stores.value = d.stores || d.rows || d || []
}

function auxName(key: string) {
  return ({ customer: '客户', supplier: '供应商', department: '部门', employee: '员工' } as Record<string, string>)[key]
}

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

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/voucher-templates?book_id=${finStore.bookId}`)
    rows.value = d.templates || []
  } finally {
    loading.value = false
  }
}

async function reloadAll() {
  await finStore.loadBooks()
  await Promise.all([loadAccounts(), loadStores(), loadAuxItems(), load()])
}

watch(() => finStore.bookId, () => reloadAll())

onMounted(reloadAll)
</script>

<style scoped>
.template-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.template-head h3 {
  margin: 0;
}

.lines-box {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}

.lines-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #f5f7fa;
  font-size: 13px;
  font-weight: 500;
}

:deep(.el-input-number .el-input__inner) {
  text-align: right;
}
</style>
