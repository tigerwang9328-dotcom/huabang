<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证管理</p>
        <h2>凭证模板</h2>
        <p>常用凭证模板管理与调用;会话内维护,刷新清空。</p>
      </div>
      <div class="heading-actions">
        <el-button type="primary" @click="openCreate">新增模板</el-button>
      </div>
    </div>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="完整数据接口待后端补,本会话数据刷新后清空"
    />

    <el-table :data="templates" empty-text="暂无凭证模板" stripe>
      <el-table-column prop="template_name" label="模板名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="voucher_type" label="凭证字" width="100" />
      <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-popconfirm
            title="确定删除该模板吗?"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="removeRow(scope.row)"
          >
            <template #reference>
              <el-button size="small" link type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增模板" width="520px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="模板名称" prop="template_name">
          <el-input v-model="form.template_name" placeholder="请输入模板名称" maxlength="50" show-word-limit />
        </el-form-item>
        <el-form-item label="凭证字" prop="voucher_type">
          <el-select v-model="form.voucher_type" placeholder="请选择凭证字" style="width: 100%">
            <el-option label="记" value="记" />
            <el-option label="转" value="转" />
            <el-option label="收" value="收" />
            <el-option label="付" value="付" />
          </el-select>
        </el-form-item>
        <el-form-item label="摘要" prop="summary">
          <el-input v-model="form.summary" type="textarea" :rows="3" placeholder="请输入摘要" maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";

interface VoucherTemplate {
  id: number;
  template_name: string;
  voucher_type: string;
  summary: string;
  created_at: string;
}

const templates = ref<VoucherTemplate[]>([]);

const dialogVisible = ref(false);
const formRef = ref<FormInstance>();

const defaultForm = () => ({
  template_name: "",
  voucher_type: "记",
  summary: "",
});

const form = reactive(defaultForm());

const rules: FormRules = {
  template_name: [{ required: true, message: "请输入模板名称", trigger: "blur" }],
  voucher_type: [{ required: true, message: "请选择凭证字", trigger: "change" }],
};

const resetForm = () => {
  Object.assign(form, defaultForm());
  formRef.value?.clearValidate();
};

const openCreate = () => {
  resetForm();
  dialogVisible.value = true;
};

const submit = async () => {
  if (!formRef.value) return;
  await formRef.value.validate((valid) => {
    if (!valid) return;
    const now = new Date();
    const row: VoucherTemplate = {
      id: Date.now(),
      template_name: form.template_name.trim(),
      voucher_type: form.voucher_type,
      summary: form.summary.trim(),
      created_at: now.toLocaleString("zh-CN", { hour12: false }),
    };
    templates.value.push(row);
    ElMessage.success("模板已新增");
    dialogVisible.value = false;
  });
};

const removeRow = (row: VoucherTemplate) => {
  templates.value = templates.value.filter((item) => item.id !== row.id);
  ElMessage.success("模板已删除");
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .heading { flex-direction: column; } }
</style>
