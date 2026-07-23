<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">固定资产</h3>
      <el-button type="primary" @click="openAdd">+ 新增资产</el-button>
    </div>

    <!-- KPI -->
    <el-row :gutter="12" style="margin-bottom:16px">
      <el-col :span="6"><el-statistic title="资产总数" :value="rows.length" suffix="项" /></el-col>
      <el-col :span="6"><el-statistic title="原值合计" :value="totalOriginal" :precision="2" prefix="¥" /></el-col>
      <el-col :span="6"><el-statistic title="累计折旧" :value="totalDepreciation" :precision="2" prefix="¥" /></el-col>
      <el-col :span="6"><el-statistic title="净值合计" :value="totalNet" :precision="2" prefix="¥" /></el-col>
    </el-row>

    <el-table :data="rows" stripe border size="small" v-loading="loading">
      <el-table-column prop="asset_code" label="编码" width="110" />
      <el-table-column prop="asset_name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="category" label="分类" width="100" />
      <el-table-column prop="original_value" label="原值" width="120" align="right" :formatter="fmt" />
      <el-table-column prop="accumulated_depre" label="累计折旧" width="120" align="right" :formatter="fmt" />
      <el-table-column prop="net_value" label="净值" width="120" align="right">
        <template #default="{row}">
          <b>{{ fmt(row, null, row.net_value ?? ((row.original_value||0) - (row.accumulated_depre||0))) }}</b>
        </template>
      </el-table-column>
      <el-table-column prop="purchase_date" label="购入日期" width="110" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{row}">
          <el-tag size="small" :type="row.status==='in_use'||row.status==='active'?'success':'info'">
            {{ row.status==='in_use'||row.status==='active'?'使用中':'已处置' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{row}">
          <el-button link size="small" @click="editRow(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length===0" description="暂无固定资产" />

    <el-dialog v-model="showAdd" :title="editId?'编辑资产':'新增固定资产'" width="500px">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="资产名称"><el-input v-model="addForm.asset_name" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="addForm.category" style="width:100%">
            <el-option label="电子设备" value="电子设备" />
            <el-option label="运输工具" value="运输工具" />
            <el-option label="机器设备" value="机器设备" />
            <el-option label="办公家具" value="办公家具" />
            <el-option label="房屋建筑" value="房屋建筑" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="原值">
          <el-input-number v-model="addForm.original_value" :min="0" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="购入日期">
          <el-date-picker v-model="addForm.purchase_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="折旧年限">
          <el-input-number v-model="addForm.depre_years" :min="1" :max="50" style="width:100%" />
        </el-form-item>
        <el-form-item v-if="editId" label="状态">
          <el-select v-model="addForm.status" style="width:100%">
            <el-option label="使用中" value="in_use" />
            <el-option label="已处置" value="scrapped" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd=false">取消</el-button>
        <el-button type="primary" @click="saveAsset" :loading="saving">保存</el-button>
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

const defaultForm = () => ({ asset_code: '', asset_name: '', category: '电子设备', original_value: 0, purchase_date: '', depre_years: 5, status: 'in_use' })
const addForm = ref(defaultForm())
const fmt = (_r: any, _c: any, v: number) => v != null ? '¥' + Number(v).toLocaleString() : '—'
const totalOriginal = computed(() => rows.value.reduce((s, r) => s + (r.original_value || 0), 0))
const totalDepreciation = computed(() => rows.value.reduce((s, r) => s + (r.accumulated_depre || 0), 0))
const totalNet = computed(() => totalOriginal.value - totalDepreciation.value)

function openAdd() { editId.value = null; addForm.value = defaultForm(); showAdd.value = true }
function editRow(row: any) { editId.value = row.id; addForm.value = { ...defaultForm(), ...row, depre_years: row.depre_years || row.useful_life_years || 5 }; showAdd.value = true }

async function load() {
  loading.value = true
  try {
    const d: any = await request.get(`/finance/assets?book_id=${finStore.bookId}`)
    rows.value = d.rows || []
  } finally { loading.value = false }
}

async function saveAsset() {
  if (!addForm.value.asset_name) { ElMessage.warning("请填写资产名称"); return }
  saving.value = true
  try {
    const payload = { ...addForm.value, depre_years: addForm.value.depre_years || 5 }
    if (!payload.asset_code) delete payload.asset_code
    if (editId.value) {
      await request.put(`/finance/assets/${editId.value}?book_id=${finStore.bookId}`, payload)
    } else {
      await request.post(`/finance/assets?book_id=${finStore.bookId}`, payload)
    }
    ElMessage.success("已保存")
    showAdd.value = false
    load()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    ElMessage.error(Array.isArray(detail) ? detail.map((i: any) => i.msg).join("；") : detail || "保存失败")
  }
  finally { saving.value = false }
}

onMounted(() => { finStore.loadBooks(); load() })
</script>
