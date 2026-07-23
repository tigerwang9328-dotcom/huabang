<template>
  <el-dialog v-model="visible" title="从表格导入数据" width="920px" :append-to-body="true" draggable @open="onOpen">
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #default>
        <p style="margin:2px 0;font-size:12px">
          一张表同时导入<b>月参数</b>、<b>广告费</b>与<b>发货赔付、其他赔付</b>：① 下载模板 → ② 填写 → ③ 选日期上传预览 → ④ 确认导入。
          也可导入两张聚水潭「销售主题分析-财务-渠道」表：1表（排除发货前取消商品）提供发货/成交/成本，2表（不排除发货前取消商品）提供实际订单与件数校对。
        </p>
        <p style="margin:2px 0;font-size:12px;color:#888">
          月参数写入所选日期所在月份（<b>{{ month }}</b>），广告费和赔付写入当天（<b>{{ bizDate }}</b>）。
          模板格式同「下载日报」：成员店缩进、每组有「合计」行（平台列=组）。在<b>成员行</b>填=改该店；在组<b>合计行</b>填=应用到全组（广告费和赔付按销售额拆分、参数复制到每家成员）。留空=保持原样（清零填 0）。
        </p>
      </template>
    </el-alert>

    <div class="imp-bar">
      <span class="imp-lbl">导入日期</span>
      <el-date-picker
        v-model="bizDate" type="date" value-format="YYYY-MM-DD" format="YYYY-MM-DD"
        :clearable="false" placeholder="选择日期" style="width:150px"
      />
      <el-button @click="onDownload">下载模板</el-button>
      <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx" :on-change="onFile">
        <el-button type="primary" :loading="previewing">选择表格并预览</el-button>
      </el-upload>
      <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx" :on-change="onJstFile">
        <el-button type="primary" :loading="previewing">导入聚水潭单表</el-button>
      </el-upload>
      <span v-if="fileName" class="imp-fn">{{ fileName }}</span>
    </div>
    <div class="jst-two-bar">
      <span class="imp-lbl">聚水潭双表</span>
      <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx" :on-change="onJstOneFile">
        <el-button type="primary">{{ jstFileOne ? '已选1表' : '选择1表（排除取消）' }}</el-button>
      </el-upload>
      <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx" :on-change="onJstTwoFile">
        <el-button type="primary">{{ jstFileTwo ? '已选2表' : '选择2表（不排除取消）' }}</el-button>
      </el-upload>
      <el-button type="primary" :disabled="!jstFileOne || !jstFileTwo" :loading="previewing" @click="onJstTwoPreview">双表合并预览</el-button>
      <span v-if="jstFileOne || jstFileTwo" class="imp-fn">{{ jstFileOne?.name || '未选1表' }} / {{ jstFileTwo?.name || '未选2表' }}</span>
    </div>

    <template v-if="preview">
      <div class="imp-stat">
        <template v-if="importMode === 'daily'">
          <el-tag type="success" size="small">参数更新 {{ paramCount }}</el-tag>
          <el-tag type="success" size="small">广告费更新 {{ adCount }}</el-tag>
          <el-tag type="success" size="small">赔付更新 {{ compensationCount }}</el-tag>
        </template>
        <template v-else>
          <el-tag type="success" size="small">日报基础数据 {{ dailyCount }}</el-tag>
          <el-tag type="info" size="small">来源：聚水潭渠道财务表</el-tag>
        </template>
        <el-tag v-if="preview.unmatched.length" type="warning" size="small">未匹配 {{ preview.unmatched.length }}</el-tag>
        <el-tag v-if="preview.errors.length" type="danger" size="small">异常 {{ preview.errors.length }}</el-tag>
      </div>
      <el-alert v-if="preview.unmatched.length" type="warning" :closable="false" style="margin-bottom:8px"
        :title="`未匹配（跳过）：${preview.unmatched.join('、')}`" />
      <el-alert v-if="preview.errors.length" type="error" :closable="false" style="margin-bottom:8px">
        <template #default>
          <div v-for="(e,i) in preview.errors" :key="i" style="font-size:12px">第 {{ e.row }} 行：{{ e.msg }}</div>
        </template>
      </el-alert>

      <el-table v-if="importMode === 'daily'" :data="preview.matched" border stripe size="small" height="320" style="font-size:12px">
        <el-table-column prop="store_name" label="店铺" min-width="140" fixed show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="60" align="center" />
        <el-table-column label="来源组" width="90" show-overflow-tooltip><template #default="{row}"><el-tag v-if="row._group" size="small" type="warning">{{ row._group }}</el-tag><span v-else style="color:#c0c4cc">—</span></template></el-table-column>
        <el-table-column label="收入系数" width="84" align="right"><template #default="{row}">{{ disp(row.platform_income_rate) }}</template></el-table-column>
        <el-table-column label="预估退货率" width="86" align="right"><template #default="{row}">{{ disp(row.estimated_return_rate) }}</template></el-table-column>
        <el-table-column label="运费险" width="68" align="right"><template #default="{row}">{{ disp(row.freight_insurance_unit_cost) }}</template></el-table-column>
        <el-table-column label="快递" width="64" align="right"><template #default="{row}">{{ disp(row.express_unit_cost) }}</template></el-table-column>
        <el-table-column label="包装" width="64" align="right"><template #default="{row}">{{ disp(row.package_unit_cost) }}</template></el-table-column>
        <el-table-column label="推广" width="64" align="right"><template #default="{row}">{{ disp(row.promotion_unit_cost) }}</template></el-table-column>
        <el-table-column label="退货人工" width="78" align="right"><template #default="{row}">{{ disp(row.return_labor_unit_cost) }}</template></el-table-column>
        <el-table-column label="货值损耗" width="78" align="right"><template #default="{row}">{{ disp(row.goods_loss_unit_cost) }}</template></el-table-column>
        <el-table-column label="阈值" width="64" align="right"><template #default="{row}">{{ disp(row.return_rate_warning_threshold) }}</template></el-table-column>
        <el-table-column label="广告费" width="92" align="right">
          <template #default="{row}">
            <span v-if="row.ad_cost !== undefined" style="color:var(--el-color-primary)">¥{{ fmtInt(row.ad_cost) }}</span>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="发货赔付、其他赔付" width="140" align="right">
          <template #default="{row}">
            <span v-if="row.compensation_amount !== undefined" style="color:var(--el-color-primary)">¥{{ Number(row.compensation_amount).toLocaleString() }}</span>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="ad_remark" label="广告费备注" min-width="100" show-overflow-tooltip />
      </el-table>

      <el-table v-else :data="preview.matched" border stripe size="small" height="320" style="font-size:12px">
        <el-table-column prop="store_name" label="店铺" min-width="160" fixed show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="72" align="center" />
        <el-table-column prop="source_channel" label="聚水潭渠道" min-width="180" show-overflow-tooltip />
        <el-table-column label="销售金额" width="112" align="right"><template #default="{row}">¥{{ fmtMoney(row.sale_amount) }}</template></el-table-column>
        <el-table-column prop="shipped_qty" label="发货件数(M)" width="92" align="right" />
        <el-table-column prop="order_count" label="销售单数(N)" width="92" align="right" />
        <el-table-column label="产品成本" width="100" align="right"><template #default="{row}">¥{{ fmtMoney(row.sale_cogs) }}</template></el-table-column>
        <el-table-column v-if="importMode === 'jst_two'" prop="actual_order_count" label="实际订单数" width="92" align="right" />
        <el-table-column v-if="importMode === 'jst_two'" prop="actual_product_qty" label="实际产品件数" width="104" align="right" />
        <el-table-column label="实退金额" width="100" align="right"><template #default="{row}">¥{{ fmtMoney(row.refund_amount) }}</template></el-table-column>
        <el-table-column prop="refund_count" label="实退数量" width="86" align="right" />
        <el-table-column label="实退成本" width="100" align="right"><template #default="{row}">¥{{ fmtMoney(row.refund_cogs) }}</template></el-table-column>
        <el-table-column label="经营利润" width="100" align="right"><template #default="{row}">¥{{ fmtMoney(row.operating_profit) }}</template></el-table-column>
      </el-table>
    </template>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!canCommit" :loading="committing" @click="onCommit">
        {{ commitText }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue"
import { ElMessage } from "element-plus"
import { downloadTemplate, previewImport, commitImport, previewJstChannelImport, previewJstChannelImportTwo, commitJstChannelImport } from "@/api/dailyImport"
import type { DailyPreviewResult } from "@/api/dailyImport"

const visible = defineModel<boolean>("visible", { default: false })
const props = defineProps<{ defaultDate: string }>()
const emit = defineEmits<{ (e: "imported"): void }>()

const bizDate = ref(props.defaultDate)
const previewing = ref(false)
const committing = ref(false)
const fileName = ref("")
const preview = ref<DailyPreviewResult | null>(null)
const importMode = ref<"daily" | "jst" | "jst_two">("daily")
const jstFileOne = ref<File | null>(null)
const jstFileTwo = ref<File | null>(null)

const month = computed(() => (bizDate.value || "").slice(0, 7))
const _PARAM_KEYS = [
  "platform_income_rate", "estimated_return_rate", "refund_only_rate", "freight_insurance_unit_cost",
  "express_unit_cost", "package_unit_cost", "promotion_unit_cost",
  "return_labor_unit_cost", "goods_loss_unit_cost", "return_rate_warning_threshold", "remark",
]
const paramCount = computed(() =>
  preview.value ? preview.value.matched.filter(r => _PARAM_KEYS.some(k => k in r)).length : 0)
const adCount = computed(() =>
  preview.value ? preview.value.matched.filter(r => r.ad_cost !== undefined).length : 0)
const compensationCount = computed(() =>
  preview.value ? preview.value.matched.filter(r => r.compensation_amount !== undefined).length : 0)
const dailyCount = computed(() => preview.value ? preview.value.matched.length : 0)
const canCommit = computed(() =>
  importMode.value === "jst" || importMode.value === "jst_two" ? dailyCount.value > 0 : (paramCount.value > 0 || adCount.value > 0 || compensationCount.value > 0))
const commitText = computed(() =>
  importMode.value === "jst" || importMode.value === "jst_two"
    ? `确认导入聚水潭日报数据（${dailyCount.value} 家）`
    : `确认导入（参数 ${paramCount.value} · 广告费 ${adCount.value} · 赔付 ${compensationCount.value}）`)

const disp = (v: any) => (v === undefined || v === null ? "—" : v)
const fmtInt = (v: any) => Number(v || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 })
const fmtMoney = (v: any) => Number(v || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const fmtPct = (v: any) => `${(Number(v || 0) * 100).toFixed(0)}%`

function onOpen() {
  bizDate.value = props.defaultDate
  fileName.value = ""
  preview.value = null
  importMode.value = "daily"
  jstFileOne.value = null
  jstFileTwo.value = null
}

async function onDownload() {
  try { await downloadTemplate(bizDate.value) } catch { ElMessage.error("模板下载失败") }
}

async function onFile(uploadFile: any) {
  const file: File = uploadFile.raw
  if (!file) return
  if (!bizDate.value) { ElMessage.warning("请先选择导入日期"); return }
  fileName.value = file.name
  previewing.value = true
  try {
    importMode.value = "daily"
    preview.value = await previewImport(file, bizDate.value)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "解析失败"); preview.value = null
  } finally { previewing.value = false }
}

async function onJstFile(uploadFile: any) {
  const file: File = uploadFile.raw
  if (!file) return
  if (!bizDate.value) { ElMessage.warning("请先选择导入日期"); return }
  fileName.value = file.name
  previewing.value = true
  try {
    importMode.value = "jst"
    preview.value = await previewJstChannelImport(file, bizDate.value)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "聚水潭表格解析失败"); preview.value = null
  } finally { previewing.value = false }
}

function onJstOneFile(uploadFile: any) {
  const file: File = uploadFile.raw
  if (!file) return
  jstFileOne.value = file
  preview.value = null
  importMode.value = "jst_two"
}

function onJstTwoFile(uploadFile: any) {
  const file: File = uploadFile.raw
  if (!file) return
  jstFileTwo.value = file
  preview.value = null
  importMode.value = "jst_two"
}

async function onJstTwoPreview() {
  if (!jstFileOne.value || !jstFileTwo.value) { ElMessage.warning("请先选择1表和2表"); return }
  if (!bizDate.value) { ElMessage.warning("请先选择导入日期"); return }
  fileName.value = ""
  previewing.value = true
  try {
    importMode.value = "jst_two"
    preview.value = await previewJstChannelImportTwo(jstFileOne.value, jstFileTwo.value, bizDate.value)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "聚水潭双表解析失败"); preview.value = null
  } finally { previewing.value = false }
}

async function onCommit() {
  if (!preview.value || !canCommit.value) return
  committing.value = true
  try {
    if (importMode.value === "jst" || importMode.value === "jst_two") {
      const res: any = await commitJstChannelImport(bizDate.value, preview.value.matched)
      ElMessage.success(`已导入聚水潭日报基础数据：${res.daily_count} 家`)
    } else {
      const res: any = await commitImport(bizDate.value, preview.value.matched)
      ElMessage.success(`已导入：参数 ${res.param_count} 家、广告费 ${res.ad_count} 家、赔付 ${res.compensation_count || 0} 家`)
    }
    emit("imported"); visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "导入失败")
  } finally { committing.value = false }
}
</script>

<style scoped>
.imp-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.jst-two-bar { display: flex; align-items: center; gap: 10px; margin: -2px 0 12px; flex-wrap: wrap; }
.imp-lbl { font-size: 13px; color: #606266; }
.imp-fn { font-size: 12px; color: #606266; }
.imp-stat { display: flex; gap: 6px; margin-bottom: 8px; }
</style>
