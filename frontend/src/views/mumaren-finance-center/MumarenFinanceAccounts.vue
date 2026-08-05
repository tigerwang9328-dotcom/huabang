<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">科目体系</p>
        <h2>科目</h2>
        <p>当前账簿可维护科目；金蝶迁移账簿永久只读，不读取旧财务表。</p>
      </div>
      <div class="actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId || isReadonly" @click="openCreate">新增科目</el-button>
      </div>
    </div>
    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="load">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-else :data="accounts" empty-text="请选择独立账簿后查看科目" stripe>
      <el-table-column prop="account_code" label="科目编码" width="140" />
      <el-table-column prop="account_name" label="科目名称" min-width="200" />
      <el-table-column prop="account_type" label="科目类别" width="140" />
      <el-table-column prop="direction" label="余额方向" width="110" />
      <el-table-column label="辅助核算" min-width="160"><template #default="scope"><el-tag v-for="type in scope.row.required_auxiliary_types || []" :key="type" size="small" class="aux-tag">{{ type === 'supplier' ? '供应商' : type }}</el-tag><span v-if="!(scope.row.required_auxiliary_types || []).length">—</span></template></el-table-column>
      <el-table-column prop="level" label="级次" width="90" align="center" />
      <el-table-column label="状态" width="90"><template #default="scope"><el-tag :type="scope.row.is_active === false ? 'info' : 'success'">{{ scope.row.is_active === false ? '停用' : '启用' }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="140"><template #default="scope"><el-button link type="primary" :disabled="isReadonly" @click="openEdit(scope.row)">编辑</el-button><el-button link type="warning" :disabled="isReadonly || scope.row.is_active === false" @click="disable(scope.row)">停用</el-button></template></el-table-column>
    </el-table>
    <el-dialog v-model="showEditor" :title="editing ? '编辑科目' : '新增科目'" width="460px" :close-on-click-modal="false">
      <el-form :model="form" label-width="90px">
        <el-form-item label="科目编码" required><el-input v-model="form.account_code" :disabled="!!editing" /></el-form-item>
        <el-form-item label="科目名称" required><el-input v-model="form.account_name" /></el-form-item>
        <el-form-item label="科目类别" required><el-select v-model="form.account_type" style="width:100%"><el-option v-for="item in accountTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <el-form-item label="余额方向" required><el-radio-group v-model="form.direction"><el-radio value="debit">借</el-radio><el-radio value="credit">贷</el-radio></el-radio-group></el-form-item>
        <el-form-item label="级次"><el-input-number v-model="form.level" :min="1" :max="10" /></el-form-item>
        <el-form-item label="辅助核算"><el-checkbox v-model="form.supplier_auxiliary">按供应商辅助核算</el-checkbox><div class="form-tip">启用后，涉及该科目的每条凭证分录必须选择供应商。</div></el-form-item>
      </el-form>
      <template #footer><el-button @click="showEditor=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { storeToRefs } from "pinia";
import { ElMessage } from "element-plus";
import { mumarenFinanceCenterApi, type MumarenFinanceAccount, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBookStore } from "@/stores/mumarenFinanceBook";

const bookStore = useMumarenFinanceBookStore();
const { books, bookId, isReadonly } = storeToRefs(bookStore);
const accounts = ref<MumarenFinanceAccount[]>([]);
const error = ref("");
const loading = ref(false);
const saving = ref(false);
const showEditor = ref(false);
const editing = ref<MumarenFinanceAccount>();
const accountTypes = [{ value: "asset", label: "资产" }, { value: "liability", label: "负债" }, { value: "equity", label: "权益" }, { value: "income", label: "收入" }, { value: "expense", label: "费用" }];
const form = reactive({ account_code: "", account_name: "", account_type: "asset" as "asset" | "liability" | "equity" | "income" | "expense", direction: "debit" as "debit" | "credit", level: 1, supplier_auxiliary: false });

const load = async () => {
  if (!bookId.value) {
    accounts.value = [];
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    accounts.value = (await mumarenFinanceCenterApi.listAccounts(bookId.value)).data.data;
  } catch {
    error.value = "无法加载独立科目体系。";
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  try {
    await bookStore.loadBooks();
    await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const openCreate = () => {
  editing.value = undefined;
  Object.assign(form, { account_code: "", account_name: "", account_type: "asset", direction: "debit", level: 1, supplier_auxiliary: false });
  showEditor.value = true;
};
const openEdit = (account: MumarenFinanceAccount) => {
  editing.value = account;
  Object.assign(form, account, { supplier_auxiliary: (account.required_auxiliary_types || []).includes("supplier") });
  showEditor.value = true;
};
const save = async () => {
  if (!bookId.value || !form.account_code.trim() || !form.account_name.trim()) return;
  saving.value = true;
  try {
    if (editing.value) {
      await mumarenFinanceCenterApi.updateAccount(bookId.value, editing.value.id, { book_id: bookId.value, account_name: form.account_name, account_type: form.account_type, direction: form.direction, level: form.level });
      const retained = (editing.value.required_auxiliary_types || []).filter((type) => type !== "supplier") as Array<"customer" | "employee" | "project" | "department">;
      await mumarenFinanceCenterApi.replaceAccountAuxiliaryDimensions(bookId.value, editing.value.id, { book_id: bookId.value, auxiliary_types: form.supplier_auxiliary ? [...retained, "supplier"] : retained });
    } else {
      const account = (await mumarenFinanceCenterApi.createAccount(bookId.value, { account_code: form.account_code, account_name: form.account_name, account_type: form.account_type, direction: form.direction, level: form.level })).data.data;
      if (form.supplier_auxiliary) await mumarenFinanceCenterApi.replaceAccountAuxiliaryDimensions(bookId.value, account.id, { book_id: bookId.value, auxiliary_types: ["supplier"] });
    }
    ElMessage.success(editing.value ? "科目已更新" : "科目已创建"); showEditor.value = false; await load();
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败"); } finally { saving.value = false; }
};
const disable = async (account: MumarenFinanceAccount) => {
  if (!bookId.value) return;
  try { await mumarenFinanceCenterApi.updateAccount(bookId.value, account.id, { book_id: bookId.value, is_active: false }); ElMessage.success("科目已停用"); await load(); }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "停用失败"); }
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.actions { display: flex; gap: 8px; }
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
.aux-tag { margin-right: 4px; }
.form-tip { margin-top: 4px; color: #7a8493; font-size: 12px; line-height: 1.4; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } }
</style>
