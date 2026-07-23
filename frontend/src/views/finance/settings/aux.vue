<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">辅助核算</h3>
      <div style="display:flex;gap:8px">
        <el-select v-model="typeFilter" style="width:100px" @change="filterRows">
          <el-option label="全部" value="" />
          <el-option label="客户" value="customer" />
          <el-option label="供应商" value="supplier" />
          <el-option label="部门" value="department" />
          <el-option label="项目" value="project" />
          <el-option label="店铺" value="store" />
          <el-option label="员工" value="employee" />
        </el-select>
        <el-button type="primary" @click="openAdd">+ 新增核算项</el-button>
      </div>
    </div>
    <el-table :data="filteredRows" stripe border size="small" v-loading="loading">
      <el-table-column prop="aux_type" label="类别" width="90">
        <template #default="{row}">{{ typeLabel(row.aux_type) }}</template>
      </el-table-column>
      <el-table-column prop="aux_code" label="编码" width="120" />
      <el-table-column prop="aux_name" label="名称" min-width="180" />
      <el-table-column prop="is_active" label="状态" width="80">
        <template #default="{row}">
          <el-tag size="small" :type="row.is_active?'success':'info'">{{ row.is_active?'启用':'停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{row}">
          <el-button size="small" link @click="editRow(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && filteredRows.length===0" description="暂无数据" />

    <el-dialog v-model="showAdd" :title="editId?'编辑核算项':'新增核算项'" width="460px">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="核算类别">
          <el-select v-model="addForm.aux_type" style="width:100%">
            <el-option label="客户" value="customer" />
            <el-option label="供应商" value="supplier" />
            <el-option label="部门" value="department" />
            <el-option label="项目" value="project" />
            <el-option label="店铺" value="store" />
            <el-option label="员工" value="employee" />
          </el-select>
        </el-form-item>
        <el-form-item label="编码"><el-input v-model="addForm.aux_code" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="addForm.aux_name" /></el-form-item>
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
import { ElMessage, ElMessageBox } from "element-plus"
import request from "@/api/request"
import { useFinanceStore } from "@/stores/finance"

const finStore = useFinanceStore()
const loading = ref(false), saving = ref(false), showAdd = ref(false)
const rows = ref<any[]>([])
const editId = ref<number | null>(null)
const typeFilter = ref("")

const defaultForm = () => ({ aux_type: 'customer', aux_code: '', aux_name: '' })
const addForm = ref(defaultForm())

const typeLabel = (t: string) => ({ customer:'客户', supplier:'供应商', department:'部门', project:'项目', store:'店铺', employee:'员工' }[t] || t)
const filteredRows = computed(() => typeFilter.value ? rows.value.filter(r => r.aux_type === typeFilter.value) : rows.value)
function filterRows() {}

function openAdd() { editId.value = null; addForm.value = defaultForm(); showAdd.value = true }
function editRow(row: any) { editId.value = row.id; addForm.value = { aux_type: row.aux_type, aux_code: row.aux_code, aux_name: row.aux_name }; showAdd.value = true }

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/aux-items?book_id=${finStore.bookId}`)
    rows.value = d.rows || []
  } finally { loading.value = false }
}

async function save() {
  saving.value = true
  try {
    if (editId.value) {
      await request.put(`/finance/aux-items/${editId.value}?book_id=${finStore.bookId}`, addForm.value)
    } else {
      await request.post(`/finance/aux-items?book_id=${finStore.bookId}`, addForm.value)
    }
    ElMessage.success("已保存"); showAdd.value = false; editId.value = null; load()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败") }
  finally { saving.value = false }
}

async function del(row: any) {
  await ElMessageBox.confirm("确定删除？", "提示", { type: "warning" })
  await request.delete(`/finance/aux-items/${row.id}?book_id=${finStore.bookId}`)
  ElMessage.success("已删除"); load()
}

onMounted(async () => { await finStore.loadBooks(); load() })
</script>
