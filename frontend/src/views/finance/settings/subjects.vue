<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">科目管理</h3>
      <div style="display:flex;gap:8px">
        <el-select v-model="typeFilter" style="width:100px" @change="filterRows">
          <el-option label="全部" value="" />
          <el-option label="资产" value="asset" />
          <el-option label="负债" value="liability" />
          <el-option label="权益" value="equity" />
          <el-option label="收入" value="income" />
          <el-option label="费用" value="expense" />
        </el-select>
        <el-button type="primary" @click="openAdd">+ 新增科目</el-button>
      </div>
    </div>

    <el-table :data="filteredRows" stripe border size="small" v-loading="loading">
      <el-table-column prop="account_code" label="科目编码" width="140" />
      <el-table-column prop="account_name" label="科目名称" min-width="160" />
      <el-table-column prop="account_type" label="类别" width="90">
        <template #default="{row}">
          <el-tag size="small" :type="typeColor(row.account_type)">
            {{ typeLabel(row.account_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="direction" label="余额方向" width="90" align="center">
        <template #default="{row}">{{ row.direction==='debit'?'借':'贷' }}</template>
      </el-table-column>
      <el-table-column prop="level" label="级次" width="60" align="center" />
      <el-table-column prop="is_active" label="状态" width="80">
        <template #default="{row}">
          <el-tag size="small" :type="row.is_active?'success':'info'">{{ row.is_active?'启用':'停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{row}">
          <el-button size="small" link @click="editRow(row)">编辑</el-button>
          <el-button size="small" link :type="row.is_active?'warning':'success'" @click="toggle(row)">
            {{ row.is_active?'停用':'启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && filteredRows.length===0" description="暂无科目" />

    <el-dialog v-model="showAdd" :title="editId?'编辑科目':'新增科目'" width="480px">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="科目编码"><el-input v-model="addForm.account_code" /></el-form-item>
        <el-form-item label="科目名称"><el-input v-model="addForm.account_name" /></el-form-item>
        <el-form-item label="类别">
          <el-select v-model="addForm.account_type" style="width:100%">
            <el-option label="资产" value="asset" />
            <el-option label="负债" value="liability" />
            <el-option label="权益" value="equity" />
            <el-option label="收入" value="income" />
            <el-option label="费用" value="expense" />
          </el-select>
        </el-form-item>
        <el-form-item label="余额方向">
          <el-radio-group v-model="addForm.direction">
            <el-radio value="debit">借方</el-radio>
            <el-radio value="credit">贷方</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd=false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { ElMessage } from "element-plus"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"

const finStore = useFinanceStore()
const loading = ref(false), saving = ref(false), showAdd = ref(false)
const rows = ref<any[]>([])
const editId = ref<number | null>(null)
const typeFilter = ref("")

const defaultForm = () => ({ account_code: '', account_name: '', account_type: 'asset', direction: 'debit' })
const addForm = ref(defaultForm())

const typeLabel = (t: string) => ({ asset:'资产', liability:'负债', equity:'权益', income:'收入', expense:'费用' }[t] || t)
const typeColor = (t: string) => ({ asset:'', liability:'warning', equity:'success', income:'success', expense:'danger' }[t] || '')
const filteredRows = computed(() => typeFilter.value ? rows.value.filter(r => r.account_type === typeFilter.value) : rows.value)

function openAdd() { editId.value = null; addForm.value = defaultForm(); showAdd.value = true }
function editRow(row: any) { editId.value = row.id; addForm.value = { ...row }; showAdd.value = true }

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/accounts?book_id=${finStore.bookId}`)
    rows.value = d.accounts || []
  } finally { loading.value = false }
}

async function save() {
  saving.value = true
  try {
    if (editId.value) {
      await request.put(`/finance/accounts/${editId.value}?book_id=${finStore.bookId}`, addForm.value)
    } else {
      await request.post(`/finance/accounts?book_id=${finStore.bookId}`, addForm.value)
    }
    ElMessage.success("已保存"); showAdd.value = false; editId.value = null; load()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败") }
  finally { saving.value = false }
}

async function toggle(row: any) {
  await request.put(`/finance/accounts/${row.id}/toggle?book_id=${finStore.bookId}`)
  ElMessage.success("操作成功"); load()
}

onMounted(() => { finStore.loadBooks(); load() })
</script>
