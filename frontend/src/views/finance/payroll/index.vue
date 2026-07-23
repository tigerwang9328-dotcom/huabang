<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">工资管理</h3>
      <div style="display:flex;gap:8px">
        <el-date-picker v-model="period" type="month" value-format="YYYY-MM" placeholder="选择月份" @change="load" style="width:150px" />
        <el-button type="primary" @click="openAdd">+ 录入工资</el-button>
      </div>
    </div>

    <!-- 汇总卡片 -->
    <el-row :gutter="12" style="margin-bottom:16px">
      <el-col :span="5"><el-statistic title="应发合计" :value="totalGross" :precision="2" prefix="¥" /></el-col>
      <el-col :span="5"><el-statistic title="社保公积金" :value="totalSocial" :precision="2" prefix="¥" /></el-col>
      <el-col :span="5"><el-statistic title="个人所得税" :value="totalTax" :precision="2" prefix="¥" /></el-col>
      <el-col :span="5"><el-statistic title="实发合计" :value="totalNet" :precision="2" prefix="¥" /></el-col>
      <el-col :span="4"><el-statistic title="人数" :value="rows.length" suffix="人" /></el-col>
    </el-row>

    <el-table :data="rows" stripe border size="small" v-loading="loading">
      <el-table-column prop="employee_name" label="姓名" width="100" />
      <el-table-column prop="department" label="部门" width="100" />
      <el-table-column prop="base_salary" label="基本工资" width="110" align="right" :formatter="fmt" />
      <el-table-column prop="bonus" label="奖金" width="100" align="right" :formatter="fmt" />
      <el-table-column prop="gross_pay" label="应发合计" width="110" align="right">
        <template #default="{row}">
          <b>¥{{ ((row.base_salary||0)+(row.bonus||0)).toLocaleString() }}</b>
        </template>
      </el-table-column>
      <el-table-column prop="social_insurance" label="社保" width="100" align="right" :formatter="fmt" />
      <el-table-column prop="deduction" label="其他扣款" width="100" align="right" :formatter="fmt" />
      <el-table-column prop="tax" label="个税" width="100" align="right" :formatter="fmt" />
      <el-table-column prop="net_pay" label="实发" width="110" align="right">
        <template #default="{row}">
          <b style="color:#409eff">¥{{ (row.net_pay||0).toLocaleString() }}</b>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="80">
        <template #default="{row}">
          <el-tag size="small" :type="row.status==='paid'?'success':''">{{ row.status==='paid'?'已发':'待发' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{row}">
          <el-button link size="small" type="primary" @click="editRow(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length===0" description="暂无工资数据" />

    <el-dialog v-model="showAdd" :title="editId?'编辑工资':'录入工资'" width="520px">
      <el-form :model="addForm" label-width="90px">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="姓名"><el-input v-model="addForm.employee_name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="部门"><el-input v-model="addForm.department" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="基本工资">
              <el-input-number v-model="addForm.base_salary" :min="0" :precision="2" style="width:100%" @change="calcNet" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="奖金">
              <el-input-number v-model="addForm.bonus" :min="0" :precision="2" style="width:100%" @change="calcNet" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="社保公积金">
              <el-input-number v-model="addForm.social_insurance" :min="0" :precision="2" style="width:100%" @change="calcNet" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="其他扣款">
              <el-input-number v-model="addForm.deduction" :min="0" :precision="2" style="width:100%" @change="calcNet" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="个人所得税">
              <el-input-number v-model="addForm.tax" :min="0" :precision="2" style="width:100%" @change="calcNet" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="实发工资">
              <el-input-number v-model="addForm.net_pay" :min="0" :precision="2" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="发放状态">
          <el-radio-group v-model="addForm.status">
            <el-radio value="pending">待发</el-radio>
            <el-radio value="paid">已发</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd=false">取消</el-button>
        <el-button type="primary" @click="savePayroll" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { ElMessage } from "element-plus"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"
import dayjs from "dayjs"

const finStore = useFinanceStore()
const loading = ref(false), saving = ref(false), showAdd = ref(false)
const rows = ref<any[]>([])
const editId = ref<number | null>(null)
const period = ref(dayjs().format("YYYY-MM"))

const defaultForm = () => ({
  employee_name: '', department: '', base_salary: 0, bonus: 0,
  social_insurance: 0, deduction: 0, tax: 0, net_pay: 0, status: 'pending'
})
const addForm = ref(defaultForm())

const fmt = (_r: any, _c: any, v: number) => v != null ? '¥' + Number(v).toLocaleString() : '—'
const totalGross = computed(() => rows.value.reduce((s, r) => s + (r.base_salary || 0) + (r.bonus || 0), 0))
const totalSocial = computed(() => rows.value.reduce((s, r) => s + (r.social_insurance || 0), 0))
const totalTax = computed(() => rows.value.reduce((s, r) => s + (r.tax || 0), 0))
const totalNet = computed(() => rows.value.reduce((s, r) => s + (r.net_pay || 0), 0))

function calcNet() {
  const gross = (addForm.value.base_salary || 0) + (addForm.value.bonus || 0)
  addForm.value.net_pay = Math.max(0,
    gross - (addForm.value.social_insurance || 0) - (addForm.value.deduction || 0) - (addForm.value.tax || 0)
  )
}

function openAdd() {
  editId.value = null
  addForm.value = defaultForm()
  showAdd.value = true
}

function editRow(row: any) {
  editId.value = row.id
  addForm.value = { ...row }
  showAdd.value = true
}

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/payroll?book_id=${finStore.bookId}&period=${period.value}`)
    rows.value = d.rows || []
  } finally {
    loading.value = false
  }
}

async function savePayroll() {
  saving.value = true
  try {
    if (editId.value) {
      await request.put(`/finance/payroll/${editId.value}?book_id=${finStore.bookId}`, addForm.value)
    } else {
      await request.post(`/finance/payroll?book_id=${finStore.bookId}&period=${period.value}`, addForm.value)
    }
    ElMessage.success("已保存")
    showAdd.value = false
    load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败")
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  finStore.loadBooks()
  if (finStore.currentPeriod) period.value = finStore.currentPeriod
  load()
})
</script>
