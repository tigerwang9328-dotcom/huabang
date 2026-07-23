<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">科目余额表</h3>
      <div style="display:flex;gap:8px">
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM"
          placeholder="期间" @change="load" style="width:150px" />
        <el-button :icon="Refresh" circle @click="load" />
      </div>
    </div>
    <el-table :data="rows" stripe border size="small" v-loading="loading"
      row-key="account_code" default-expand-all>
      <el-table-column prop="account_code" label="科目编码" width="120" />
      <el-table-column prop="account_name" label="科目名称" min-width="160" />
      <el-table-column label="期初余额" align="center" header-align="center">
        <el-table-column prop="opening_debit" label="借方" width="110" align="right" :formatter="fmt" />
        <el-table-column prop="opening_credit" label="贷方" width="110" align="right" :formatter="fmt" />
      </el-table-column>
      <el-table-column label="本期发生额" align="center" header-align="center">
        <el-table-column prop="period_debit" label="借方" width="110" align="right" :formatter="fmt" />
        <el-table-column prop="period_credit" label="贷方" width="110" align="right" :formatter="fmt" />
      </el-table-column>
      <el-table-column label="期末余额" align="center" header-align="center">
        <el-table-column prop="closing_debit" label="借方" width="110" align="right" :formatter="fmt" />
        <el-table-column prop="closing_credit" label="贷方" width="110" align="right" :formatter="fmt" />
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length===0" description="暂无数据" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from "vue"
import { Refresh } from "@element-plus/icons-vue"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"
import dayjs from "dayjs"

const finStore = useFinanceStore()
const loading = ref(false), rows = ref<any[]>([])
const period = ref(dayjs().format("YYYY-MM"))
const fmt = (_r: any, _c: any, v: number) => v != null && v !== 0 ? '¥' + Number(v).toLocaleString() : '—'

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/books/account-balance?book_id=${finStore.bookId}&period=${period.value}`)
    rows.value = d.rows || []
  } finally { loading.value = false }
}

onMounted(async () => {
  await finStore.loadBooks()
  if (finStore.currentPeriod) period.value = finStore.currentPeriod
  load()
})

watch(() => finStore.bookId, () => load())
watch(() => finStore.currentPeriod, (val) => {
  if (!val || val === period.value) return
  period.value = val
  load()
})
</script>
