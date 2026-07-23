<template>
  <el-card class="rss-panel" shadow="never" style="margin-top:16px">
    <template #header>
      <div class="rss-hd">
        <span class="rss-title">款式退货退款查询（下单时间口径）</span>
        <el-tag v-if="fromCache" size="small" type="success" effect="plain">每日 08:00 自动更新</el-tag>
        <el-date-picker
          v-model="range" type="daterange" value-format="YYYY-MM-DD"
          range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期"
          :clearable="false" size="small" style="width:240px"
        />
        <el-button size="small" type="primary" :loading="loading" @click="onCompute">
          {{ loading ? `计算中…${elapsed}s` : '计算' }}
        </el-button>
        <el-button size="small" :loading="refreshing" @click="onRefreshCache" title="按默认前20~10天窗口立即重算并刷新缓存">
          {{ refreshing ? `刷新中…${elapsed}s` : '刷新默认' }}
        </el-button>
        <el-input v-model="keyword" size="small" placeholder="搜款式名 / SPU" clearable
                  style="width:170px" />
        <span class="rss-lbl">最小订单数</span>
        <el-input-number v-model="minTotal" :min="0" :step="5" size="small" controls-position="right"
                         style="width:96px" />
        <template v-if="result">
          <span class="rss-time">数据截至：<b :class="{ 'rss-stale': isStale }">{{ result.data_as_of || '未知' }}</b></span>
          <span class="rss-time">计算时间：{{ result.computed_at }}</span>
        </template>
        <div style="flex:1" />
        <template v-if="result && displayRows.length">
          <span class="rss-time">共 {{ displayRows.length }} 款</span>
          <el-button size="small" @click="onExport">导出表格</el-button>
        </template>
      </div>
    </template>

    <el-alert v-if="isStale" type="warning" :closable="false" show-icon style="margin-bottom:8px"
      :title="`注意：数据截至 ${result?.data_as_of}，与计算时间相差较大，中台同步可能滞后，数字偏旧。`" />
    <el-alert type="info" :closable="false" style="margin-bottom:10px">
      <template #default>
        <span style="font-size:12px">
          与「退货数据（店铺口径）」<b>同口径</b>，维度改为<b>款式(SPU)</b>：按<b>下单时间</b>统计，
          <b>计数单位=订单数</b>（窗口内含该款的去重订单数；含多款的订单退款<b>整单归属</b>到所含每个款式）。
          已退=订单有已确认退款，待退=订单有待确认退款，二者仅在<b>已发货</b>订单中计。
          预估退款率=(已发货里 待退+已退)/订单总数；
          <b>总退款率(含未发货)</b>=不限发货状态的(待退+已退)/订单总数（含未发货就取消退款的单）；
          仅退款率=(订单总数−已发货)/订单总数。退款类型仅含 普通退货/仅退款/拒收退货。
          <b>默认每天 08:00 自动计算「前 20~10 天」滚动窗口并缓存，进页面即展示</b>；改日期点「计算」可临时查任意区间。
        </span>
      </template>
    </el-alert>

    <el-table v-if="result" v-loading="loading || refreshing" :data="displayRows" border stripe size="small"
              style="font-size:12px" max-height="520" :default-sort="{ prop: 'total', order: 'descending' }"
              show-summary :summary-method="summary">
      <el-table-column label="序号" type="index" width="60" align="center" />
      <el-table-column label="款式 SPU" prop="spu_id" width="120" show-overflow-tooltip sortable />
      <el-table-column label="款式名称" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.spu_name_missing" style="color:#c0c4cc">（未维护名称）</span>
          <span v-else>{{ row.spu_name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="pending_refund" label="已发货待退款" width="110" align="right" sortable />
      <el-table-column prop="refunded" label="已发货已退款" width="110" align="right" sortable />
      <el-table-column prop="shipped" label="已发货订单数" width="110" align="right" sortable />
      <el-table-column prop="total" label="订单总数" width="96" align="right" sortable />
      <el-table-column prop="est_refund_rate" label="预估退款率" width="104" align="right" sortable>
        <template #default="{ row }">
          <span :class="rateClass(row.est_refund_rate)">{{ pct(row.est_refund_rate) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="total_refund_rate" label="总退款率(含未发货)" width="138" align="right" sortable>
        <template #default="{ row }">
          <span :class="rateClass(row.total_refund_rate)">{{ pct(row.total_refund_rate) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="only_refund_rate" label="仅退款率" width="96" align="right" sortable>
        <template #default="{ row }">{{ pct(row.only_refund_rate) }}</template>
      </el-table-column>
    </el-table>
    <el-empty v-else v-loading="loading" description="正在加载每日缓存…若无数据请点「刷新默认」" :image-size="60" />
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { ElMessage } from "element-plus"
import { getSpuReturnStats, getSpuReturnCache, refreshSpuReturnCache } from "@/api/returnStats"
import type { SpuReturnResult, SpuReturnRow } from "@/api/returnStats"

// 默认窗口：前 20 天 ~ 前 10 天（含两端）
function daysAgo(n: number): string {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10)
}
const range = ref<[string, string]>([daysAgo(20), daysAgo(10)])
const loading = ref(false)
const refreshing = ref(false)
const elapsed = ref(0)
const result = ref<SpuReturnResult | null>(null)
const fromCache = ref(false)
const keyword = ref("")
const minTotal = ref(0)
let timer: any = null

const pct = (v: number) => `${(Number(v || 0) * 100).toFixed(2)}%`
function rateClass(v: number) {
  const n = Number(v || 0)
  return n > 0.3 ? "rss-rate-high" : n > 0.15 ? "rss-rate-mid" : ""
}

const displayRows = computed<SpuReturnRow[]>(() => {
  const rows = result.value?.rows || []
  const kw = keyword.value.trim().toLowerCase()
  const mt = Number(minTotal.value || 0)
  return rows.filter(r => {
    if (r.total < mt) return false
    if (!kw) return true
    return String(r.spu_id).toLowerCase().includes(kw) || (r.spu_name || "").toLowerCase().includes(kw)
  })
})

const isStale = computed(() => {
  const r = result.value
  if (!r || !r.data_as_of) return false
  const a = new Date(r.data_as_of.replace(" ", "T")).getTime()
  const c = new Date(r.computed_at.replace(" ", "T")).getTime()
  return c - a > 30 * 60 * 1000
})

function startTimer() { elapsed.value = 0; timer = setInterval(() => { elapsed.value += 1 }, 1000) }
function stopTimer() { clearInterval(timer) }

// 进页面：常态读取每日缓存直接展示
onMounted(async () => {
  loading.value = true
  try {
    const c = await getSpuReturnCache()
    if (c && c.cached !== false && c.rows) {
      result.value = c
      fromCache.value = true
      if (c.date_from && c.date_to) range.value = [c.date_from, c.date_to]
    }
  } catch { /* 缓存读取失败则保持空态，用户可手动计算 */ }
  finally { loading.value = false }
})

async function onCompute() {
  if (!range.value?.[0] || !range.value?.[1]) { ElMessage.warning("请选择日期范围"); return }
  loading.value = true; startTimer();
  try {
    result.value = await getSpuReturnStats(range.value[0], range.value[1])
    fromCache.value = false
    ElMessage.success(`计算完成，共 ${result.value.rows.length} 款`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || "计算失败")
  } finally { loading.value = false; stopTimer() }
}

async function onRefreshCache() {
  refreshing.value = true; startTimer()
  try {
    result.value = await refreshSpuReturnCache()
    fromCache.value = true
    if (result.value && (result.value as any).date_from && (result.value as any).date_to)
      range.value = [(result.value as any).date_from, (result.value as any).date_to]
    ElMessage.success("默认窗口已重算并刷新缓存")
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || "刷新失败")
  } finally { refreshing.value = false; stopTimer() }
}

function summary({ columns }: any) {
  const v: string[] = columns.map(() => "")
  const rows = displayRows.value
  if (!rows.length) return v
  const sum = (k: keyof SpuReturnRow) => rows.reduce((s, r) => s + Number(r[k] || 0), 0)
  const total = sum("total"), shipped = sum("shipped"), pd = sum("pending_refund"), rf = sum("refunded")
  const incl = sum("refund_incl")
  v[0] = "合计"
  v[3] = String(pd); v[4] = String(rf); v[5] = String(shipped); v[6] = String(total)
  v[7] = total ? `${((pd + rf) / total * 100).toFixed(2)}%` : "—"
  v[8] = total ? `${(incl / total * 100).toFixed(2)}%` : "—"
  v[9] = total ? `${((total - shipped) / total * 100).toFixed(2)}%` : "—"
  return v
}

function csvCell(v: any): string {
  const s = v == null ? "" : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}
function onExport() {
  const rows = displayRows.value
  if (!rows.length) return
  const head = ["款式SPU", "款式名称", "已发货待退款", "已发货已退款", "已发货订单数", "订单总数", "预估退款率", "总退款率(含未发货)", "仅退款率"]
  const lines = [head.join(",")]
  for (const r of rows) {
    lines.push([
      r.spu_id, r.spu_name_missing ? "（未维护名称）" : (r.spu_name || ""),
      r.pending_refund, r.refunded, r.shipped, r.total,
      pct(r.est_refund_rate), pct(r.total_refund_rate), pct(r.only_refund_rate),
    ].map(csvCell).join(","))
  }
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" })
  const a = document.createElement("a")
  a.href = URL.createObjectURL(blob)
  a.download = `款式退货退款_${result.value?.start_date}_${range.value[1]}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<style scoped>
.rss-hd { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rss-title { font-weight: 600; font-size: 14px; }
.rss-lbl { font-size: 12px; color: #606266; }
.rss-time { font-size: 12px; color: #909399; }
.rss-stale { color: var(--el-color-warning); }
.rss-rate-high { color: var(--el-color-danger); font-weight: 600; }
.rss-rate-mid { color: var(--el-color-warning); }
</style>
