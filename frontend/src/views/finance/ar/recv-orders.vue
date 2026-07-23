<template>
  <div>
    <!-- KPI 卡片 -->
    <el-row :gutter="12" style="margin-bottom:16px">
      <el-col :span="6"><el-card shadow="never" class="kpi-card">
        <div class="kpi-label">应收总额</div>
        <div class="kpi-value" style="color:#409eff">{{ fmt(kpi.total_amount) }}</div>
      </el-card></el-col>
      <el-col :span="6"><el-card shadow="never" class="kpi-card">
        <div class="kpi-label">已回款</div>
        <div class="kpi-value" style="color:#67c23a">{{ fmt(kpi.received_amount) }}</div>
      </el-card></el-col>
      <el-col :span="6"><el-card shadow="never" class="kpi-card">
        <div class="kpi-label">未收余额</div>
        <div class="kpi-value" style="color:#f56c6c">{{ fmt(kpi.balance) }}</div>
      </el-card></el-col>
      <el-col :span="6"><el-card shadow="never" class="kpi-card">
        <div class="kpi-label">未结清单数</div>
        <div class="kpi-value" style="color:#e6a23c">{{ kpi.open_count }}</div>
      </el-card></el-col>
    </el-row>

    <!-- 过滤 + 操作栏 -->
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
      <el-date-picker v-model="filterPeriod" type="month" format="YYYY-MM" value-format="YYYY-MM"
        placeholder="期间" clearable style="width:130px" @change="load" />
      <el-select v-model="filterStatus" clearable placeholder="状态" style="width:100px" @change="load">
        <el-option value="open" label="未收" />
        <el-option value="partial" label="部分" />
        <el-option value="settled" label="已结清" />
        <el-option value="cancelled" label="已取消" />
      </el-select>
      <el-button type="primary" @click="openCreate" style="margin-left:auto">+ 新建应收单</el-button>
    </div>

    <el-table :data="rows" stripe border size="small" v-loading="loading"
      @row-click="(row:any) => openDetail(row)">
      <el-table-column prop="order_no" label="单号" width="150" />
      <el-table-column prop="order_date" label="日期" width="100" />
      <el-table-column prop="customer_name" label="客户" min-width="120" show-overflow-tooltip />
      <el-table-column label="应收金额" width="110" align="right">
        <template #default="{ row }">{{ fmt(row.total_amount) }}</template>
      </el-table-column>
      <el-table-column label="已回款" width="110" align="right">
        <template #default="{ row }">{{ fmt(row.received_amount) }}</template>
      </el-table-column>
      <el-table-column label="余额" width="110" align="right">
        <template #default="{ row }">
          <span :style="{ color: row.balance > 0 ? '#f56c6c' : '#67c23a' }">{{ fmt(row.balance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" @click.stop>
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click.stop="openCollect(row)"
            v-if="row.status !== 'settled' && row.status !== 'cancelled'">登记回款</el-button>
          <el-button size="small" link type="danger" @click.stop="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 详情/编辑抽屉 -->
    <el-drawer v-model="showDetail" title="应收单据详情" size="680px" direction="rtl">
      <div v-if="detail">
        <el-descriptions :column="2" border size="small" style="margin-bottom:16px">
          <el-descriptions-item label="单号">{{ detail.order_no }}</el-descriptions-item>
          <el-descriptions-item label="日期">{{ detail.order_date }}</el-descriptions-item>
          <el-descriptions-item label="客户">{{ detail.customer_name }}</el-descriptions-item>
          <el-descriptions-item label="联系人">{{ detail.contact }}</el-descriptions-item>
          <el-descriptions-item label="应收金额">{{ fmt(detail.total_amount) }}</el-descriptions-item>
          <el-descriptions-item label="已回款">{{ fmt(detail.received_amount) }}</el-descriptions-item>
          <el-descriptions-item label="余额">{{ fmt(detail.balance) }}</el-descriptions-item>
          <el-descriptions-item label="状态"><el-tag size="small" :type="statusType(detail.status)">{{ statusLabel(detail.status) }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ detail.remark }}</el-descriptions-item>
        </el-descriptions>
        <div style="font-weight:600;margin-bottom:8px">商品明细</div>
        <el-table :data="detail.lines || []" border size="small">
          <el-table-column prop="item_name" label="品名" min-width="120" />
          <el-table-column prop="spec" label="规格" width="90" />
          <el-table-column prop="quantity" label="数量" width="70" align="right" />
          <el-table-column label="单价" width="90" align="right">
            <template #default="{ row }">{{ fmt(row.unit_price) }}</template>
          </el-table-column>
          <el-table-column label="金额" width="100" align="right">
            <template #default="{ row }">{{ fmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column label="税额" width="90" align="right">
            <template #default="{ row }">{{ fmt(row.tax_amount) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <!-- 新建对话框 -->
    <el-dialog v-model="showCreate" title="新建应收单据" width="680px" :close-on-click-modal="false">
      <el-form :model="form" label-width="80px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="单号"><el-input v-model="form.order_no" placeholder="AR-2026-001" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="日期">
              <el-date-picker v-model="form.order_date" type="date" format="YYYY-MM-DD"
                value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="客户名称"><el-input v-model="form.customer_name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系人"><el-input v-model="form.contact" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
      </el-form>

      <!-- 明细行 -->
      <div style="border:1px solid #ebeef5;border-radius:4px;overflow:hidden;margin-top:8px">
        <div style="background:#f5f7fa;padding:8px 12px;display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:13px;font-weight:500">商品明细</span>
          <el-button size="small" @click="addLine">+ 添加行</el-button>
        </div>
        <el-table :data="form.lines" size="small">
          <el-table-column label="品名" min-width="120">
            <template #default="{ row }"><el-input v-model="row.item_name" size="small" /></template>
          </el-table-column>
          <el-table-column label="数量" width="80">
            <template #default="{ row }"><el-input-number v-model="row.quantity" size="small" :min="0" :controls="false" style="width:100%" @change="calcAmount(row)" /></template>
          </el-table-column>
          <el-table-column label="单价" width="100">
            <template #default="{ row }"><el-input-number v-model="row.unit_price" size="small" :min="0" :controls="false" style="width:100%" @change="calcAmount(row)" /></template>
          </el-table-column>
          <el-table-column label="金额" width="100" align="right">
            <template #default="{ row }">{{ fmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column width="50">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="form.lines.splice($index, 1)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div style="text-align:right;padding:8px 12px;font-weight:600">
          合计：{{ fmt(totalAmount) }}
        </div>
      </div>

      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 登记回款 -->
    <el-dialog v-model="showCollect" title="登记回款" width="360px">
      <el-form label-width="80px">
        <el-form-item label="回款金额">
          <el-input-number v-model="collectForm.collect_amount" :min="0.01" :max="collectMaxAmount"
            :precision="2" style="width:100%" />
          <div style="color:#909399;font-size:12px;margin-top:4px">未收余额：{{ fmt(collectMaxAmount) }}</div>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="collectForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCollect = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doCollect">确认回款</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const loading = ref(false)
const saving = ref(false)
const rows = ref<any[]>([])
const kpi = ref({ total_amount: 0, received_amount: 0, balance: 0, open_count: 0 })
const filterPeriod = ref('')
const filterStatus = ref('')

const fmt = (v: number) => '¥' + (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const statusLabel = (s: string) => ({ open: '未收', partial: '部分', settled: '已结清', cancelled: '已取消' }[s] || s)
const statusType = (s: string) => ({ open: 'danger', partial: 'warning', settled: 'success', cancelled: 'info' }[s] || '')

// ── 列表 ──
async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams({ book_id: String(finStore.bookId) })
    if (filterPeriod.value) params.set('period', filterPeriod.value)
    if (filterStatus.value) params.set('status', filterStatus.value)
    const d: any = await request.get('/finance/recv-orders?' + params)
    rows.value = d.rows || []
    kpi.value = d.kpi || {}
  } finally {
    loading.value = false
  }
}

// ── 详情 ──
const showDetail = ref(false)
const detail = ref<any>(null)
async function openDetail(row: any) {
  const d: any = await request.get(`/finance/recv-orders/${row.id}`)
  detail.value = d
  showDetail.value = true
}

// ── 新建 ──
const showCreate = ref(false)
const defaultLine = () => ({ item_name: '', spec: '', quantity: 1, unit_price: 0, amount: 0, tax_rate: 0, tax_amount: 0, remark: '' })
const form = ref<any>({ order_no: '', order_date: '', customer_name: '', contact: '', remark: '', lines: [defaultLine()] })
const totalAmount = computed(() => form.value.lines.reduce((s: number, l: any) => s + (l.amount || 0), 0))

function openCreate() {
  form.value = { order_no: '', order_date: '', customer_name: '', contact: '', remark: '', lines: [defaultLine()] }
  showCreate.value = true
}
function addLine() { form.value.lines.push(defaultLine()) }
function calcAmount(row: any) { row.amount = Math.round(row.quantity * row.unit_price * 100) / 100 }

async function save() {
  if (!form.value.order_no || !form.value.order_date) return ElMessage.warning('单号和日期不能为空')
  saving.value = true
  try {
    await request.post(`/finance/recv-orders?book_id=${finStore.bookId}`, {
      ...form.value,
      total_amount: totalAmount.value,
    })
    ElMessage.success('已保存')
    showCreate.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// ── 回款 ──
const showCollect = ref(false)
const collectId = ref<number>(0)
const collectMaxAmount = ref(0)
const collectForm = ref({ collect_amount: 0, remark: '' })

function openCollect(row: any) {
  collectId.value = row.id
  collectMaxAmount.value = row.balance
  collectForm.value = { collect_amount: row.balance, remark: '' }
  showCollect.value = true
}
async function doCollect() {
  saving.value = true
  try {
    await request.post(`/finance/recv-orders/${collectId.value}/collect`, collectForm.value)
    ElMessage.success('回款已登记')
    showCollect.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

// ── 删除 ──
async function del(row: any) {
  await ElMessageBox.confirm(`确定删除单据 ${row.order_no}？`, '提示', { type: 'warning' })
  await request.delete(`/finance/recv-orders/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.kpi-card { text-align: center; }
.kpi-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.kpi-value { font-size: 20px; font-weight: 700; }
</style>
