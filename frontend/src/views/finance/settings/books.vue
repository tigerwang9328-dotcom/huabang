<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <h3 style="margin:0">账套管理</h3>
        <p style="margin:4px 0 0;color:#909399;font-size:12px">每个独立核算主体一个账套，数据完全隔离</p>
      </div>
      <el-button type="primary" @click="openCreate">+ 新建账套</el-button>
    </div>

    <el-table :data="rows" stripe border size="small" v-loading="loading">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="book_code" label="账套编码" width="120" />
      <el-table-column prop="book_name" label="账套名称" width="180" />
      <el-table-column prop="company_name" label="公司名称" width="180" />
      <el-table-column prop="accounting_standard" label="会计准则" width="140" />
      <el-table-column prop="current_period" label="当前期间" width="100" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" link @click="switchBook(row)">切换</el-button>
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="warning" @click="initSubjects(row)">补全科目</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length === 0" description="暂无账套，请创建第一个账套" />

    <!-- 新建账套向导 -->
    <el-dialog v-model="showCreate" title="新建账套" width="520px" :close-on-click-modal="false">
      <el-steps :active="step" finish-status="success" style="margin-bottom:24px">
        <el-step title="基本信息" />
        <el-step title="会计设置" />
        <el-step title="完成" />
      </el-steps>

      <!-- Step 0: 基本信息 -->
      <div v-if="step === 0">
        <el-form :model="form" label-width="110px">
          <el-form-item label="账套编码" required>
            <el-input v-model="form.book_code" placeholder="如 DEFAULT / BRANCH_SZ（唯一）" />
          </el-form-item>
          <el-form-item label="账套名称" required>
            <el-input v-model="form.book_name" placeholder="如 牧马人主账套" />
          </el-form-item>
          <el-form-item label="公司名称">
            <el-input v-model="form.company_name" placeholder="牧马人服饰" />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 1: 会计设置 -->
      <div v-if="step === 1">
        <el-form :model="form" label-width="110px">
          <el-form-item label="会计准则">
            <el-select v-model="form.accounting_standard" style="width:100%">
              <el-option value="小企业会计准则" label="小企业会计准则" />
              <el-option value="企业会计准则" label="企业会计准则" />
            </el-select>
          </el-form-item>
          <el-form-item label="启用日期" required>
            <el-date-picker v-model="form.start_date" type="month" format="YYYY-MM"
              value-format="YYYY-MM-DD" placeholder="选择账套启用月份" style="width:100%" />
          </el-form-item>
          <el-form-item label="安全现金线">
            <el-input-number v-model="form.safety_cash_line" :min="0" :step="10000" style="width:100%" />
            <div style="color:#909399;font-size:12px;margin-top:4px">低于此金额时触发预警（元）</div>
          </el-form-item>
          <el-alert type="info" :closable="false" style="margin-top:8px">
            <div>创建后将自动：</div>
            <div>✓ 初始化当年所有会计期间</div>
            <div>✓ 导入49个标准一级科目（小企业会计准则）</div>
            <div>✓ 创建6类辅助核算（客户/供应商/部门/项目/店铺/员工）</div>
          </el-alert>
        </el-form>
      </div>

      <!-- Step 2: 完成 -->
      <div v-if="step === 2" style="text-align:center;padding:24px 0">
        <el-icon style="font-size:64px;color:#67c23a"><CircleCheck /></el-icon>
        <div style="font-size:18px;font-weight:bold;margin-top:12px">账套创建成功！</div>
        <div style="color:#606266;margin-top:8px">
          {{ form.book_name }} 已就绪，共初始化 {{ createdResult.subjects_initialized || 0 }} 个科目
        </div>
        <el-button type="primary" style="margin-top:16px" @click="showCreate = false; load()">确定</el-button>
      </div>

      <template #footer v-if="step < 2">
        <el-button @click="step > 0 ? step-- : (showCreate = false)">
          {{ step === 0 ? '取消' : '上一步' }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="nextStep">
          {{ step === 1 ? '创建账套' : '下一步' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑账套 -->
    <el-dialog v-model="showEdit" title="编辑账套" width="480px">
      <el-form :model="editForm" label-width="110px">
        <el-form-item label="账套名称"><el-input v-model="editForm.book_name" /></el-form-item>
        <el-form-item label="公司名称"><el-input v-model="editForm.company_name" /></el-form-item>
        <el-form-item label="当前期间">
          <el-date-picker v-model="editForm.current_period" type="month" format="YYYY-MM"
            value-format="YYYY-MM" placeholder="切换当前期间" style="width:100%" />
        </el-form-item>
        <el-form-item label="安全现金线">
          <el-input-number v-model="editForm.safety_cash_line" :min="0" :step="10000" style="width:100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width:100%">
            <el-option value="active" label="启用" />
            <el-option value="closed" label="停用" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck } from '@element-plus/icons-vue'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const loading = ref(false)
const saving = ref(false)
const rows = ref<any[]>([])

// ── 新建向导 ──
const showCreate = ref(false)
const step = ref(0)
const form = ref({
  book_code: '',
  book_name: '',
  company_name: '牧马人服饰',
  accounting_standard: '小企业会计准则',
  start_date: '',
  safety_cash_line: 300000,
})
const createdResult = ref<any>({})

function openCreate() {
  step.value = 0
  form.value = {
    book_code: '',
    book_name: '',
    company_name: '牧马人服饰',
    accounting_standard: '小企业会计准则',
    start_date: '',
    safety_cash_line: 300000,
  }
  showCreate.value = true
}

async function nextStep() {
  if (step.value === 0) {
    if (!form.value.book_code || !form.value.book_name) {
      ElMessage.warning('账套编码和名称不能为空')
      return
    }
    step.value = 1
  } else if (step.value === 1) {
    if (!form.value.start_date) {
      ElMessage.warning('请选择启用日期')
      return
    }
    saving.value = true
    try {
      const res: any = await request.post('/finance/books', form.value)
      createdResult.value = res
      step.value = 2
      await finStore.loadBooks()
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '创建失败')
    } finally {
      saving.value = false
    }
  }
}

// ── 编辑 ──
const showEdit = ref(false)
const editId = ref<number | null>(null)
const editForm = ref<any>({})

function openEdit(row: any) {
  editId.value = row.id
  editForm.value = {
    book_name: row.book_name,
    company_name: row.company_name,
    current_period: row.current_period,
    safety_cash_line: row.safety_cash_line,
    status: row.status,
  }
  showEdit.value = true
}

async function saveEdit() {
  saving.value = true
  try {
    await request.put(`/finance/books/${editId.value}`, editForm.value)
    ElMessage.success('已保存')
    showEdit.value = false
    await load()
    await finStore.loadBooks()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// ── 切换账套 ──
function switchBook(row: any) {
  finStore.switchBook(row.id)
  ElMessage.success(`已切换到账套：${row.book_name}`)
}

// ── 补全科目 ──
async function initSubjects(row: any) {
  try {
    const res: any = await request.post(`/finance/books/${row.id}/init-subjects`)
    ElMessage.success(`已补充 ${res.subjects_added} 个缺失科目`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

// ── 加载 ──
async function load() {
  loading.value = true
  try {
    const d: any = await request.get('/finance/books')
    rows.value = d.books || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
