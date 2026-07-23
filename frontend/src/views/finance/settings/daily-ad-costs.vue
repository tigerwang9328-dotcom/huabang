<template>
  <div class="ad-cost-page">
    <!-- 顶部操作栏 -->
    <div class="top-bar">
      <div class="top-bar-left">
        <el-date-picker
          v-model="selectedDate"
          type="date"
          value-format="YYYY-MM-DD"
          format="YYYY-MM-DD"
          :clearable="false"
          placeholder="选择日期"
          style="width:150px"
          @change="onDateChange"
        />
        <el-select
          v-model="filterPlatform"
          placeholder="全部平台"
          clearable
          style="width:120px"
          @change="loadData"
        >
          <el-option v-for="p in platforms" :key="p" :label="p" :value="p" />
        </el-select>
        <el-input
          v-model="filterKeyword"
          placeholder="搜索店铺"
          clearable
          style="width:160px"
          @input="onKeywordInput"
          @clear="loadData"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button :loading="loading" @click="loadData">刷新</el-button>
      </div>
      <div class="top-bar-right">
        <el-button @click="groupMgrVisible = true">管理店铺组</el-button>
        <el-button @click="importVisible = true">从表格导入数据</el-button>
        <el-button type="info" @click="openBatchDialog">批量设置广告费</el-button>
        <el-button type="primary" :loading="saving" @click="saveAll">保存全部</el-button>
      </div>
    </div>

    <!-- 说明 -->
    <el-alert type="info" :closable="false" style="margin-bottom:14px">
      <template #default>
        <span style="font-size:12px">
          广告费和发货赔付、其他赔付按<b>日期+店铺</b>维护，广告费优先级高于数据采集广告费。
          ROI = 销售金额 ÷ 广告费（广告费为 0 时显示 —）。
          修改后须点击<b>保存全部</b>才写入数据库。
        </span>
      </template>
    </el-alert>

    <!-- 批量设置提示 -->
    <el-alert
      v-if="batchAppliedMsg"
      :title="batchAppliedMsg"
      type="success"
      show-icon
      :closable="true"
      style="margin-bottom:10px"
      @close="batchAppliedMsg = ''"
    />

    <!-- 数据表格 -->
    <el-table
      :data="displayRows"
      border stripe size="small"
      v-loading="loading"
      style="font-size:12px"
      show-summary
      :summary-method="summaryRow"
      :row-class-name="rowClassName"
    >
      <el-table-column label="#" type="index" width="40" align="center" />

      <el-table-column prop="store_name" label="店铺" min-width="180" fixed="left" show-overflow-tooltip>
        <template #default="{ row }">
          <span :style="{ paddingLeft: ((row._level || 0) * 14) + 'px', fontWeight: row._row_kind === 'group' ? 600 : 400 }">{{ row.store_name }}</span>
          <el-tag v-if="row.has_manual_record && row._row_kind !== 'group'" size="small" type="success" style="margin-left:4px">已维护</el-tag>
          <el-dropdown
            v-for="platform in availableAdPlatforms(row)"
            :key="platform.key"
            trigger="click"
            class="ad-account-dropdown"
            @command="applyAdAccount(row, platform.key, String($event || ''))"
          >
            <el-button
              size="small"
              :type="isAdAccountMaintained(row, platform.key) ? 'success' : 'info'"
              plain
              :loading="isAdAccountLoading(platform.key)"
              class="ad-account-trigger"
            >
              {{ platform.label }}
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="!accountsForPlatform(platform.key).length" disabled>
                  暂无{{ platform.label }}账户
                </el-dropdown-item>
                <el-dropdown-item command="__clear__">
                  清空广告费
                </el-dropdown-item>
                <el-dropdown-item
                  v-for="account in accountsForPlatform(platform.key)"
                  :key="accountId(platform.key, account)"
                  :command="accountId(platform.key, account)"
                >
                  {{ formatAdAccountOption(platform.key, account) }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>

      <el-table-column prop="platform" label="平台" width="72" align="center" />

      <el-table-column prop="sale_amount" label="销售金额" width="110" align="right">
        <template #default="{ row }">
          <span class="money-cell">{{ row.sale_amount > 0 ? '¥' + fmtNum(row.sale_amount) : '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="order_count" label="订单数" width="72" align="right">
        <template #default="{ row }">{{ row.order_count > 0 ? row.order_count : '—' }}</template>
      </el-table-column>

      <el-table-column prop="shipped_qty" label="发货件数" width="80" align="right">
        <template #default="{ row }">{{ row.shipped_qty > 0 ? row.shipped_qty : '—' }}</template>
      </el-table-column>

      <!-- 广告费（可编辑） -->
      <el-table-column label="广告费 (¥)" width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.ad_cost"
            :min="0"
            :max="10000000"
            :precision="0"
            :step="100"
            size="small"
            controls-position="right"
            style="width:118px"
            @change="onAdCostChange(row)"
          />
        </template>
      </el-table-column>

      <!-- 发货赔付、其他赔付（可编辑） -->
      <el-table-column label="发货赔付、其他赔付 (¥)" width="190" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.compensation_amount"
            :min="0"
            :max="10000000"
            :precision="2"
            :step="100"
            size="small"
            controls-position="right"
            style="width:150px"
          />
        </template>
      </el-table-column>

      <!-- ROI（只读，自动计算） -->
      <el-table-column label="ROI" width="72" align="right">
        <template #default="{ row }">
          <span :class="roiClass(row.roi)">{{ fmtRoi(row.roi) }}</span>
        </template>
      </el-table-column>

      <!-- 备注（可编辑） -->
      <el-table-column label="备注" min-width="160">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            size="small"
            placeholder="可空"
            clearable
          />
        </template>
      </el-table-column>

      <!-- 更新时间（只读） -->
      <el-table-column label="更新时间" width="150" align="center">
        <template #default="{ row }">
          <span style="color:#888;font-size:11px">{{ row.updated_at ? fmtTime(row.updated_at) : '—' }}</span>
        </template>
      </el-table-column>

      <!-- 更新人（只读） -->
      <el-table-column label="更新人" width="80" align="center">
        <template #default="{ row }">
          <span style="color:#888;font-size:11px">{{ row.updated_by_name || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 批量设置对话框 -->
    <el-dialog v-model="batchVisible" title="批量设置广告费" width="380px" :append-to-body="true">
      <div style="margin-bottom:12px;font-size:13px;color:#555">
        将当前筛选结果中 <b>{{ tableData.length }}</b> 家店铺的广告费统一设为：
      </div>
      <el-input-number
        v-model="batchValue"
        :min="0"
        :max="10000000"
        :precision="0"
        :step="100"
        size="default"
        controls-position="right"
        style="width:100%"
        placeholder="输入广告费金额（¥）"
      />
      <template #footer>
        <el-button @click="batchVisible = false">取消</el-button>
        <el-button type="primary" @click="applyBatch">应用到当前表格</el-button>
      </template>
    </el-dialog>

    <StoreGroupManager v-model:visible="groupMgrVisible" @changed="loadData" />
    <ImportDailyDialog v-model:visible="importVisible" :default-date="selectedDate" @imported="loadData" />
    <ReturnStatsPanel />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Search } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import request from "@/api/request"
import StoreGroupManager from "./components/StoreGroupManager.vue"
import ImportDailyDialog from "./components/ImportDailyDialog.vue"
import ReturnStatsPanel from "./components/ReturnStatsPanel.vue"
import { useGroupedRows } from "./useGroupedRows"
import { listGroups } from "@/api/storeReportGroup"

// ─── 状态 ────────────────────────────────────────────────────────────
const loading    = ref(false)
const saving     = ref(false)
const tableData  = ref<any[]>([])
const platforms  = ref<string[]>([])
const groups     = ref<any[]>([])
const groupMgrVisible = ref(false)
const importVisible = ref(false)

// 默认日期：昨天
function yesterdayStr() {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return d.toISOString().slice(0, 10)
}
const selectedDate    = ref(yesterdayStr())
const filterPlatform  = ref("")
const filterKeyword   = ref("")
let   keywordTimer: ReturnType<typeof setTimeout> | null = null

const batchVisible    = ref(false)
const batchValue      = ref(0)
const batchAppliedMsg = ref("")

type AdPlatformKey = "qianchuan" | "kuaishou" | "pinduoduo" | "wechatChannel"
type AdAccount = {
  aavid?: string
  account_key?: string
  account_name: string
  store_id?: number | null
  store_ids?: number[]
  last_biz_date: string | null
  last_ad_cost: number | null
}
type AdPlatformConfig = {
  key: AdPlatformKey
  label: string
  endpoint: string
  bindEndpoint: string
  idField: "aavid" | "account_key"
  match: RegExp
}

const adPlatformConfigs: AdPlatformConfig[] = [
  { key: "qianchuan", label: "千川", endpoint: "/sales/qianchuan/accounts", bindEndpoint: "/sales/qianchuan/accounts/bind", idField: "aavid", match: /抖音|抖店|douyin/i },
  { key: "kuaishou", label: "快手", endpoint: "/sales/kuaishou/accounts", bindEndpoint: "/sales/kuaishou/accounts/bind", idField: "account_key", match: /快手|kuaishou/i },
  { key: "pinduoduo", label: "拼多多", endpoint: "/sales/pinduoduo/accounts", bindEndpoint: "/sales/pinduoduo/accounts/bind", idField: "account_key", match: /拼多多|pinduoduo|pdd/i },
  { key: "wechatChannel", label: "视频号", endpoint: "/sales/wechat-channel/accounts", bindEndpoint: "/sales/wechat-channel/accounts/bind", idField: "account_key", match: /视频号|微信视频号|wechat/i },
]
const adAccountLoading = ref<Record<string, boolean>>({})
const adAccounts = ref<Record<string, AdAccount[]>>({})
const adAccountSelections = ref<Record<string, string>>({})

// ─── 格式化工具 ───────────────────────────────────────────────────────
function fmtNum(v: number) {
  return Number(v).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtInt(v: number) {
  return Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 0 })
}
function fmtRoi(v: number | null) {
  if (v == null || v <= 0) return "—"
  return v.toFixed(2)
}
function roiClass(v: number | null) {
  if (v == null || v <= 0) return ""
  if (v < 3) return "roi-warn"
  return "roi-ok"
}
function fmtTime(ts: string) {
  if (!ts) return "—"
  const raw = String(ts)
  const source = raw.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(raw) ? raw : raw + "Z"
  const d = new Date(source)
  if (Number.isNaN(d.getTime())) return raw.replace("T", " ").slice(0, 16)
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(d).replace(/\//g, "-")
}
function rowKey(row: any) {
  return row?._row_kind === "group" ? `group:${row._group_id}` : `store:${row.store_id}`
}
function adSelectionKey(row: any, platformKey: AdPlatformKey) {
  return `${rowKey(row)}:${platformKey}`
}
function adPlatformConfig(platformKey: AdPlatformKey) {
  return adPlatformConfigs.find(p => p.key === platformKey)!
}
function accountId(platformKey: AdPlatformKey, account: AdAccount) {
  const config = adPlatformConfig(platformKey)
  return String(account[config.idField] || "")
}
function accountName(platformKey: AdPlatformKey, account: AdAccount) {
  const raw = String(account.account_name || "").trim()
  const id = accountId(platformKey, account)
  const label = adPlatformConfig(platformKey).label
  const duplicated = new RegExp(`^${label}账户\\s*${id}$`)
  return raw && !duplicated.test(raw) ? raw : `${label}账户`
}
function formatAdAccountOption(platformKey: AdPlatformKey, account: AdAccount) {
  const cost = account.last_ad_cost == null ? "未采集" : `¥${fmtNum(Number(account.last_ad_cost))}`
  const dt = account.last_biz_date || "无日期"
  return `${accountName(platformKey, account)} ID：${accountId(platformKey, account)}｜${dt} ${cost}`
}
function platformMatchesRow(row: any, platformKey: AdPlatformKey) {
  const config = adPlatformConfig(platformKey)
  return config.match.test(String(row?.platform || "")) || config.match.test(String(row?.store_name || ""))
}
function availableAdPlatforms(row: any) {
  return adPlatformConfigs.filter(platform => {
    if (row?._row_kind === "group") {
      return (row._members || []).some((member: any) => platformMatchesRow(member, platform.key))
    }
    return platformMatchesRow(row, platform.key)
  })
}
function accountsForPlatform(platformKey: AdPlatformKey) {
  return adAccounts.value[platformKey] || []
}
function isAdAccountLoading(platformKey: AdPlatformKey) {
  return !!adAccountLoading.value[platformKey]
}
function isAdAccountMaintained(row: any, platformKey: AdPlatformKey) {
  if (adAccountSelections.value[adSelectionKey(row, platformKey)]) return true
  const rows = row?._row_kind === "group"
    ? (row._members || []).filter((member: any) => platformMatchesRow(member, platformKey))
    : [row]
  const accounts = accountsForPlatform(platformKey)
  return rows.some((member: any) => {
    const storeId = Number(member?.store_id || 0)
    return Number(member?.ad_cost || 0) > 0
      || !!member?.has_manual_record
      || accounts.some(account => {
        const accountStoreIds = Array.isArray((account as any).store_ids) ? (account as any).store_ids.map(Number) : []
        return Number((account as any).store_id || 0) === storeId || accountStoreIds.includes(storeId)
      })
  })
}

// ─── 合计行 ────────────────────────────────────────────────────────────
function summaryRow({ columns }: any) {
  const vals: string[] = columns.map(() => "")
  const rows = tableData.value
  if (!rows.length) return vals
  vals[0] = "合计"
  const totalSale = rows.reduce((s, r) => s + Number(r.sale_amount || 0), 0)
  const totalAd   = rows.reduce((s, r) => s + Number(r.ad_cost   || 0), 0)
  const totalComp = rows.reduce((s, r) => s + Number(r.compensation_amount || 0), 0)
  // col index: 0=#, 1=shop, 2=platform, 3=sale, 4=orders, 5=qty, 6=ad_cost, 7=compensation, 8=roi, 9=remark, 10=time, 11=user
  vals[3] = totalSale > 0 ? "¥" + fmtNum(totalSale) : "—"
  vals[6] = totalAd > 0   ? "¥" + fmtInt(totalAd)   : "—"
  vals[7] = totalComp > 0 ? "¥" + fmtNum(totalComp) : "—"
  if (totalAd > 0) vals[8] = (totalSale / totalAd).toFixed(2)
  return vals
}

// ─── ROI 实时计算 ─────────────────────────────────────────────────────
function recalcRoi(row: any) {
  const sale = Number(row.sale_amount || 0)
  const ad   = Number(row.ad_cost     || 0)
  row.roi = ad > 0 ? round4(sale / ad) : null
}

function onAdCostChange(row: any) {
  row._clear_ad_cost = false
  if (row?._row_kind === "group") {
    ;(row._members || []).forEach((member: any) => { member._clear_ad_cost = false })
  }
  recalcRoi(row)
}

function round4(v: number) { return Math.round(v * 10000) / 10000 }
function round2(v: number) { return Math.round(v * 100) / 100 }

// ─── 店铺组分组（与 dashboard 同序）+ 组级编辑 ───────────────────────
function splitBySales(members: any[], total: number, key = 'ad_cost') {
  const totalSale = members.reduce((s, r) => s + Number(r.sale_amount || 0), 0)
  if (totalSale > 0) {
    let allocated = 0
    members.forEach((m, i) => {
      const share = i === members.length - 1 ? round2(total - allocated) : round2(total * Number(m.sale_amount || 0) / totalSale)
      allocated += share
      m[key] = share < 0 ? 0 : share
      if (key === 'ad_cost') {
        m._clear_ad_cost = false
        recalcRoi(m)
      }
    })
  } else {
    const each = round2(total / Math.max(members.length, 1))
    members.forEach(m => {
      m[key] = each
      if (key === 'ad_cost') {
        m._clear_ad_cost = false
        recalcRoi(m)
      }
    })
  }
}
function buildGroupRow(meta: any) {
  const m = meta.members
  const sumSale = () => m.reduce((s: number, r: any) => s + Number(r.sale_amount || 0), 0)
  const sumAd = () => m.reduce((s: number, r: any) => s + Number(r.ad_cost || 0), 0)
  const sumComp = () => m.reduce((s: number, r: any) => s + Number(r.compensation_amount || 0), 0)
  const g: any = {
    _row_kind: 'group', _level: meta.level, _group_id: meta.group_id, _group_name: meta.group_name, _members: m,
    store_id: null, platform: '组', store_name: '▸ ' + meta.group_name + ' 合计（' + m.length + '店）',
    has_manual_record: false, updated_at: null, updated_by_name: '',
  }
  Object.defineProperty(g, 'sale_amount', { enumerable: true, get: sumSale, set() {} })
  Object.defineProperty(g, 'order_count', { enumerable: true, get: () => m.reduce((s: number, r: any) => s + Number(r.order_count || 0), 0), set() {} })
  Object.defineProperty(g, 'shipped_qty', { enumerable: true, get: () => m.reduce((s: number, r: any) => s + Number(r.shipped_qty || 0), 0), set() {} })
  Object.defineProperty(g, 'ad_cost', { enumerable: true, get: sumAd, set(v: any) { splitBySales(m, Number(v || 0), 'ad_cost') } })
  Object.defineProperty(g, 'compensation_amount', { enumerable: true, get: sumComp, set(v: any) { splitBySales(m, Number(v || 0), 'compensation_amount') } })
  Object.defineProperty(g, 'roi', { enumerable: true, get() { const a = sumAd(); return a > 0 ? sumSale() / a : null }, set() {} })
  Object.defineProperty(g, 'remark', { enumerable: true, get() { return '' }, set() {} })
  return g
}
const { displayRows, rowClassName } = useGroupedRows(tableData, groups, { saleKey: 'sale_amount', buildGroupRow })

// ─── 数据加载 ─────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    const params: Record<string, string> = { biz_date: selectedDate.value }
    if (filterPlatform.value) params.platform = filterPlatform.value
    if (filterKeyword.value)  params.keyword  = filterKeyword.value
    const qs = new URLSearchParams(params).toString()
    const data: any[] = await request.get(`/finance/daily-ad-costs?${qs}`)
    // ensure roi is computed
    tableData.value = data.map(r => ({
      ...r,
      ad_cost: Number(r.ad_cost || 0),
      compensation_amount: Number(r.compensation_amount || 0),
      roi: r.ad_cost > 0 ? round4(Number(r.sale_amount) / Number(r.ad_cost)) : null,
    }))
    try { groups.value = (await listGroups()) as any[] || [] } catch { groups.value = [] }
  } catch (e: any) {
    ElMessage.error("加载失败: " + (e?.message || e))
  } finally {
    loading.value = false
  }
}

async function loadPlatforms() {
  try {
    const data: string[] = await request.get("/finance/daily-ad-costs/platforms")
    platforms.value = data
  } catch {}
}

async function loadAdAccounts() {
  await Promise.all(adPlatformConfigs.map(async platform => {
    adAccountLoading.value[platform.key] = true
    try {
      const data: AdAccount[] = await request.get(`${platform.endpoint}?biz_date=${selectedDate.value}`)
      adAccounts.value[platform.key] = Array.isArray(data) ? data : []
    } catch (e: any) {
      adAccounts.value[platform.key] = []
      ElMessage.error(`${platform.label}账户加载失败: ` + (e?.message || e))
    } finally {
      adAccountLoading.value[platform.key] = false
    }
  }))
}

function onKeywordInput() {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(loadData, 400)
}

async function onDateChange() {
  adAccountSelections.value = {}
  await Promise.all([loadData(), loadAdAccounts()])
}

function targetRowsForPlatform(row: any, platformKey: AdPlatformKey) {
  if (row?._row_kind === "group") {
    return (row._members || []).filter((member: any) => platformMatchesRow(member, platformKey))
  }
  return [row]
}

async function applyAdAccount(row: any, platformKey: AdPlatformKey, accountKey: string) {
  if (accountKey === "__clear__") {
    clearAdAccount(row, platformKey)
    return
  }

  adAccountSelections.value[adSelectionKey(row, platformKey)] = accountKey || ""
  if (!accountKey) return

  const account = accountsForPlatform(platformKey).find(a => accountId(platformKey, a) === accountKey)
  if (!account) return
  if (account.last_ad_cost == null) {
    ElMessage.warning(`该${adPlatformConfig(platformKey).label}账户还没有采集到广告消耗`)
    return
  }

  const adCost = Number(account.last_ad_cost || 0)
  const targets = targetRowsForPlatform(row, platformKey)
  if (row?._row_kind === "group") {
    splitBySales(targets, adCost, "ad_cost")
    targets.forEach((member: any) => {
      member.has_manual_record = true
      member._clear_ad_cost = false
    })
    if (platformKey === "qianchuan") {
      try {
        const config = adPlatformConfig(platformKey)
        const storeIds = targets.map((member: any) => Number(member.store_id || 0)).filter(Boolean)
        await request.post(config.bindEndpoint, {
          [config.idField]: accountKey,
          store_ids: storeIds,
          biz_date: selectedDate.value,
        })
        ElMessage.success(`已绑定 ${accountName(platformKey, account)} 到当前店铺组，后续采集会按销售额自动分摊`)
      } catch (e: any) {
        ElMessage.warning(`广告费已分摊，但千川组绑定失败：${e?.response?.data?.detail || e?.message || e}`)
      }
    } else {
      ElMessage.success(`已把 ${accountName(platformKey, account)} 的广告费按销售额分摊到${adPlatformConfig(platformKey).label}店铺`)
    }
  } else {
    try {
      const config = adPlatformConfig(platformKey)
      await request.post(config.bindEndpoint, {
        [config.idField]: accountKey,
        store_id: row.store_id,
        biz_date: selectedDate.value,
      })
      ;(account as any).store_id = row.store_id
      ElMessage.success(`已绑定 ${accountName(platformKey, account)}，后续采集会自动写入该店`)
    } catch (e: any) {
      ElMessage.warning(`广告费已填入，但账户绑定失败：${e?.message || e}`)
    }
    row.ad_cost = adCost
    row._clear_ad_cost = false
    recalcRoi(row)
    row.has_manual_record = true
  }
  if (account.last_biz_date && account.last_biz_date !== selectedDate.value) {
    ElMessage.warning(`当前选择日期为 ${selectedDate.value}，该账户最近采集日期为 ${account.last_biz_date}`)
  }
}

function clearAdAccount(row: any, platformKey: AdPlatformKey) {
  adAccountSelections.value[adSelectionKey(row, platformKey)] = ""
  const targets = targetRowsForPlatform(row, platformKey)
  targets.forEach((member: any) => {
    member.ad_cost = 0
    member._clear_ad_cost = true
    member.has_manual_record = false
    recalcRoi(member)
  })
  ElMessage.success(`已清空${adPlatformConfig(platformKey).label}广告费，请点击保存全部生效`)
}

// ─── 批量设置 ─────────────────────────────────────────────────────────
function openBatchDialog() {
  batchValue.value = 0
  batchVisible.value = true
}

async function applyBatch() {
  const val = Number(batchValue.value || 0)
  if (val < 0) { ElMessage.warning("广告费不能为负数"); return }

  // 如果有已录入非零值，弹确认
  const hasNonZero = tableData.value.some(r => Number(r.ad_cost) > 0)
  if (hasNonZero) {
    try {
      await ElMessageBox.confirm(
        `当前表格中有已录入的广告费，批量设置为 ¥${fmtInt(val)} 将覆盖全部，是否继续？`,
        "确认覆盖",
        { type: "warning", confirmButtonText: "覆盖", cancelButtonText: "取消" }
      )
    } catch { return }
  }

  tableData.value.forEach(row => {
    row.ad_cost = val
    row._clear_ad_cost = false
    recalcRoi(row)
    row.has_manual_record = true
  })
  batchAppliedMsg.value = `已批量设置当前表格广告费为 ¥${fmtInt(val)}，请点击"保存全部"生效`
  batchVisible.value = false
}

// ─── 保存全部 ─────────────────────────────────────────────────────────
async function saveAll() {
  saving.value = true
  try {
    const items = tableData.value.map(r => ({
      store_id: r.store_id,
      ad_cost:  Number(r.ad_cost || 0),
      compensation_amount: Number(r.compensation_amount || 0),
      remark:   r.remark || "",
      clear_record: !!r._clear_ad_cost,
    }))
    const res: any = await request.post("/finance/daily-ad-costs/batch-save", {
      biz_date: selectedDate.value,
      items,
    })
    if (res.ok) {
      ElMessage.success(`每日广告费和赔付保存成功，共 ${res.success} 条`)
      batchAppliedMsg.value = ""
      await loadData()  // 刷新 updated_at 和 updated_by_name
    } else {
      const errMsg = (res.errors || []).map((e: any) => `店铺${e.store_id}: ${e.error}`).join("；")
      ElMessage.error(`部分保存失败：${errMsg}`)
      await loadData()
    }
  } catch (e: any) {
    ElMessage.error("保存失败: " + (e?.message || e))
  } finally {
    saving.value = false
  }
}

// ─── 生命周期 ─────────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([loadPlatforms(), loadData(), loadAdAccounts()])
})
</script>

<style scoped>
.ad-cost-page {
  padding: 16px;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
  gap: 8px;
}
.top-bar-left,
.top-bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.money-cell {
  font-variant-numeric: tabular-nums;
}
.ad-account-dropdown {
  margin-left: 6px;
  vertical-align: middle;
}
.ad-account-trigger {
  padding: 0 2px;
  font-size: 12px;
}
.roi-ok   { color: #10b981; font-weight: 500; }
.roi-warn { color: #f59e0b; font-weight: 500; }
:deep(.fin-group-row td) { background: #eef1f6 !important; }
</style>
