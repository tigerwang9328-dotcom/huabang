<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证管理</p>
        <h2>凭证模板</h2>
        <p>常用凭证模板管理与调用;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button :disabled="isReadonly || !bookId" type="primary"  @click="openCreate">新增模板</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="templates" empty-text="暂无凭证模板" stripe>
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
              <el-button :disabled="isReadonly" size="small" link type="danger" :loading="actingId === scope.row.id">删除</el-button>
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
        <el-button :disabled="isReadonly" type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { storeToRefs } from "pinia";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import {
  mumarenFinanceCenterApi,
  voucherTemplatesApi,
  type MumarenFinanceBook,
  type MumarenVoucherTemplate,
} from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBookStore } from "@/stores/mumarenFinanceBook";

const bookStore = useMumarenFinanceBookStore();
const { books, bookId, isReadonly } = storeToRefs(bookStore);
const templates = ref<MumarenVoucherTemplate[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
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

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    templates.value = (await voucherTemplatesApi.list({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载凭证模板。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  templates.value = [];
  load();
};

onMounted(async () => {
  try {
    await bookStore.loadBooks();
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const openCreate = () => {
  if (isReadonly.value) return;
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  resetForm();
  dialogVisible.value = true;
};

const submit = async () => {
  if (isReadonly.value) return;
  if (!formRef.value || !bookId.value) return;
  const bid = bookId.value;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      await voucherTemplatesApi.create({
        book_id: bid,
        template_name: form.template_name.trim(),
        voucher_type: form.voucher_type,
        summary: form.summary.trim(),
      });
      ElMessage.success("模板已新增");
      dialogVisible.value = false;
      await load();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || "保存失败");
    } finally {
      saving.value = false;
    }
  });
};

const removeRow = async (row: MumarenVoucherTemplate) => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await voucherTemplatesApi.delete(row.id, bookId.value);
    ElMessage.success("模板已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .filters { flex-direction: column; } .heading { flex-direction: column; } }
</style>
