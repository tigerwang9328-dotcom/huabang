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
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{row}">
            <el-tag :type="row.status===1?\"success\":\"danger\">{{ row.status===1?"启用":"禁用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_admin" label="超管" width="60">
          <template #default="{row}">{{ row.is_admin?"是":"否" }}</template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" show-overflow-tooltip />
        <el-table-column label="操作" width="120">
          <template #default="{row}">
            <el-button size="small" @click="editUser(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteUser(row.id)" v-if="!row.is_admin">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        layout="total, prev, pager, next" @change="loadUsers" style="margin-top:12px; justify-content:flex-end; display:flex" />
    </el-card>

    <el-dialog v-model="showCreate" title="新建用户" width="500px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="用户名" required><el-input v-model="createForm.username" /></el-form-item>
        <el-form-item label="密码" required><el-input v-model="createForm.password" type="password" /></el-form-item>
        <el-form-item label="真实姓名"><el-input v-model="createForm.real_name" /></el-form-item>
        <el-form-item label="手机号"><el-input v-model="createForm.phone" /></el-form-item>
        <el-form-item label="关联门店"><el-input v-model="createForm.store_code" placeholder="门店编码（店长/导购必填）" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate=false">取消</el-button>
        <el-button type="primary" @click="submitCreate" :loading="submitting">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { systemApi } from "@/api/system";
import { ElMessage, ElMessageBox } from "element-plus";
const users = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const showCreate = ref(false);
const submitting = ref(false);
const createForm = reactive({ username: "", password: "", real_name: "", phone: "", store_code: "" });
const loadUsers = async () => {
  const res = await systemApi.getUsers({ page: page.value, page_size: pageSize.value, keyword: keyword.value });
  users.value = res.data.data?.items || [];
  total.value = res.data.data?.total || 0;
};
const editUser = (user: any) => ElMessage.info("编辑功能开发中");
const deleteUser = async (id: number) => {
  await ElMessageBox.confirm("确认删除该用户？", "警告", { type: "warning" });
  await systemApi.deleteUser(id);
  ElMessage.success("已删除");
  loadUsers();
};
const submitCreate = async () => {
  if (!createForm.username || !createForm.password) return ElMessage.warning("用户名和密码为必填");
  submitting.value = true;
  try {
    await systemApi.createUser(createForm);
    ElMessage.success("用户创建成功");
    showCreate.value = false;
    loadUsers();
  } finally { submitting.value = false; }
};
onMounted(loadUsers);
</script>
<style scoped>
.page-container { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { font-size: 18px; color: #333; }
</style>
