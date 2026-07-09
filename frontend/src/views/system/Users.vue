<template>
  <div class="page-container">
    <div class="page-header">
      <h2>用户管理</h2>
      <el-button type="primary" @click="showCreate = true">新建用户</el-button>
    </div>
    <el-card>
      <div style="margin-bottom:12px">
        <el-input v-model="keyword" placeholder="搜索用户名/姓名" style="width:240px" clearable @change="loadUsers">
          <template #append><el-button icon="Search" @click="loadUsers" /></template>
        </el-input>
      </div>
      <el-table :data="users" stripe size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="real_name" label="姓名" width="100" />
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="store_code" label="关联门店" width="100" />
        <el-table-column label="岗位角色" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="r in row.roles || []" :key="r.code" size="small" style="margin-right:4px">{{ r.name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'">{{ row.status === 1 ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_admin" label="超管" width="60">
          <template #default="{ row }">{{ row.is_admin ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column prop="must_change_password" label="待改密" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.must_change_password" type="warning" size="small">待改密</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" show-overflow-tooltip />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="editUser(row)">编辑</el-button>
            <el-button size="small" type="warning" @click="setMustChange(row)" v-if="!row.must_change_password">强制改密</el-button>
            <el-button size="small" type="danger" @click="deleteUser(row.id)" v-if="!row.is_admin">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @change="loadUsers"
        style="margin-top:12px; justify-content:flex-end; display:flex"
      />
    </el-card>

    <el-dialog v-model="showCreate" title="新建用户" width="500px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="用户名" required><el-input v-model="createForm.username" /></el-form-item>
        <el-form-item label="密码" required><el-input v-model="createForm.password" type="password" /></el-form-item>
        <el-form-item label="真实姓名"><el-input v-model="createForm.real_name" /></el-form-item>
        <el-form-item label="手机号"><el-input v-model="createForm.phone" /></el-form-item>
        <el-form-item label="关联门店"><el-input v-model="createForm.store_code" placeholder="门店编码（店长/导购必填）" /></el-form-item>
        <el-form-item label="岗位角色" required>
          <el-select v-model="createForm.role_ids" multiple placeholder="选择岗位角色" style="width:100%">
            <el-option v-for="role in roles" :key="role.id" :label="`${role.name}（${scopeName(role.data_scope)}）`" :value="role.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="首次强制改密">
          <el-switch v-model="createForm.must_change_password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="submitCreate" :loading="submitting">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { systemApi } from '@/api/system'
import { ElMessage, ElMessageBox } from 'element-plus'

const users = ref<any[]>([])
const roles = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const showCreate = ref(false)
const submitting = ref(false)
const createForm = reactive({
  username: '', password: '', real_name: '', phone: '', store_code: '', role_ids: [] as number[], must_change_password: false
})

const loadUsers = async () => {
  const res = await systemApi.getUsers({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
  users.value = res.data.data?.items || []
  total.value = res.data.data?.total || 0
}

const loadRoles = async () => {
  const res = await systemApi.getRoles()
  roles.value = res.data.data || []
}

const scopeName = (s: string) => ({ all: '全公司', company: '公司级', dept: '部门级', store: '门店级', self: '个人级' } as any)[s] || s

const editUser = (user: any) => ElMessage.info('编辑功能开发中')

const setMustChange = async (user: any) => {
  await ElMessageBox.confirm(`确认强制 ${user.real_name || user.username} 下次登录改密？`, '提示')
  ElMessage.success('已标记（功能完善中）')
}

const deleteUser = async (id: number) => {
  await ElMessageBox.confirm('确认删除该用户？', '警告', { type: 'warning' })
  await systemApi.deleteUser(id)
  ElMessage.success('已删除')
  loadUsers()
}

const submitCreate = async () => {
  if (!createForm.username || !createForm.password) return ElMessage.warning('用户名和密码为必填')
  submitting.value = true
  try {
    await systemApi.createUser(createForm)
    ElMessage.success('用户创建成功')
    showCreate.value = false
    loadUsers()
  } finally {
    submitting.value = false
  }
}

onMounted(() => { loadUsers(); loadRoles() })
</script>

<style scoped>
.page-container { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { font-size: 18px; color: #333; }
</style>
