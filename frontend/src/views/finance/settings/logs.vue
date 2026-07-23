<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">操作日志</h3>
      <div style="display:flex;gap:8px">
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
          range-separator="至" start-placeholder="开始" end-placeholder="结束" @change="load" />
        <el-button :icon="Refresh" circle @click="load" />
      </div>
    </div>
    <el-table :data="rows" stripe border size="small" v-loading="loading">
      <el-table-column prop="created_at" label="时间" width="170" />
      <el-table-column prop="operator" label="操作人" width="100" />
      <el-table-column prop="action" label="操作" width="140">
        <template #default="{row}">
          <el-tag size="small" :type="actionColor(row.action)">{{ actionLabel(row.action) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="target" label="对象" width="160" />
      <el-table-column prop="remark" label="备注" min-width="200" show-overflow-tooltip />
    </el-table>
    <el-empty v-if="!loading && rows.length===0" description="暂无操作日志" />
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
const dateRange = ref<string[]>([dayjs().subtract(30,'day').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')])

const actionLabel = (a: string) => ({ close_period:'结账', unclose_period:'反结账', lock_period:'锁账', create_voucher:'新建凭证', post_voucher:'过账', reverse_voucher:'冲销' }[a] || a)
const actionColor = (a: string) => a.includes('close') ? 'warning' : a.includes('post') ? 'success' : ''

async function load() {
  loading.value = true
  try {
    const [s, e] = dateRange.value || []
    const q = new URLSearchParams({ book_id: String(finStore.bookId), ...(s ? {start:s} : {}), ...(e ? {end:e} : {}) })
    const d: any = await request.get(`/finance/audit-logs?${q}`)
    rows.value = d.logs || []
  } finally { loading.value = false }
}

onMounted(() => { finStore.loadBooks(); load() })
</script>
