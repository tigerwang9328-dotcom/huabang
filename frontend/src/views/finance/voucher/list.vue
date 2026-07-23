<template>
  <div class="voucher-list-page">
    <!-- 搜索工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-date-picker v-model="filterPeriod" type="month" value-format="YYYY-MM"
          placeholder="期间" style="width:130px" @change="load" />
        <el-select v-model="filterStatus" style="width:110px" @change="load" clearable placeholder="状态">
          <el-option label="草稿" value="draft" />
          <el-option label="已审核" value="reviewed" />
          <el-option label="已过账" value="posted" />
          <el-option label="已冲销" value="reversed" />
        </el-select>
        <el-select v-model="filterType" style="width:100px" @change="load" clearable placeholder="凭证字">
          <el-option label="记" value="记" />
          <el-option label="收" value="收" />
          <el-option label="付" value="付" />
          <el-option label="转" value="转" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <el-button :icon="Refresh" @click="load" :loading="loading">刷新</el-button>
        <el-button plain :icon="Download" @click="exportExcel" :loading="exporting">导出</el-button>
        <el-button type="primary" :icon="Plus" @click="$router.push('/finance/voucher/new')">录凭证</el-button>
      </div>
    </div>

    <!-- 统计行 -->
    <div class="stats-row" v-if="stats.total > 0">
      <span>共 <b>{{ stats.total }}</b> 张</span>
      <el-divider direction="vertical" />
      <span>草稿 <b class="text-gray">{{ stats.draft }}</b></span>
      <el-divider direction="vertical" />
      <span>已审核 <b class="text-warning">{{ stats.reviewed }}</b></span>
      <el-divider direction="vertical" />
      <span>已过账 <b class="text-success">{{ stats.posted }}</b></span>
      <el-divider direction="vertical" />
      <span>借方合计 <b>¥{{ fmtNum(stats.totalDebit) }}</b></span>
    </div>

    <!-- 表格 -->
    <el-table :data="rows" stripe border size="small" v-loading="loading"
      @row-click="viewDetail" style="cursor:pointer">
      <el-table-column type="selection" width="40" />
      <el-table-column prop="voucher_no" label="凭证号" width="140" />
      <el-table-column prop="voucher_date" label="日期" width="105" />
      <el-table-column prop="voucher_type" label="字" width="55" align="center">
        <template #default="{row}">
          <el-tag size="small" type="info">{{ row.voucher_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
      <el-table-column prop="total_debit" label="借方合计" width="120" align="right"
        :formatter="(_r,_c,v)=>'¥'+fmtNum(v)" />
      <el-table-column prop="source_type" label="来源" width="90">
        <template #default="{row}">
          <el-tag size="small" :type="srcColor(row.source_type)">{{ srcLabel(row.source_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_by" label="制单人" width="90" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{row}">
          <el-tag size="small" :type="statusColor(row.status)">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" @click.stop>
        <template #default="{row}">
          <el-button size="small" link type="primary" @click.stop="review(row)"
            v-if="row.status === 'draft'">审核</el-button>
          <el-button size="small" link @click.stop="unreview(row)"
            v-if="row.status === 'reviewed'">反审核</el-button>
          <el-button size="small" link type="success" @click.stop="post(row)"
            v-if="row.status === 'reviewed'">过账</el-button>
          <el-button size="small" link type="warning" @click.stop="unpost(row)"
            v-if="row.status === 'posted'">反过账</el-button>
          <el-button size="small" link type="danger" @click.stop="del(row)"
            v-if="row.status === 'draft'">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @change="load"
      />
    </div>

    <!-- 凭证详情抽屉 -->
    <el-drawer v-model="showDetail" title="凭证详情" size="560px" destroy-on-close>
      <div v-if="detail" class="detail-wrap">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="凭证号">{{ detail.voucher_no }}</el-descriptions-item>
          <el-descriptions-item label="日期">{{ detail.voucher_date }}</el-descriptions-item>
          <el-descriptions-item label="凭证字">{{ detail.voucher_type }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="statusColor(detail.status)">{{ statusLabel(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="摘要" :span="2">{{ detail.summary }}</el-descriptions-item>
          <el-descriptions-item label="制单人">{{ detail.created_by }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ srcLabel(detail.source_type) }}</el-descriptions-item>
        </el-descriptions>

        <div class="line-title">分录明细</div>
        <el-table :data="detail.lines" border size="small">
          <el-table-column prop="account_code" label="科目编码" width="100" />
          <el-table-column prop="account_name" label="科目名称" min-width="140" />
          <el-table-column prop="summary" label="摘要" min-width="120" show-overflow-tooltip />
          <el-table-column prop="debit_amount" label="借方" width="110" align="right"
            :formatter="(_r,_c,v)=>v>0?'¥'+fmtNum(v):''" />
          <el-table-column prop="credit_amount" label="贷方" width="110" align="right"
            :formatter="(_r,_c,v)=>v>0?'¥'+fmtNum(v):''" />
        </el-table>

        <div class="balance-row">
          <span>借方合计：<b>¥{{ fmtNum(detail.total_debit) }}</b></span>
          <span>贷方合计：<b>¥{{ fmtNum(detail.total_credit) }}</b></span>
          <el-tag size="small" :type="Math.abs((detail.total_debit||0)-(detail.total_credit||0))<0.01?'success':'danger'">
            {{ Math.abs((detail.total_debit||0)-(detail.total_credit||0))<0.01 ? '借贷平衡' : '不平衡！' }}
          </el-tag>
        </div>
      </div>
      <el-skeleton v-else :rows="8" animated />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh, Download, Plus } from "@element-plus/icons-vue"
import dayjs from "dayjs"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"

const store = useFinanceStore()
const bookId = computed(() => store.bookId)

// 筛选
const filterPeriod = ref(store.currentPeriod || dayjs().format("YYYY-MM"))
const filterStatus = ref("")
const filterType = ref("")

// 列表
const loading = ref(false)
const exporting = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

// 统计
const stats = reactive({ total: 0, draft: 0, reviewed: 0, posted: 0, totalDebit: 0 })

// 详情抽屉
const showDetail = ref(false)
const detail = ref<any>(null)

// ── Helpers ──
const fmtNum = (v: number) => v != null ? Number(v).toLocaleString("zh-CN", { minimumFractionDigits: 2 }) : "0.00"
const statusLabel = (s: string) => ({ draft: "草稿", reviewed: "已审核", posted: "已过账", reversed: "已冲销" }[s] || s)
const statusColor = (s: string) => ({ draft: "" as any, reviewed: "warning", posted: "success", reversed: "info" }[s] || "")
const srcLabel = (s: string) => ({ manual: "手工", jst_daily: "JST自动", carry_forward: "结转" }[s] || s)
const srcColor = (s: string) => ({ manual: "" as any, jst_daily: "primary", carry_forward: "success" }[s] || "")

// ── Load ──
async function load() {
  loading.value = true
  try {
    const params: any = {
      book_id: bookId.value, page: page.value, page_size: pageSize.value,
    }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterType.value) params.voucher_type = filterType.value
    // 拼period到接口（后端支持period参数）
    if (filterPeriod.value) params.period = filterPeriod.value

    const d: any = await request.get("/finance/vouchers", { params })
    rows.value = d.rows || []
    total.value = d.total || 0

    // 计算统计
    stats.total = d.total || 0
    stats.draft = rows.value.filter((r: any) => r.status === "draft").length
    stats.reviewed = rows.value.filter((r: any) => r.status === "reviewed").length
    stats.posted = rows.value.filter((r: any) => r.status === "posted").length
    stats.totalDebit = rows.value.reduce((s: number, r: any) => s + (Number(r.total_debit) || 0), 0)
  } catch { ElMessage.error("加载失败") }
  finally { loading.value = false }
}

async function viewDetail(row: any) {
  showDetail.value = true
  detail.value = null
  try {
    const d: any = await request.get(`/finance/vouchers/${row.id}?book_id=${bookId.value}`)
    detail.value = d
  } catch { ElMessage.error("加载详情失败") }
}

async function review(row: any) {
  try { await request.post(`/finance/vouchers/${row.id}/review?book_id=${bookId.value}`); ElMessage.success("已审核"); load() }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "审核失败") }
}
async function unreview(row: any) {
  await ElMessageBox.confirm("确认反审核？")
  try { await request.post(`/finance/vouchers/${row.id}/unreview?book_id=${bookId.value}`); ElMessage.success("已反审核"); load() }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "反审核失败") }
}
async function post(row: any) {
  try { await request.post(`/finance/vouchers/${row.id}/post?book_id=${bookId.value}`); ElMessage.success("已过账"); load() }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "过账失败") }
}
async function unpost(row: any) {
  await ElMessageBox.confirm("确认反过账？反过账将撤销对总账的影响。", "反过账确认", { type: "warning" })
  try { await request.post(`/finance/vouchers/${row.id}/unpost?book_id=${bookId.value}`); ElMessage.success("已反过账"); load() }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "反过账失败") }
}
async function del(row: any) {
  await ElMessageBox.confirm(`确认删除凭证 ${row.voucher_no}？`)
  try { await request.delete(`/finance/vouchers/${row.id}?book_id=${bookId.value}`); ElMessage.success("已删除"); load() }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "删除失败") }
}

async function exportExcel() {
  exporting.value = true
  try {
    const res = await request.get("/finance/export/vouchers", {
      params: { book_id: bookId.value, period: filterPeriod.value },
      responseType: "blob" as any,
    })
    const url = URL.createObjectURL(res as any)
    const a = document.createElement("a"); a.href = url
    a.download = `凭证_${filterPeriod.value}.xlsx`; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error("导出失败") }
  finally { exporting.value = false }
}

onMounted(async () => {
  if (!store.loaded) await store.loadBooks()
  filterPeriod.value = store.currentPeriod || dayjs().format("YYYY-MM")
  await load()
})
</script>

<style scoped>
.voucher-list-page { display: flex; flex-direction: column; gap: 14px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.stats-row { display: flex; align-items: center; gap: 4px; font-size: 13px; color: #555; padding: 8px 12px; background: #f8f9fc; border-radius: 8px; flex-wrap: wrap; }
.text-gray { color: #999; }
.text-warning { color: #e6a23c; }
.text-success { color: #67c23a; }
.pagination { display: flex; justify-content: flex-end; margin-top: 4px; }

.detail-wrap { padding: 4px 0; }
.line-title { font-size: 13px; font-weight: 600; margin: 14px 0 8px; color: #555; }
.balance-row { display: flex; gap: 16px; align-items: center; padding: 10px 0; font-size: 13px; }
</style>
