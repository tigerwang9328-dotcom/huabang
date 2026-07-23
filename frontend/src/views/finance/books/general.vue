<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">总账</h3>
      <div style="display:flex;gap:8px">
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM"
          placeholder="期间" @change="load" style="width:150px" />
        <el-button :icon="Refresh" circle @click="load" />
      </div>
    </div>
    <el-table :data="rows" stripe border size="small" v-loading="loading">
      <el-table-column prop="account_code" label="科目编码" width="110" />
      <el-table-column prop="account_name" label="科目名称" min-width="160" />
      <el-table-column prop="direction" label="方向" width="60" align="center">
        <template #default="{row}">
          <el-tag size="small" :type="row.direction==='debit'?'':'warning'">
            {{ row.direction==='debit'?'借':'贷' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="opening" label="期初余额" width="130" align="right" :formatter="fmtNum" />
      <el-table-column prop="period_debit" label="本期借方" width="130" align="right" :formatter="fmtNum" />
      <el-table-column prop="period_credit" label="本期贷方" width="130" align="right" :formatter="fmtNum" />
      <el-table-column prop="closing" label="期末余额" width="130" align="right">
        <template #default="{row}">
          <b>{{ fmtNum(row, null, row.closing) }}</b>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length===0" description="暂无数据，请先录入并过账凭证" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Refresh } from "@element-plus/icons-vue"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"
import dayjs from "dayjs"

const finStore = useFinanceStore()
const loading = ref(false), rows = ref<any[]>([])
const period = ref(dayjs().format("YYYY-MM"))
const fmtNum = (_r: any, _c: any, v: number) => v != null && v !== 0 ? '¥' + Number(v).toLocaleString() : '—'

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/books/general-ledger?book_id=${finStore.bookId}&period=${period.value}`)
    rows.value = d.rows || []
  } finally { loading.value = false }
}

onMounted(() => {
  finStore.loadBooks()
  if (finStore.currentPeriod) period.value = finStore.currentPeriod
  load()
})
</script>
