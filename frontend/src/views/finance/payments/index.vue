<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">出账管理</h3>
      <div style="display:flex;gap:8px">
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM"
          @change="load" style="width:150px" placeholder="期间" />
        <el-button type="primary" @click="openAdd">+ 记一笔</el-button>
      </div>
    </div>

    <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">
      <el-card v-for="acc in bankAccounts" :key="acc.id" style="min-width:160px;flex:1">
        <div style="font-size:12px;color:#999">{{ acc.account_name }}</div>
        <div style="font-size:18px;font-weight:700;margin-top:4px;color:#409eff">
          ¥{{ Number(acc.balance||0).toLocaleString() }}
        </div>
      </el-card>
    </div>

    <el-table :data="rows" stripe border size="small" v-loading="loading">
      <el-table-column prop="payment_date" label="日期" width="110" />
      <el-table-column prop="payment_type" label="类型" width="80">
        <template #default="{row}">
          <el-tag size="small" :type="row.payment_type==='income'?'success':'danger'">
            {{ row.payment_type==='income'?'收入':'支出' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="counterparty" label="对方" width="140" show-overflow-tooltip />
      <el-table-column prop="amount" label="金额" width="120" align="right" :formatter="fmt" />
      <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
      <el-table-column prop="bank_account" label="账户" width="120" />
    </el-table>
    <el-empty v-if="!loading && rows.length===0" description="暂无流水" />

    <el-dialog v-model="showAdd" title="记一笔" width="500px">
      <el-form :model="addForm" label-width="80px">
        <el-form-item label="类型">
          <el-radio-group v-model="addForm.payment_type">
            <el-radio value="income">收入</el-radio>
            <el-radio value="expense">支出</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="addForm.payment_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="对方"><el-input v-model="addForm.counterparty" /></el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="addForm.amount" :min="0" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="摘要"><el-input v-model="addForm.summary" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd=false">取消</el-button>
        <el-button type="primary" @click="savePayment" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { ElMessage } from "element-plus"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"
import dayjs from "dayjs"

const finStore = useFinanceStore()
const loading = ref(false), saving = ref(false), showAdd = ref(false)
const rows = ref<any[]>([]), bankAccounts = ref<any[]>([])
const period = ref(dayjs().format("YYYY-MM"))

const defaultForm = () => ({ payment_type: 'expense', payment_date: '', counterparty: '', amount: 0, summary: '' })
const addForm = ref(defaultForm())
const fmt = (_r: any, _c: any, v: number) => v != null ? '¥' + Number(v).toLocaleString() : '—'

function openAdd() { addForm.value = defaultForm(); showAdd.value = true }

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/payments?book_id=${finStore.bookId}&period=${period.value}`)
    rows.value = d.rows || []
    bankAccounts.value = d.bank_accounts || []
  } finally { loading.value = false }
}

async function savePayment() {
  saving.value = true
  try {
    await request.post(`/finance/payments?book_id=${finStore.bookId}`, addForm.value)
    ElMessage.success("已保存")
    showAdd.value = false
    load()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败") }
  finally { saving.value = false }
}

onMounted(() => {
  finStore.loadBooks()
  if (finStore.currentPeriod) period.value = finStore.currentPeriod
  load()
})
</script>
