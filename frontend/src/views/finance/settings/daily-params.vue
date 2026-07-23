<template>
  <div class="params-page">
    <!-- 顶部操作栏（原样保留） -->
    <div class="top-bar">
      <div class="top-bar-left">
        <el-date-picker
          v-model="selectedMonth"
          type="month"
          value-format="YYYY-MM"
          format="YYYY年MM月"
          :clearable="false"
          placeholder="选择月份"
          style="width:150px"
          @change="loadData"
        />
        <el-button :loading="loading" @click="loadData">刷新</el-button>
      </div>
      <div class="top-bar-right">
        <el-button @click="groupMgrVisible = true">管理店铺组</el-button>
        <el-button @click="importVisible = true">从表格导入数据</el-button>
        <el-button type="info" @click="copyFromLastMonth">复制上月参数</el-button>
        <el-button type="primary" :loading="saving" @click="saveAll">保存全部</el-button>
      </div>
    </div>

    <!-- 说明（原样保留） -->
    <el-alert title="日报参数说明" type="info" :closable="false" style="margin-bottom:16px">
      <template #default>
        <p style="margin:4px 0;font-size:12px">
          参数用于日报利润公式计算：<b>利润 = 实际金额 - 商品成本 + 退货成本冲回 - 运费险 - 包装 - 快递 - 推广 - 退货人工 - 货值损耗 - 广告费</b>
        </p>
        <p style="margin:4px 0;font-size:12px;color:#888">未配置参数的店铺，费用相关字段按 0 计算，利润仅含销售额与商品成本差。</p>
      </template>
    </el-alert>

    <!-- 参数表格 -->
    <el-table :data="displayRows" border stripe size="small" v-loading="loading" style="font-size:12px" :row-class-name="rowClassName">

      <!-- 店铺列（不加批量） -->
      <el-table-column prop="store_name" label="店铺" min-width="180" fixed="left" show-overflow-tooltip>
        <template #default="{ row }">
          <span :style="{ paddingLeft: ((row._level || 0) * 14) + 'px', fontWeight: row._row_kind === 'group' ? 600 : 400 }">{{ row.store_name }}</span>
          <el-tag v-if="!row.id && row._row_kind !== 'group'" size="small" type="warning" style="margin-left:4px">未配置</el-tag>
        </template>
      </el-table-column>

      <!-- 平台列（不加批量） -->
      <el-table-column prop="platform" label="平台" width="72" align="center" />

      <!-- 平台收入系数 -->
      <el-table-column width="128" align="right">
        <template #header>
          <div class="th-flex">
            <el-tooltip content="L = 退款后金额 × 此系数，即平台实际打款比例（如含服务费则 < 1）" placement="top">
              <span>平台收入系数&nbsp;<el-icon style="vertical-align:-2px"><InfoFilled /></el-icon></span>
            </el-tooltip>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('platform_income_rate')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.platform_income_rate"
            :min="0" :max="2" :precision="4" :step="0.01"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 预估退货率 -->
      <el-table-column width="128" align="right">
        <template #header>
          <div class="th-flex">
            <el-tooltip content="统一使用此预估值（输入百分比，如 20 表示 20%）" placement="top">
              <span>预估退货率(%)&nbsp;<el-icon style="vertical-align:-2px"><InfoFilled /></el-icon></span>
            </el-tooltip>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('estimated_return_rate_pct')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.estimated_return_rate_pct"
            :min="0" :max="100" :precision="0" :step="1"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 仅退款率 -->
      <el-table-column width="128" align="right">
        <template #header>
          <div class="th-flex">
            <el-tooltip content="日报 X 列，仅退款率。输入百分比，如 20 表示 20%" placement="top">
              <span>仅退款率(%)&nbsp;<el-icon style="vertical-align:-2px"><InfoFilled /></el-icon></span>
            </el-tooltip>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('refund_only_rate_pct')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.refund_only_rate_pct"
            :min="0" :max="100" :precision="0" :step="1"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 运费险/件 -->
      <el-table-column width="128" align="right">
        <template #header>
          <div class="th-flex">
            <span>运费险/件(Q)</span>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('freight_insurance_unit_cost')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.freight_insurance_unit_cost"
            :min="0" :max="100" :precision="4" :step="0.5"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 快递费/件 -->
      <el-table-column width="128" align="right">
        <template #header>
          <div class="th-flex">
            <span>快递费/件(S)</span>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('express_unit_cost')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.express_unit_cost"
            :min="0" :max="100" :precision="4" :step="0.5"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 包装费/单 -->
      <el-table-column width="128" align="right">
        <template #header>
          <div class="th-flex">
            <span>包装费/单(R)</span>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('package_unit_cost')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.package_unit_cost"
            :min="0" :max="100" :precision="4" :step="0.5"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 推广单件 -->
      <el-table-column width="128" align="right">
        <template #header>
          <div class="th-flex">
            <el-tooltip content="U = 销售单数 × (1-预估退货率) × 推广单件成本" placement="top">
              <span>推广单件(U)&nbsp;<el-icon style="vertical-align:-2px"><InfoFilled /></el-icon></span>
            </el-tooltip>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('promotion_unit_cost')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.promotion_unit_cost"
            :min="0" :max="1000" :precision="4" :step="1"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 退货人工/件 -->
      <el-table-column width="136" align="right">
        <template #header>
          <div class="th-flex">
            <span>退货人工/件(V)</span>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('return_labor_unit_cost')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.return_labor_unit_cost"
            :min="0" :max="100" :precision="4" :step="0.5"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 货值损耗/件 -->
      <el-table-column width="136" align="right">
        <template #header>
          <div class="th-flex">
            <span>货值损耗/件(W)</span>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('goods_loss_unit_cost')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.goods_loss_unit_cost"
            :min="0" :max="1000" :precision="4" :step="1"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 预估退货率阈值 -->
      <el-table-column width="136" align="right">
        <template #header>
          <div class="th-flex">
            <el-tooltip content="超过此预估退货率触发预警（输入百分比，如 12 表示 12%，默认 8%）" placement="top">
              <span>预估退货率阈值(%)&nbsp;<el-icon style="vertical-align:-2px"><InfoFilled /></el-icon></span>
            </el-tooltip>
            <el-tooltip content="批量设置本列参数" placement="top">
              <el-button link type="primary" class="batch-btn" @click.stop="openBatch('return_rate_warning_threshold_pct')">批量</el-button>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-model="row.return_rate_warning_threshold_pct"
            :min="0" :max="100" :precision="1" :step="1"
            size="small" controls-position="right" style="width:108px" />
        </template>
      </el-table-column>

      <!-- 启用预警（无批量，是开关） -->
      <el-table-column label="启用预警" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.warning_enabled" />
        </template>
      </el-table-column>

      <!-- 备注（无批量） -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" placeholder="备注" />
        </template>
      </el-table-column>
    </el-table>

    <div class="bottom-tip">共 {{ tableData.length }} 家店铺，已配置 {{ configuredCount }} 家</div>

    <!-- ── 批量维护弹窗 ───────────────────────────────────────────── -->
    <el-dialog
      v-model="batchDlg.visible"
      :title="`批量维护：${batchDlg.label}`"
      width="400px"
      :append-to-body="true"
      draggable
    >
      <!-- 作用范围 -->
      <el-descriptions :column="2" size="small" border style="margin-bottom:16px">
        <el-descriptions-item label="月份">{{ selectedMonth }}</el-descriptions-item>
        <el-descriptions-item label="作用店铺">{{ tableData.length }} 家（全部）</el-descriptions-item>
      </el-descriptions>

      <!-- 输入框 -->
      <div style="margin-bottom:8px;font-size:13px;color:#606266">
        输入数值
        <span style="font-size:11px;color:#909399">（允许范围：{{ batchDlg.field?.min }} ~ {{ batchDlg.field?.max }}）</span>
      </div>
      <el-input-number
        v-model="batchDlg.value"
        :min="batchDlg.field?.min"
        :max="batchDlg.field?.max"
        :precision="batchDlg.field?.precision"
        :step="batchDlg.field?.step ?? 1"
        :value-on-clear="undefined"
        style="width:100%"
        controls-position="right"
        placeholder="请输入数值"
      />
      <div v-if="batchDlg.field?.tip" style="font-size:11px;color:#909399;margin-top:6px">
        {{ batchDlg.field.tip }}
      </div>

      <!-- 提示 -->
      <div style="font-size:11px;color:#92400e;background:#fffbeb;border:1px solid #fde68a;padding:8px 10px;border-radius:4px;margin-top:14px;line-height:1.6">
        ⚠️ 应用后将修改当前表格中<b>所有 {{ tableData.length }} 家店铺</b>的【{{ batchDlg.label }}】。<br>
        需点击右上角"<b>保存全部</b>"按钮才会写入系统，不会立即保存。
      </div>

      <template #footer>
        <el-button @click="batchDlg.visible = false">取消</el-button>
        <el-button type="primary" @click="applyBatch">应用到当前表格</el-button>
      </template>
    </el-dialog>

    <StoreGroupManager v-model:visible="groupMgrVisible" @changed="loadData" />
    <ImportDailyDialog v-model:visible="importVisible" :default-date="selectedMonth + '-01'" @imported="loadData" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { InfoFilled } from "@element-plus/icons-vue"
import request from "@/api/request"
import dayjs from "dayjs"
import StoreGroupManager from "./components/StoreGroupManager.vue"
import ImportDailyDialog from "./components/ImportDailyDialog.vue"
import { useGroupedRows } from "./useGroupedRows"
import { listGroups } from "@/api/storeReportGroup"

// ── 原有状态（原样保留）────────────────────────────────────────────
const selectedMonth = ref(dayjs().format("YYYY-MM"))
const loading = ref(false)
const saving  = ref(false)
const tableData = ref<any[]>([])
const groups = ref<any[]>([])
const groupMgrVisible = ref(false)
const importVisible = ref(false)

const configuredCount = computed(() => tableData.value.filter(r => r.id).length)

// ─── 店铺组分组（与 dashboard 同序）+ 组级编辑：组行填值复制到组内每家店 ───
const _GROUP_PARAM_FIELDS = ['platform_income_rate','estimated_return_rate_pct','refund_only_rate_pct','freight_insurance_unit_cost','express_unit_cost','package_unit_cost','promotion_unit_cost','return_labor_unit_cost','goods_loss_unit_cost','return_rate_warning_threshold_pct','warning_enabled']
function buildGroupRow(meta: any) {
  const m = meta.members
  const g: any = {
    _row_kind: 'group', _level: meta.level, _group_id: meta.group_id, _group_name: meta.group_name, _members: m,
    store_id: null, id: 'g' + meta.group_id, platform: '组', store_name: '▸ ' + meta.group_name + '（' + m.length + '店）',
  }
  for (const f of _GROUP_PARAM_FIELDS) {
    Object.defineProperty(g, f, {
      enumerable: true,
      get() { if (!m.length) return undefined; const v0 = m[0][f]; return m.every((x: any) => x[f] === v0) ? v0 : undefined },
      set(v: any) { m.forEach((x: any) => { x[f] = v }) },
    })
  }
  Object.defineProperty(g, 'remark', { enumerable: true, get() { return '' }, set() {} })
  return g
}
const { displayRows, rowClassName } = useGroupedRows(tableData, groups, { saleKey: 'sale_amount', buildGroupRow })

function toRow(store: any, param: any) {
  return {
    store_id:   store.store_id,
    store_name: store.store_name,
    platform:   store.platform,
    id: param?.id ?? null,
    platform_commission_rate:    param?.platform_commission_rate    ?? 0,
    platform_income_rate:        param?.platform_income_rate        ?? 1,
    estimated_return_rate_pct:   ((param?.estimated_return_rate    ?? 0) * 100),
    refund_only_rate_pct:        ((param?.refund_only_rate         ?? 0) * 100),
    freight_insurance_unit_cost: param?.freight_insurance_unit_cost ?? 0,
    express_unit_cost:           param?.express_unit_cost           ?? 0,
    package_unit_cost:           param?.package_unit_cost           ?? 0,
    promotion_unit_cost:         param?.promotion_unit_cost         ?? 0,
    return_labor_unit_cost:      param?.return_labor_unit_cost      ?? 0,
    goods_loss_unit_cost:        param?.goods_loss_unit_cost        ?? 0,
    return_rate_warning_threshold_pct: ((param?.return_rate_warning_threshold ?? 0.08) * 100),
    warning_enabled: param?.warning_enabled ?? true,
    remark: param?.remark ?? "",
  }
}

async function loadData() {
  loading.value = true
  try {
    const [storesRes, paramsRes, groupsRes] = await Promise.all([
      request.get("/finance/daily-report/params/stores"),
      request.get(`/finance/daily-report/params?month=${selectedMonth.value}`),
      listGroups(),
    ])
    groups.value = (groupsRes as any[]) || []
    const stores = (storesRes as any[]) || []
    const params = (paramsRes as any[]) || []
    const paramMap: Record<number, any> = {}
    for (const p of params) paramMap[p.store_id] = p

    tableData.value = stores.map((s: any) => toRow(s, paramMap[s.store_id] || null))
  } catch {
    ElMessage.error("加载失败")
  } finally {
    loading.value = false
  }
}

async function saveAll() {
  saving.value = true
  try {
    const rows = tableData.value.map(r => ({
      month:    selectedMonth.value,
      store_id: r.store_id,
      store_name: r.store_name,
      platform: r.platform,
      platform_commission_rate:    r.platform_commission_rate,
      platform_income_rate:        r.platform_income_rate,
      estimated_return_rate:       r.estimated_return_rate_pct / 100,
      refund_only_rate:            r.refund_only_rate_pct / 100,
      freight_insurance_unit_cost: r.freight_insurance_unit_cost,
      express_unit_cost:           r.express_unit_cost,
      package_unit_cost:           r.package_unit_cost,
      promotion_unit_cost:         r.promotion_unit_cost,
      return_labor_unit_cost:      r.return_labor_unit_cost,
      goods_loss_unit_cost:        r.goods_loss_unit_cost,
      return_rate_warning_threshold: r.return_rate_warning_threshold_pct / 100,
      warning_enabled:             r.warning_enabled,
      remark:                      r.remark,
    }))
    for (const row of rows) {
      await request.post("/finance/daily-report/params", row)
    }
    ElMessage.success(`已保存 ${rows.length} 条参数`)
    await loadData()
  } catch {
    ElMessage.error("保存失败")
  } finally {
    saving.value = false
  }
}

async function copyFromLastMonth() {
  const lastMonth = dayjs(selectedMonth.value).subtract(1, "month").format("YYYY-MM")
  try {
    await ElMessageBox.confirm(
      `将 ${lastMonth} 的参数复制到 ${selectedMonth.value}（仅复制尚未配置的店铺）？`,
      "复制上月参数",
      { type: "info", confirmButtonText: "确认复制", cancelButtonText: "取消" }
    )
    const res: any = await request.post("/finance/daily-report/params/copy-month", {
      src_month: lastMonth,
      dst_month: selectedMonth.value,
    })
    ElMessage.success(`复制完成，新增 ${res.copied} 条`)
    await loadData()
  } catch {}
}

// ── 批量维护（新增）────────────────────────────────────────────────

interface BatchFieldCfg {
  key: string
  label: string
  min: number
  max: number
  precision: number
  step: number
  tip?: string
}

const BATCH_FIELDS: BatchFieldCfg[] = [
  {
    key: "platform_income_rate",
    label: "平台收入系数",
    min: 0, max: 1.5, precision: 4, step: 0.01,
    tip: "常见值：0.95、0.97、1.00（代表平台打款比例，不是扣点百分比）",
  },
  {
    key: "estimated_return_rate_pct",
    label: "预估退货率(%)",
    min: 0, max: 100, precision: 0, step: 1,
    tip: "输入百分比数值：如填 35 代表 35%，系统内部按 0.35 保存",
  },
  {
    key: "refund_only_rate_pct",
    label: "仅退款率(%)",
    min: 0, max: 100, precision: 0, step: 1,
    tip: "输入百分比数值：如填 20 代表 20%，系统内部按 0.20 保存",
  },
  {
    key: "freight_insurance_unit_cost",
    label: "运费险/件(Q)",
    min: 0, max: 100, precision: 4, step: 0.5,
  },
  {
    key: "express_unit_cost",
    label: "快递费/件(S)",
    min: 0, max: 100, precision: 4, step: 0.5,
  },
  {
    key: "package_unit_cost",
    label: "包装费/单(R)",
    min: 0, max: 100, precision: 4, step: 0.5,
  },
  {
    key: "promotion_unit_cost",
    label: "推广单件(U)",
    min: 0, max: 1000, precision: 4, step: 1,
  },
  {
    key: "return_labor_unit_cost",
    label: "退货人工/件(V)",
    min: 0, max: 100, precision: 4, step: 0.5,
  },
  {
    key: "goods_loss_unit_cost",
    label: "货值损耗/件(W)",
    min: 0, max: 1000, precision: 4, step: 1,
  },
  {
    key: "return_rate_warning_threshold_pct",
    label: "预估退货率阈值(%)",
    min: 0, max: 100, precision: 1, step: 1,
    tip: "输入百分比数值：如填 8 代表 8%，系统内部按 0.08 保存",
  },
]

const BATCH_FIELD_MAP: Record<string, BatchFieldCfg> = Object.fromEntries(
  BATCH_FIELDS.map(f => [f.key, f])
)

const batchDlg = reactive({
  visible: false,
  fieldKey: "",
  label: "",
  value: undefined as number | undefined,
  field: null as BatchFieldCfg | null,
})

function openBatch(fieldKey: string) {
  const field = BATCH_FIELD_MAP[fieldKey]
  if (!field) return

  // 取当前列第一个非零非undefined行的值作为默认值
  const firstRow = tableData.value.find(r => {
    const v = r[fieldKey]
    return v !== null && v !== undefined && v !== 0
  })

  batchDlg.fieldKey = fieldKey
  batchDlg.label    = field.label
  batchDlg.field    = field
  batchDlg.value    = firstRow ? Number(firstRow[fieldKey]) : undefined
  batchDlg.visible  = true
}

async function applyBatch() {
  const { field, fieldKey, label, value } = batchDlg

  // 必填校验
  if (value === undefined || value === null || isNaN(Number(value))) {
    ElMessage.warning("请先输入有效数值")
    return
  }
  if (!field) return

  const numVal = Number(value)

  // 范围校验
  if (numVal < field.min || numVal > field.max) {
    ElMessage.error(`【${label}】必须在 ${field.min} ~ ${field.max} 之间，当前输入：${numVal}`)
    return
  }

  // 检查是否有已有非零值（需要覆盖确认）
  const hasExisting = tableData.value.some(r => {
    const v = r[fieldKey]
    return v !== null && v !== undefined && Number(v) !== 0
  })

  if (hasExisting) {
    try {
      await ElMessageBox.confirm(
        `当前列已有部分店铺存在参数，是否覆盖当前表格中所有 ${tableData.value.length} 家店铺的【${label}】为 ${numVal}？`,
        "确认覆盖",
        {
          type: "warning",
          confirmButtonText: "确认覆盖",
          cancelButtonText: "取消",
          distinguishCancelAndClose: true,
        }
      )
    } catch {
      return
    }
  }

  // 批量写入 tableData（不触碰数据库）
  tableData.value.forEach(row => {
    row[fieldKey] = numVal
  })

  batchDlg.visible = false
  ElMessage.success({
    message: `已批量设置【${label}】为 ${numVal}，请点击右上角"保存全部"生效`,
    duration: 4000,
  })
}

onMounted(loadData)
</script>

<style scoped>
.params-page  { display: flex; flex-direction: column; gap: 16px; }
.top-bar      { display: flex; justify-content: space-between; align-items: center; }
.top-bar-left, .top-bar-right { display: flex; gap: 8px; align-items: center; }
.bottom-tip   { font-size: 12px; color: #888; text-align: right; padding-top: 4px; }

/* 表头：字段名 + 批量按钮并排 */
.th-flex {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  white-space: nowrap;
  overflow: hidden;
}

/* 批量按钮：小、不抢眼、hover 变主色 */
.batch-btn {
  font-size: 10px !important;
  padding: 0 2px !important;
  min-height: auto !important;
  line-height: 1.4 !important;
  color: #c0c4cc !important;
  flex-shrink: 0;
}
.batch-btn:hover {
  color: var(--el-color-primary) !important;
}
:deep(.fin-group-row td) { background: #eef1f6 !important; }
</style>
