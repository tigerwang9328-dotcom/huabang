<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">系统设置</p>
        <h2>辅助核算</h2>
        <p>客户、供应商、部门、项目等辅助核算维度管理;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId" @click="openDialog">新增核算项</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-select v-model="filterDimension" placeholder="按维度过滤" clearable style="width: 200px" @change="load">
        <el-option label="客户" value="客户" />
        <el-option label="供应商" value="供应商" />
        <el-option label="部门" value="部门" />
        <el-option label="项目" value="项目" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="items" empty-text="暂无核算项" stripe>
      <el-table-column prop="aux_type" label="维度" width="120" />
      <el-table-column prop="code" label="编码" width="140" />
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column label="父级编码" width="140">
        <template #default="{ row }">{{ row.parent_code || "—" }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
            {{ row.status === "active" ? "启用" : "停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || "—" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button link :type="row.status === 'active' ? 'warning' : 'success'" size="small" :loading="actingId === row.id" @click="toggle(row)">
            {{ row.status === "active" ? "停用" : "启用" }}
          </el-button>
          <el-popconfirm title="确定删除该核算项?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small" :loading="actingId === row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增核算项" width="480px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="维度">
          <el-select v-model="form.aux_type" style="width:100%" placeholder="选择维度">
            <el-option label="客户" value="客户" />
            <el-option label="供应商" value="供应商" />
            <el-option label="部门" value="部门" />
            <el-option label="项目" value="项目" />
          </el-select>
        </el-form-item>
        <el-form-item label="编码">
          <el-input v-model="form.code" placeholder="如 C001 / S001 / D001 / P001" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="父级编码">
          <el-input v-model="form.parent_code" placeholder="可选,留空表示顶级" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  auxiliaryAccountingsApi,
  mumarenFinanceCenterApi,
  type MumarenAuxiliaryAccounting,
  type MumarenFinanceBook,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const items = ref<MumarenAuxiliaryAccounting[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
const dialogVisible = ref(false);
const filterDimension = ref("");
const auxTypeValue = (label: string) => ({ 客户: "customer", 供应商: "supplier", 员工: "employee", 项目: "project", 部门: "department" }[label] || label);

const form = reactive({
  aux_type: "客户",
  code: "",
  name: "",
  parent_code: "",
  remark: "",
});

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    items.value = (await auxiliaryAccountingsApi.list({
      book_id: bookId.value,
      aux_type: filterDimension.value ? auxTypeValue(filterDimension.value) : undefined,
    })).data.data;
  } catch {
    error.value = "无法加载辅助核算项。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  items.value = [];
  load();
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const openDialog = () => {
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  form.aux_type = "客户";
  form.code = "";
  form.name = "";
  form.parent_code = "";
  form.remark = "";
  dialogVisible.value = true;
};

const save = async () => {
  if (!bookId.value) return;
  if (!form.code) {
    ElMessage.warning("请填写编码");
    return;
  }
  if (!form.name) {
    ElMessage.warning("请填写名称");
    return;
  }
  saving.value = true;
  try {
    await auxiliaryAccountingsApi.create({
      book_id: bookId.value,
      aux_type: auxTypeValue(form.aux_type),
      code: form.code,
      name: form.name,
      parent_id: items.value.find((item) => item.code === form.parent_code)?.id ?? null,
    });
    ElMessage.success("核算项已新增");
    dialogVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
};

const toggle = async (row: MumarenAuxiliaryAccounting) => {
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await auxiliaryAccountingsApi.update(row.id, {
      is_active: !row.is_active,
    }, bookId.value);
    ElMessage.success(row.is_active ? "已停用" : "已启用");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "操作失败");
  } finally {
    actingId.value = undefined;
  }
};

const remove = async (row: MumarenAuxiliaryAccounting) => {
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await auxiliaryAccountingsApi.delete(row.id, bookId.value);
    ElMessage.success("核算项已删除");
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
.filters { display: flex; gap: 12px; align-items: center; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .filters { flex-direction: column; align-items: stretch; } .heading { flex-direction: column; } }
</style>
