<template>
  <section class="panel">
    <div class="heading">
      <div><p class="panel-kicker">设置</p><h2>账套管理</h2><p>仅创建新的独立当前账；金蝶迁移账簿永久只读。</p></div>
      <div class="actions"><el-button :loading="loading" @click="load">刷新</el-button><el-button type="primary" @click="visible = true">新增账簿</el-button></div>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-else :data="books" stripe>
      <el-table-column prop="book_code" label="账簿编码" width="170" />
      <el-table-column prop="book_name" label="账簿名称" min-width="210" />
      <el-table-column prop="company_name" label="主体" min-width="220" />
      <el-table-column label="类型" width="160"><template #default="{ row }"><el-tag :type="row.is_readonly ? 'warning' : 'success'">{{ row.is_readonly ? '金蝶迁移账簿（只读）' : '独立当前账' }}</el-tag></template></el-table-column>
      <el-table-column prop="status" label="状态" width="100" />
    </el-table>
    <el-dialog v-model="visible" title="新增独立账簿" width="480px" :close-on-click-modal="false">
      <el-alert type="info" :closable="false" title="创建后会初始化基础科目和当年会计期间；不能创建历史只读账簿。" />
      <el-form :model="form" label-width="88px" style="margin-top:16px"><el-form-item label="账簿编码" required><el-input v-model="form.book_code" placeholder="如 CURRENT_2026" /></el-form-item><el-form-item label="账簿名称" required><el-input v-model="form.book_name" /></el-form-item><el-form-item label="公司主体"><el-input v-model="form.company_name" /></el-form-item></el-form>
      <template #footer><el-button @click="visible = false">取消</el-button><el-button type="primary" :loading="saving" @click="createBook">创建</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { mumarenFinanceCenterApi } from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";

const { books, bookId, loadBooks } = useMumarenFinanceBook();
const loading = ref(false); const saving = ref(false); const visible = ref(false); const error = ref("");
const form = reactive({ book_code: "", book_name: "", company_name: "" });
const load = async () => { loading.value = true; error.value = ""; try { await loadBooks(); } catch { error.value = "无法加载独立账簿。"; } finally { loading.value = false; } };
const createBook = async () => {
  if (!form.book_code.trim() || !form.book_name.trim()) return ElMessage.warning("请填写账簿编码和名称");
  saving.value = true;
  try {
    const book = (await mumarenFinanceCenterApi.createBook({ book_code: form.book_code.trim(), book_name: form.book_name.trim(), company_name: form.company_name.trim() || null })).data.data;
    await load(); bookId.value = book.id; visible.value = false; form.book_code = ""; form.book_name = ""; form.company_name = ""; ElMessage.success("账簿已创建并初始化基础科目和会计期间");
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "创建账簿失败"); } finally { saving.value = false; }
};
onMounted(load);
</script>

<style scoped>
.panel { padding:30px; border:1px solid #e1e7ef; border-radius:14px; background:#fff; display:grid; gap:16px; }.heading,.actions { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }.actions { align-items:center; }.panel-kicker { margin:0; color:#176b97; font-size:12px; font-weight:700; letter-spacing:.08em; }h2 { margin:8px 0; }p { color:#5d6b7e; }@media (max-width:640px) { .heading { flex-direction:column; } }
</style>
