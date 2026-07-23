<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">明细账</h3>
      <div style="display:flex;gap:8px">
        <el-select v-model="accountCode" filterable placeholder="选择科目" style="width:260px" @change="load">
          <el-option v-for="a in accounts" :key="a.account_code"
            :label="`${a.account_code} ${a.account_name}`" :value="a.account_code" />
        </el-select>
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM"
          @change="load" style="width:150px" />
        <el-button :icon="Refresh" circle @click="load" />
      </div>
    </div>

    <el-alert v-if="accountCode" :title="`期初余额：¥${opening.toLocaleString()}`"
      type="info" :closable="false" style="margin-bottom:12px" />

    <el-table :data="rows" stripe border size="small" v-loading="loading">
      <el-table-column prop="voucher_no" label="凭证号" width="140" />
      <el-table-column prop="voucher_date" label="日期" width="110" />
      <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
      <el-table-column prop="debit" label="借方" width="120" align="right" :formatter="fmt" />
      <el-table-column prop="credit" label="贷方" width="120" align="right" :formatter="fmt" />
      <el-table-column prop="balance" label="余额" width="130" align="right">
        <template #default="{row}">
          <b>{{ fmt(row, null, row.balance) }}</b>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && accountCode && rows.length===0" description="本期无发生额" />
    <el-empty v-if="!accountCode" description="请选择科目" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from "vue"
import { Refresh } from "@element-plus/icons-vue"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"
import dayjs from "dayjs"

const finStore = useFinanceStore()
const loading = ref(false)
const rows = ref<any[]>([])
const accounts = ref<any[]>([])
const accountCode = ref("")
const period = ref(dayjs().format("YYYY-MM"))
const opening = ref(0)
const fmt = (_r: any, _c: any, v: number) => v != null && v !== 0 ? '¥' + Number(v).toLocaleString() : '—'

async function loadAccounts() {
  try {
    const d: any = await request.get(`/finance/accounts?book_id=${finStore.bookId}`)
    accounts.value = d.accounts || []
    if (accountCode.value && !accounts.value.some((a: any) => a.account_code === accountCode.value)) {
      accountCode.value = ""
      rows.value = []
      opening.value = 0
    }
  } catch {}
}

async function load() {
  if (!accountCode.value) return
  loading.value = true
  try {
    const d: any = await request.get(
      `/finance/ledger/detail?book_id=${finStore.bookId}&account_code=${accountCode.value}&period=${period.value}`
    )
    rows.value = d.rows || []
    opening.value = d.opening || 0
  } finally { loading.value = false }
}

onMounted(async () => {
  await finStore.loadBooks()
  if (finStore.currentPeriod) period.value = finStore.currentPeriod
  loadAccounts()
})

watch(() => finStore.bookId, async () => {
  await loadAccounts()
  load()
})
watch(() => finStore.currentPeriod, (val) => {
  if (!val || val === period.value) return
  period.value = val
  load()
})
</script>
