<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">发票管理</h3>
      <div style="display:flex;gap:8px">
        <el-select v-model="direction" style="width:100px" @change="load">
          <el-option label="全部" value="" />
          <el-option label="进项" value="in" />
          <el-option label="销项" value="out" />
        </el-select>
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM"
          @change="load" style="width:150px" />
        <el-button type="primary" @click="openAdd">+ 录入发票</el-button>
      </div>
    </div>

    <!-- 统计 -->
    <el-row :gutter="12" style="margin-bottom:16px">
      <el-col :span="6"><el-statistic title="进项发票" :value="inCount" suffix="张" /></el-col>
      <el-col :span="6"><el-statistic title="进项税额" :value="inTax" :precision="2" prefix="¥" /></el-col>
      <el-col :span="6"><el-statistic title="销项发票" :value="outCount" suffix="张" /></el-col>
      <el-col :span="6"><el-statistic title="销项税额" :value="outTax" :precision="2" prefix="¥" /></el-col>
    </el-row>

    <el-table :data="filteredRows" stripe border size="small" v-loading="loading">
      <el-table-column prop="invoice_no" label="发票号码" width="180" />
      <el-table-column prop="direction" label="方向" width="80">
        <template #default="{row}">
          <el-tag size="small" :type="row.direction==='in'?'success':'warning'">
            {{ row.direction==='in'?'进项':'销项' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="counterparty" label="对方单位" min-width="160" show-overflow-tooltip />
      <el-table-column prop="amount" label="金额" width="120" align="right" :formatter="fmt" />
      <el-table-column prop="tax_amount" label="税额" width="100" align="right" :formatter="fmt" />
      <el-table-column prop="invoice_date" label="开票日期" width="110" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{row}">
          <el-tag size="small" :type="row.status==='verified'?'success':''">
            {{ row.status==='verified'?'已认证':'待认证' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{row}">
          <el-button v-if="row.status!=='verified'" link size="small" type="success"
            @click="verify(row)">认证</el-button>
          <el-button link size="small" type="danger" @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && filteredRows.length===0" description="暂无发票" />

    <el-dialog v-model="showAdd" title="录入发票" width="520px">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="发票号码"><el-input v-model="addForm.invoice_no" /></el-form-item>
        <el-form-item label="方向">
          <el-radio-group v-model="addForm.direction">
            <el-radio value="in">进项（买入）</el-radio>
            <el-radio value="out">销项（卖出）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="对方单位"><el-input v-model="addForm.counterparty" /></el-form-item>
        <el-form-item label="不含税额">
          <el-input-number v-model="addForm.amount" :min="0" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="税额">
          <el-input-number v-model="addForm.tax_amount" :min="0" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="开票日期">
          <el-date-picker v-model="addForm.invoice_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd=false">取消</el-button>
        <el-button type="primary" @click="saveInvoice" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"
import dayjs from "dayjs"

const finStore = useFinanceStore()
const loading = ref(false), saving = ref(false), showAdd = ref(false)
const rows = ref<any[]>([])
const direction = ref("")
const period = ref(dayjs().format("YYYY-MM"))

const defaultForm = () => ({ invoice_no: '', direction: 'in', counterparty: '', amount: 0, tax_amount: 0, invoice_date: `${period.value || dayjs().format("YYYY-MM")}-01` })
const addForm = ref(defaultForm())
const fmt = (_r: any, _c: any, v: number) => v != null ? '¥' + Number(v).toLocaleString() : '—'

const filteredRows = computed(() => {
  if (!direction.value) return rows.value
  return rows.value.filter(r => r.direction === direction.value)
})
const inCount = computed(() => rows.value.filter(r => r.direction === 'in').length)
const outCount = computed(() => rows.value.filter(r => r.direction === 'out').length)
const inTax = computed(() => rows.value.filter(r => r.direction === 'in').reduce((s, r) => s + (r.tax_amount || 0), 0))
const outTax = computed(() => rows.value.filter(r => r.direction === 'out').reduce((s, r) => s + (r.tax_amount || 0), 0))

function openAdd() { addForm.value = defaultForm(); showAdd.value = true }

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/invoices?book_id=${finStore.bookId}&period=${period.value}`)
    rows.value = d.rows || []
  } finally { loading.value = false }
}

async function verify(row: any) {
  await request.put(`/finance/invoices/${row.id}/verify?book_id=${finStore.bookId}`)
  ElMessage.success("已认证"); load()
}

async function del(row: any) {
  await ElMessageBox.confirm("确认删除？", "提示", { type: "warning" })
  await request.delete(`/finance/invoices/${row.id}?book_id=${finStore.bookId}`)
  ElMessage.success("已删除"); load()
}

async function saveInvoice() {
  if (!addForm.value.invoice_date) { ElMessage.warning("请选择开票日期"); return }
  saving.value = true
  try {
    const payload = {
      ...addForm.value,
      invoice_type: addForm.value.direction === 'in' ? 'input' : 'output',
      counterpart: addForm.value.counterparty,
    }
    await request.post(`/finance/invoices?book_id=${finStore.bookId}`, payload)
    const invoicePeriod = addForm.value.invoice_date.slice(0, 7)
    if (invoicePeriod !== period.value) period.value = invoicePeriod
    ElMessage.success("已保存"); showAdd.value = false; load()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败") }
  finally { saving.value = false }
}

onMounted(async () => {
  await finStore.loadBooks()
  if (finStore.currentPeriod) period.value = finStore.currentPeriod
  load()
})
</script>
