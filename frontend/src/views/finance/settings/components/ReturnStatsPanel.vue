<template>
  <el-card class="rs-panel" shadow="never" style="margin-top:16px">
    <template #header>
      <div class="rs-hd">
        <span class="rs-title">退货数据（下单时间口径）</span>
        <el-tag v-if="fromCache" size="small" type="success" effect="plain">每日 08:05 自动更新</el-tag>
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
        <template v-if="result">
          <span class="rs-time">数据截至：<b :class="{ 'rs-stale': isStale }">{{ result.data_as_of || '未知' }}</b></span>
          <span class="rs-time">计算时间：{{ result.computed_at }}</span>
        </template>
        <div style="flex:1" />
        <template v-if="result && result.rows.length">
          <el-button size="small" type="warning" :loading="applying" @click="onApply">一键导入财报参数</el-button>
          <el-button size="small" :loading="exporting" @click="onExport">导出表格</el-button>
        </template>
      </div>
    </template>

    <el-alert v-if="isStale" type="warning" :closable="false" show-icon style="margin-bottom:8px"
      :title="`注意：数据截至 ${result?.data_as_of}，与计算时间相差较大，中台同步可能滞后，数字偏旧。`" />
    <el-alert type="info" :closable="false" style="margin-bottom:10px">
      <template #default>
        <span style="font-size:12px">
          按<b>下单时间</b>统计各店退货，<b>按店铺组分组</b>（成员缩进、组末为合计行，参考日报）。
          预估退款率=(待退+已退)/订单总数；仅退款率=(订单总数−已发货)/订单总数。
          数据源为中台同步数据，<b>「数据截至」为真实新鲜度</b>。
          <b>默认每天 08:05 自动计算「前 20~10 天」滚动窗口并缓存，进页面即展示</b>；改日期点「计算」可临时查任意区间。
        </span>
      </template>
    </el-alert>

    <el-table v-if="result" v-loading="loading || refreshing" :data="displayRows" border stripe size="small" style="font-size:12px"
              max-height="500" show-summary :summary-method="summary" :row-class-name="rowClassName">
      <el-table-column label="序号" width="68" align="center">
        <template #default="{ row }">{{ row._row_kind === 'group' ? '' : row.seq }}</template>
      </el-table-column>
      <el-table-column label="店铺" min-width="220" show-overflow-tooltip fixed="left">
        <template #default="{ row }">
          <span :style="{ paddingLeft: ((row._level || 0) * 14) + 'px', fontWeight: row._row_kind === 'group' ? 600 : 400 }">{{ row.store_name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="pending_refund" label="已发货待退款" width="110" align="right" />
      <el-table-column prop="refunded" label="已发货已退款" width="110" align="right" />
      <el-table-column prop="shipped" label="已发货订单数" width="110" align="right" />
      <el-table-column prop="total" label="订单总数" width="92" align="right" />
      <el-table-column label="预估退款率" width="96" align="right">
        <template #default="{ row }">{{ pct(row.est_refund_rate) }}</template>
      </el-table-column>
      <el-table-column label="仅退款率" width="92" align="right">
        <template #default="{ row }">{{ pct(row.only_refund_rate) }}</template>
      </el-table-column>
    </el-table>
    <el-empty v-else v-loading="loading" description="正在加载每日缓存…若无数据请点「刷新默认」" :image-size="60" />
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computeAndWait, applyToParams, exportXlsx, getStoreReturnCache, refreshStoreReturnCache } from "@/api/returnStats"
import type { ReturnResult } from "@/api/returnStats"
import { useGroupedRows } from "../useGroupedRows"
import { listGroups } from "@/api/storeReportGroup"

const props = defineProps<{ defaultDate?: string }>()

// 默认窗口：前 20 天 ~ 前 10 天（含两端），与 SPU 面板一致
function daysAgo(n: number): string {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10)
}
const range = ref<[string, string]>([props.defaultDate || daysAgo(20), props.defaultDate || daysAgo(10)])
const loading = ref(false)
const refreshing = ref(false)
const elapsed = ref(0)
const applying = ref(false)
const exporting = ref(false)
const result = ref<ReturnResult | null>(null)
const groups = ref<any[]>([])
const fromCache = ref(false)
let timer: any = null

const applyMonth = computed(() => (range.value?.[1] || "").slice(0, 7))
const pct = (v: number) => `${(Number(v || 0) * 100).toFixed(2)}%`

// 店铺组合计行（参考日报：成员求和、rate 重算）
function buildGroupRow(meta: any) {
  const m = meta.members
  const sum = (k: string) => m.reduce((s: number, r: any) => s + Number(r[k] || 0), 0)
  const total = sum("total"), shipped = sum("shipped"), pd = sum("pending_refund"), rf = sum("refunded")
  return {
    _row_kind: "group", _level: meta.level, _group_id: meta.group_id, _group_name: meta.group_name,
    store_id: null, seq: "",
    store_name: `▸ ${meta.group_name} 合计（${m.length}店）`,
    pending_refund: pd, refunded: rf, shipped, total,
    est_refund_rate: total ? (pd + rf) / total : 0,
    only_refund_rate: total ? (total - shipped) / total : 0,
  }
}
const rowsRef = computed(() => result.value?.rows || [])
const { displayRows, rowClassName } = useGroupedRows(rowsRef, groups, { saleKey: "total", buildGroupRow })

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
    // 先加载店铺组（缓存数据需要分组展示）
    try { groups.value = (await listGroups()) as any[] || [] } catch { groups.value = [] }
    const c = await getStoreReturnCache()
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
  loading.value = true; elapsed.value = 0; startTimer()
  try {
    try { groups.value = (await listGroups()) as any[] || [] } catch { groups.value = [] }
    result.value = await computeAndWait(range.value[0], range.value[1], s => { elapsed.value = s })
    fromCache.value = false
    ElMessage.success(`计算完成，共 ${result.value.rows.length} 家店`)
  } catch (e: any) {
    ElMessage.error(e?.message || "计算失败")
  } finally { loading.value = false; stopTimer() }
}

async function onRefreshCache() {
  refreshing.value = true; startTimer()
  try {
    try { groups.value = (await listGroups()) as any[] || [] } catch { groups.value = [] }
    const c = await refreshStoreReturnCache()
    if (c && c.rows) {
      result.value = c
      fromCache.value = true
      if (c.date_from && c.date_to) range.value = [c.date_from, c.date_to]
    }
    ElMessage.success("默认窗口已重算并刷新缓存")
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || "刷新失败")
  } finally { refreshing.value = false; stopTimer() }
}

function summary({ columns }: any) {
  const v: string[] = columns.map(() => "")
  const t = result.value?.totals
  if (!t) return v
  v[1] = "合计"
  v[2] = String(t.pending_refund); v[3] = String(t.refunded)
  v[4] = String(t.shipped); v[5] = String(t.total)
  return v
}

async function onExport() {
  if (!result.value) return
  exporting.value = true
  try {
    const groupNameById = new Map((groups.value || []).map(g => [Number(g.id), g.name]))
    const rows = displayRows.value.map(row => ({
      ...row,
      _group_name: row._group_name || groupNameById.get(Number(row._group_id)) || "",
    }))
    await exportXlsx(result.value, rows)
  }
  catch (e: any) { ElMessage.error(e?.message || "导出失败") }
  finally { exporting.value = false }
}

async function onApply() {
  if (!result.value?.rows.length) return
  const month = applyMonth.value
  const rows = result.value.rows.filter(r => r.store_id != null)
  if (!rows.length) { ElMessage.warning("没有可写入的店铺（均未在中台建档）"); return }
  try {
    await ElMessageBox.confirm(
      `将把 ${rows.length} 家店的「预估退款率」写入 ${month} 月日报参数的「预估退货率」（estimated_return_rate），覆盖原值。是否继续？`,
      "确认写入日报参数", { type: "warning", confirmButtonText: "确认写入", cancelButtonText: "取消" }
    )
  } catch { return }
  applying.value = true
  try {
    const payload = rows.map(r => ({ store_id: r.store_id, est_refund_rate: r.est_refund_rate, store_name: r.store_name }))
    const res: any = await applyToParams(month, payload)
    ElMessage.success(`已写入 ${res.count} 家店到 ${month} 日报参数`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "写入失败")
  } finally { applying.value = false }
}
</script>

<style scoped>
.rs-hd { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rs-title { font-weight: 600; font-size: 14px; }
.rs-time { font-size: 12px; color: #909399; }
.rs-stale { color: var(--el-color-warning); }
:deep(.fin-group-row td) { background: #eef1f6 !important; font-weight: 600; }
</style>
