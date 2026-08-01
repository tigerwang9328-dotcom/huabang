<template>
  <div class="sys-page">
    <div class="page-header">
      <div><h2>岗位权限矩阵</h2><p>围绕 10 大一级模块配置各岗位可见模块、页面与数据范围</p></div>
      <el-button @click="load" :loading="loading">刷新</el-button>
    </div>
    <el-card>
      <el-table :data="roles" stripe size="small" v-loading="loading" row-key="code">
        <el-table-column prop="name" label="岗位" width="130" fixed />
        <el-table-column prop="code" label="角色编码" width="150" />
        <el-table-column prop="data_scope" label="数据范围" width="100">
          <template #default="{ row }"><el-tag>{{ scopeName(row.data_scope) }}</el-tag></template>
        </el-table-column>
        <el-table-column v-for="m in modules" :key="m.code" :label="m.name" min-width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="hasModule(row, m.code) ? 'success' : 'info'" size="small">
              {{ hasModule(row, m.code) ? moduleCount(row, m.code) + '项' : '无' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { systemApi } from '@/api/system'
const loading = ref(false)
const modules = ref<any[]>([])
const roles = ref<any[]>([])
const permissions = ref<any[]>([])
const permModule = computed(() => Object.fromEntries(permissions.value.map((p:any)=>[p.code,p.module])))
const load = async () => {
  loading.value = true
  try {
    const res = await systemApi.getModulePermissionMatrix()
    const data = res.data.data || {}
    modules.value = data.modules || []
    roles.value = data.roles || []
    permissions.value = data.permissions || []
  } finally { loading.value = false }
}
const moduleCount = (role:any, moduleCode:string) => (role.permissions || []).filter((c:string)=>permModule.value[c]===moduleCode).length
const hasModule = (role:any, moduleCode:string) => moduleCount(role,moduleCode)>0
const scopeName = (s:string) => ({all:'全公司',company:'公司级',dept:'部门级',store:'门店级',self:'个人级'} as any)[s] || s
onMounted(load)
</script>
<style scoped>
.sys-page{padding:0}.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.page-header h2{font-size:20px;margin:0 0 6px;color:#0f172a}.page-header p{margin:0;color:#64748b}
</style>
