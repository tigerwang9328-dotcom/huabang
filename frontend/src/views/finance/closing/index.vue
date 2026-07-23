<template>
  <div class="closing-page">
    <!-- 头部 -->
    <div class="page-header">
      <h3 style="margin:0">期间结账</h3>
      <el-button type="primary" @click="initPeriods" :loading="initing">初始化期间</el-button>
    </div>

    <!-- 当前账套信息 -->
    <el-card class="info-card" shadow="never">
      <div class="book-info">
        <span class="info-item"><b>账套：</b>{{ store.currentBook?.book_name || '—' }}</span>
        <span class="info-item"><b>当前期间：</b>
          <el-tag type="primary" size="small">{{ store.currentBook?.current_period || '—' }}</el-tag>
        </span>
        <span class="info-item"><b>会计准则：</b>{{ store.currentBook?.accounting_standard || '—' }}</span>
      </div>
    </el-card>

    <!-- 操作面板 -->
    <el-card shadow="never" class="action-card">
      <template #header>
        <span class="card-title">🔒 结账操作</span>
      </template>
      <el-form inline>
        <el-form-item label="目标期间">
          <el-date-picker v-model="targetPeriod" type="month" value-format="YYYY-MM"
            placeholder="选择要结账的期间" style="width:160px" />
        </el-form-item>
        <el-form-item>
          <el-button @click="preCheck" :loading="checking">预检</el-button>
          <el-button type="primary" @click="doClose" :loading="closing" :disabled="checking">执行结账</el-button>
          <el-button type="warning" @click="doUnclose" :loading="unclosing">反结账</el-button>
          <el-button type="success" @click="doCarryForward" :loading="forwarding">结转损益</el-button>
        </el-form-item>
      </el-form>

      <!-- 预检结果 -->
      <div v-if="checkResult" class="check-result">
        <el-alert
          :title="checkResult.message"
          :type="checkResult.can_close ? 'success' : 'error'"
          show-icon :closable="false">
          <template #default>
            <span v-if="checkResult.can_close && checkResult.warning_count">
              可以结账，但还有 {{ checkResult.warning_count }} 项建议处理。
            </span>
            <span v-else-if="!checkResult.can_close">
              有 {{ checkResult.blocking_count }} 项必须处理后才能结账。
            </span>
            <span v-else>结账前检查已通过。</span>
          </template>
        </el-alert>

        <div class="check-list">
          <div v-for="item in checkResult.checks || []" :key="item.key" class="check-item">
            <div class="check-main">
              <el-tag size="small" :type="checkTagType(item)">{{ checkStatusText(item) }}</el-tag>
              <span class="check-title">{{ item.title }}</span>
              <span v-if="item.count" class="check-count">{{ item.count }}项</span>
            </div>
            <div class="check-message">
              <span>{{ item.message }}</span>
              <el-button v-if="item.action_path" size="small" link type="primary"
                @click="$router.push(item.action_path)">
                {{ item.action_label || '前往处理' }}
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 期间列表 -->
    <el-card shadow="never">
      <template #header>
        <span class="card-title">📅 期间列表</span>
      </template>
      <el-table :data="periods" stripe border size="small" v-loading="loading">
        <el-table-column prop="period" label="会计期间" width="120" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{row}">
            <el-tag size="small"
              :type="row.status==='closed'?'danger':row.status==='locked'?'info':'success'">
              {{ { open:'开放', closed:'已结账', locked:'已锁定' }[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="closed_by" label="结账人" width="120" />
        <el-table-column prop="closed_at" label="结账时间" min-width="180">
          <template #default="{row}">{{ row.closed_at ? row.closed_at.replace('T', ' ').slice(0,19) : '—' }}</template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="180">
          <template #default="{row}">
            <el-button size="small" link type="primary"
              @click="quickClose(row)" v-if="row.status==='open'">结账</el-button>
            <el-button size="small" link type="warning"
              @click="quickUnclose(row)" v-if="row.status==='closed'">反结账</el-button>
            <el-button size="small" link type="info"
              @click="lockPeriod(row)" v-if="row.status==='closed'">锁定</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 操作日志 -->
    <el-card shadow="never">
      <template #header><span class="card-title">📋 结账日志</span></template>
      <el-table :data="logs" stripe size="small" max-height="240">
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{row}">{{ row.created_at ? row.created_at.replace('T',' ').slice(0,19) : '' }}</template>
        </el-table-column>
        <el-table-column prop="action" label="操作" width="130">
          <template #default="{row}">
            <el-tag size="small" :type="row.action.includes('unclose')?'warning':row.action.includes('close')?'success':''">
              {{ actionLabel(row.action) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target" label="目标" width="150" />
        <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        <el-table-column prop="operator" label="操作人" width="100" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import dayjs from "dayjs"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"

const store = useFinanceStore()
const bookId = computed(() => store.bookId)

const loading = ref(false)
const initing = ref(false)
const checking = ref(false)
const closing = ref(false)
const unclosing = ref(false)
const forwarding = ref(false)

const periods = ref<any[]>([])
const logs = ref<any[]>([])
const targetPeriod = ref(store.currentPeriod || dayjs().format("YYYY-MM"))
const checkResult = ref<any>(null)

const actionLabel = (a: string) => ({
  close_period: '结账', unclose_period: '反结账', carry_forward: '结转损益',
  lock_period: '锁定', create_voucher: '新建凭证', review: '审核', post: '过账'
}[a] || a)

const checkTagType = (item: any) => {
  if (item.passed) return 'success'
  if (item.severity === 'error') return 'danger'
  if (item.severity === 'warning') return 'warning'
  return 'info'
}
const checkStatusText = (item: any) => {
  if (item.passed) return '通过'
  return item.severity === 'error' ? '阻止' : '提醒'
}

async function loadPeriods() {
  loading.value = true
  try {
    const d: any = await request.get("/finance/closing/periods-list", {
      params: { book_id: bookId.value }
    })
    periods.value = d.rows || []
  } catch {
    // 兼容旧接口
    try {
      const d: any = await request.get("/finance/closing/periods", { params: { book_id: bookId.value } })
      periods.value = d.periods || []
    } catch {}
  } finally { loading.value = false }
}

async function loadLogs() {
  try {
    const d: any = await request.get("/finance/closing/periods", { params: { book_id: bookId.value } })
    logs.value = d.periods || []
  } catch {}
}

async function initPeriods() {
  initing.value = true
  try {
    await request.post(`/finance/closing/init-periods?book_id=${bookId.value}`)
    ElMessage.success("期间已初始化")
    await loadPeriods()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "初始化失败") }
  finally { initing.value = false }
}

async function preCheck() {
  if (!targetPeriod.value) { ElMessage.warning("请选择期间"); return }
  checking.value = true
  try {
    const d: any = await request.post(`/finance/closing/pre-check?book_id=${bookId.value}&period=${targetPeriod.value}`)
    checkResult.value = d
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "预检失败") }
  finally { checking.value = false }
}

async function doClose() {
  if (!targetPeriod.value) { ElMessage.warning("请选择期间"); return }
  if (!checkResult.value || checkResult.value.period !== targetPeriod.value) {
    await preCheck()
  }
  if (!checkResult.value?.can_close) return
  await ElMessageBox.confirm(`确认对 ${targetPeriod.value} 执行结账？结账后本期凭证将不可修改。`, "结账确认", { type: "warning" })
  closing.value = true
  try {
    const d: any = await request.post(`/finance/closing/close?book_id=${bookId.value}&period=${targetPeriod.value}`)
    ElMessage.success(`${d.closed_period} 结账成功，当前期间已推进到 ${d.new_period}`)
    await store.loadBooks()
    checkResult.value = null
    await loadPeriods(); await loadLogs()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "结账失败") }
  finally { closing.value = false }
}

async function doUnclose() {
  if (!targetPeriod.value) { ElMessage.warning("请选择期间"); return }
  await ElMessageBox.confirm(`确认反结账 ${targetPeriod.value}？`, "反结账确认", { type: "warning" })
  unclosing.value = true
  try {
    await request.post(`/finance/closing/unclose?book_id=${bookId.value}&period=${targetPeriod.value}`)
    ElMessage.success("反结账成功")
    await store.loadBooks()
    checkResult.value = null
    await loadPeriods(); await loadLogs()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "反结账失败") }
  finally { unclosing.value = false }
}

async function doCarryForward() {
  if (!targetPeriod.value) { ElMessage.warning("请选择期间"); return }
  await ElMessageBox.confirm(`对 ${targetPeriod.value} 执行损益结转？将生成自动凭证。`)
  forwarding.value = true
  try {
    const d: any = await request.post(`/finance/closing/carry-forward?book_id=${bookId.value}&period=${targetPeriod.value}`)
    if (d.voucher_id) {
      ElMessage.success(`结转完成，凭证 ${d.voucher_no}，净利润 ¥${d.net_profit?.toLocaleString()}`)
    } else {
      ElMessage.info(d.message || "无需结转")
    }
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "结转失败") }
  finally { forwarding.value = false }
}

async function quickClose(row: any) {
  targetPeriod.value = row.period
  await preCheck()
  if (checkResult.value?.can_close) await doClose()
}
async function quickUnclose(row: any) {
  targetPeriod.value = row.period; await doUnclose()
}
async function lockPeriod(row: any) {
  await ElMessageBox.confirm(`锁定 ${row.period} 后将无法反结账，确认？`, "锁定确认", { type: "warning" })
  try {
    await request.post(`/finance/closing/lock?book_id=${bookId.value}&period=${row.period}`)
    ElMessage.success("已锁定"); await loadPeriods()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "锁定失败") }
}

onMounted(async () => {
  if (!store.loaded) await store.loadBooks()
  targetPeriod.value = store.currentPeriod || dayjs().format("YYYY-MM")
  await loadPeriods()
  await loadLogs()
})
</script>

<style scoped>
.closing-page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.info-card, .action-card { border-radius: 12px; }
.book-info { display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }
.info-item { font-size: 14px; color: #555; }
.check-result { margin-top: 12px; }
.check-list { margin-top: 10px; border: 1px solid #ebeef5; border-radius: 8px; overflow: hidden; }
.check-item { padding: 10px 12px; border-bottom: 1px solid #ebeef5; background: #fff; }
.check-item:last-child { border-bottom: 0; }
.check-main { display: flex; align-items: center; gap: 8px; min-height: 24px; }
.check-title { font-weight: 600; color: #303133; }
.check-count { color: #909399; font-size: 12px; }
.check-message { display: flex; align-items: center; gap: 8px; margin-top: 4px; padding-left: 52px; color: #606266; font-size: 13px; line-height: 20px; }
.card-title { font-size: 14px; font-weight: 600; }
</style>
