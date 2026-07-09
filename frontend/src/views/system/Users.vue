<template>
  <div class="system-page">
    <div class="page-head">
      <div>
        <h1>用户管理</h1>
        <p>管理员工账号、岗位角色、门店绑定、账号状态和登录安全。</p>
      </div>
      <el-button type="primary" @click="openCreate">新建用户</el-button>
    </div>

    <div class="card toolbar">
      <el-input v-model="filters.keyword" placeholder="用户名/姓名/手机号" style="width:220px" clearable @keyup.enter="loadUsers" />
      <el-select v-model="filters.role_id" placeholder="角色" clearable style="width:180px">
        <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" clearable style="width:130px">
        <el-option label="启用" :value="1" />
        <el-option label="禁用" :value="0" />
      </el-select>
      <el-input v-model="filters.store_code" placeholder="门店编码" style="width:150px" clearable />
      <el-button type="primary" @click="loadUsers">查询</el-button>
      <el-button @click="resetFilters">重置</el-button>
    </div>

    <div class="card">
      <el-table :data="users" v-loading="loading" style="width:100%">
        <el-table-column label="用户" min-width="160">
          <template #default="{ row }">
            <b>{{ row.real_name || row.username }}</b>
            <div class="muted">{{ row.username }} <span v-if="row.employee_no">· {{ row.employee_no }}</span></div>
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column label="岗位角色" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="r in row.roles || []" :key="r.code" size="small" style="margin:2px">{{ r.name }}</el-tag>
            <span v-if="!(row.roles || []).length" class="danger">无角色</span>
          </template>
        </el-table-column>
        <el-table-column label="数据绑定" min-width="160">
          <template #default="{ row }">
            <div>主门店：{{ row.store_code || '-' }}</div>
            <div class="muted">部门：{{ row.dept_id || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="风险" width="140">
          <template #default="{ row }">
            <el-tag v-if="row.data_risk" type="danger">未绑定门店</el-tag>
            <el-tag v-else type="success">正常</el-tag>
            <el-tag v-if="row.locked_until" type="warning" style="margin-left:4px">已锁定</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'">{{ row.status === 1 ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="登录" min-width="190">
          <template #default="{ row }">
            <div>{{ row.last_login_at || '-' }}</div>
            <div class="muted">IP：{{ row.last_login_ip || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="260">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status === 1 && !row.is_admin" link type="warning" @click="disable(row)">停用</el-button>
            <el-button v-if="row.status !== 1" link type="success" @click="enable(row)">启用</el-button>
            <el-button link @click="resetPassword(row)">重置密码</el-button>
            <el-button v-if="!row.is_admin" link type="danger" @click="deleteUser(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination style="margin-top:16px" layout="total, prev, pager, next" :total="total" v-model:current-page="filters.page" :page-size="filters.page_size" @current-change="loadUsers" />
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '新建用户'" width="720px">
      <el-form :model="form" label-width="110px">
        <div class="form-grid">
          <el-form-item label="用户名" required><el-input v-model="form.username" :disabled="editing" /></el-form-item>
          <el-form-item :label="editing ? '新密码' : '初始密码'" :required="!editing"><el-input v-model="form.password" type="password" show-password :placeholder="editing ? '不修改请留空' : '请输入初始密码'" /></el-form-item>
          <el-form-item label="真实姓名"><el-input v-model="form.real_name" /></el-form-item>
          <el-form-item label="手机号"><el-input v-model="form.phone" /></el-form-item>
          <el-form-item label="员工编号"><el-input v-model="form.employee_no" /></el-form-item>
          <el-form-item label="岗位名称"><el-input v-model="form.position" /></el-form-item>
          <el-form-item label="部门"><el-select v-model="form.dept_id" clearable filterable style="width:100%"><el-option v-for="d in departments" :key="d.id" :label="d.name" :value="d.id" /></el-select></el-form-item>
          <el-form-item label="主门店"><el-select v-model="form.store_code" filterable allow-create clearable style="width:100%"><el-option v-for="s in storeOptions" :key="s" :label="s" :value="s" /></el-select></el-form-item>
        </div>
        <el-form-item label="可管理门店"><el-select v-model="form.store_codes" multiple filterable allow-create style="width:100%"><el-option v-for="s in storeOptions" :key="s" :label="s" :value="s" /></el-select></el-form-item>
        <el-form-item label="岗位角色" required><el-select v-model="form.role_ids" multiple filterable style="width:100%"><el-option v-for="r in roles" :key="r.id" :label="`${r.name}（${scopeName(r.data_scope)}）`" :value="r.id" /></el-select></el-form-item>
        <el-form-item label="状态" v-if="editing"><el-switch v-model="form.status" :active-value="1" :inactive-value="0" /></el-form-item>
        <el-form-item label="首次强制改密"><el-switch v-model="form.must_change_password" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { systemApi } from '@/api/system'

const users = ref<any[]>([])
const roles = ref<any[]>([])
const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const editing = ref(false)
const currentId = ref<number | null>(null)
const total = ref(0)
const filters = reactive<any>({ page: 1, page_size: 20, keyword: '', role_id: undefined, status: undefined, store_code: '' })
const form = reactive<any>({ username: '', password: '', real_name: '', phone: '', employee_no: '', position: '', dept_id: null, store_code: '', store_codes: [], role_ids: [], status: 1, must_change_password: false })
const storeOptions = ref<string[]>([])
const departments = ref<any[]>([])

function scopeName(s: string) { return ({ all: '全部', company: '公司', dept: '部门', store: '门店', self: '个人' } as any)[s] || s }
function resetForm() { Object.assign(form, { username: '', password: '', real_name: '', phone: '', employee_no: '', position: '', dept_id: null, store_code: '', store_codes: [], role_ids: [], status: 1, must_change_password: false }) }
function resetFilters() { Object.assign(filters, { page: 1, keyword: '', role_id: undefined, status: undefined, store_code: '' }); loadUsers() }
async function loadUsers() { loading.value = true; try { const res = await systemApi.getUsers(filters); users.value = res.data.data?.items || []; total.value = res.data.data?.total || 0 } finally { loading.value = false } }
async function loadRoles() { const res = await systemApi.getRoles({ show_legacy: false }); roles.value = res.data.data || [] }
async function loadOrgOptions() { const res = await systemApi.getOrgOptions(); storeOptions.value = res.data.data?.inventories || []; departments.value = res.data.data?.departments || [] }
function openCreate() { editing.value = false; currentId.value = null; resetForm(); dialogVisible.value = true }
function openEdit(row: any) { editing.value = true; currentId.value = row.id; resetForm(); Object.assign(form, { ...row, password: '', role_ids: row.role_ids || [], store_codes: row.store_codes || [] }); dialogVisible.value = true }
async function saveUser() { if (!form.username || (!editing.value && !form.password)) return ElMessage.warning('用户名和密码为必填'); submitting.value = true; try { const payload = { ...form }; if (editing.value && !payload.password) delete payload.password; if (editing.value && currentId.value) await systemApi.updateUser(currentId.value, payload); else await systemApi.createUser(payload); ElMessage.success('用户已保存'); dialogVisible.value = false; loadUsers() } finally { submitting.value = false } }
async function enable(row: any) { await systemApi.enableUser(row.id); ElMessage.success('用户已启用'); loadUsers() }
async function disable(row: any) { await ElMessageBox.confirm(`确认停用 ${row.real_name || row.username}？`, '停用用户', { type: 'warning' }); await systemApi.disableUser(row.id); ElMessage.success('用户已停用'); loadUsers() }
async function resetPassword(row: any) { const { value } = await ElMessageBox.prompt('可输入新密码；留空则重置为系统默认 Hb@123456', '重置密码', { inputType: 'password', inputPlaceholder: '留空使用默认密码' }); const res = await systemApi.resetUserPassword(row.id, { password: value || undefined }); ElMessage.success(res.data.data?.default_password ? `已重置，默认密码：${res.data.data.default_password}` : '密码已重置'); loadUsers() }
async function deleteUser(row: any) { await ElMessageBox.confirm(`确认删除 ${row.real_name || row.username}？`, '删除用户', { type: 'warning' }); await systemApi.deleteUser(row.id); ElMessage.success('用户已删除'); loadUsers() }
onMounted(() => { loadRoles(); loadOrgOptions(); loadUsers() })
</script>

<style scoped>
.system-page{padding:24px;background:#f6f8fb;min-height:100%}.page-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px}.page-head h1{margin:0;color:#0f172a;font-size:26px}.page-head p{margin:8px 0 0;color:#64748b}.card{background:#fff;border:1px solid #e5eaf2;border-radius:14px;padding:18px;margin-bottom:16px;box-shadow:0 8px 24px rgba(15,23,42,.04)}.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.muted{color:#94a3b8;font-size:12px}.danger{color:#ef4444}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}@media(max-width:900px){.form-grid{grid-template-columns:1fr}}
</style>
