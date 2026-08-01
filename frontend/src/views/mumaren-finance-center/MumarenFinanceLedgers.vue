<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">当前账</p>
        <h2>账簿</h2>
        <p>只展示新财务中心独立账簿，不读取旧财务表。</p>
      </div>
      <div class="actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增账簿</el-button>
      </div>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-else :data="books" empty-text="暂无独立账簿" stripe>
      <el-table-column prop="book_code" label="账簿编码" min-width="150" />
      <el-table-column prop="book_name" label="账簿名称" min-width="180" />
      <el-table-column prop="company_name" label="公司" min-width="180" />
      <el-table-column prop="status" label="状态" width="110" />
    </el-table>

    <el-dialog v-model="createVisible" title="新增账簿" width="520px" :close-on-click-modal="false">
      <el-form label-width="100px">
        <el-form-item label="账簿编码" required>
          <el-input v-model="form.book_code" maxlength="64" placeholder="例如：HB2026" />
        </el-form-item>
        <el-form-item label="账簿名称" required>
          <el-input v-model="form.book_name" maxlength="128" placeholder="请输入账簿名称" />
        </el-form-item>
        <el-form-item label="所属公司">
          <el-input v-model="form.company_name" maxlength="255" placeholder="请输入所属公司" />
        </el-form-item>
        <el-form-item label="启用状态" required>
          <el-select v-model="form.status" class="full-width">
            <el-option label="启用" value="active" />
            <el-option label="停用" value="inactive" />
          </el-select>
        </el-form-item>
      </el-form>
      <p class="hint">创建后自动初始化标准基础科目与 2026 年 12 个开放会计期间。</p>
      <template #footer>
        <el-button :disabled="saving" @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建并切换</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { storeToRefs } from "pinia";
import { ElMessage } from "element-plus";
import { mumarenFinanceCenterApi, type CreateMumarenFinanceBookPayload } from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBookStore } from "@/stores/mumarenFinanceBook";

const bookStore = useMumarenFinanceBookStore();
const { books, bookId, error, loading } = storeToRefs(bookStore);
const saving = ref(false);
const createVisible = ref(false);
const emptyForm = (): CreateMumarenFinanceBookPayload => ({ book_code: "", book_name: "", company_name: "", status: "active" });
const form = ref<CreateMumarenFinanceBookPayload>(emptyForm());

const load = async () => {
  await bookStore.loadBooks();
};

const openCreate = () => {
  form.value = emptyForm();
  createVisible.value = true;
};

const submitCreate = async () => {
  if (!form.value.book_code.trim() || !form.value.book_name.trim()) {
    ElMessage.warning("请填写账簿编码和账簿名称。");
    return;
  }
  saving.value = true;
  try {
    const created = (await mumarenFinanceCenterApi.createBook({
      ...form.value,
      book_code: form.value.book_code.trim(),
      book_name: form.value.book_name.trim(),
      company_name: form.value.company_name?.trim() || null,
    })).data.data;
    bookId.value = created.id;
    createVisible.value = false;
    await load();
    ElMessage.success("账簿已创建并切换为当前账。");
  } catch {
    ElMessage.error("新增账簿失败，请检查账簿编码是否重复。");
  } finally {
    saving.value = false;
  }
};

onMounted(load);
</script>

<style scoped>
.panel { padding:30px; border:1px solid #e1e7ef; border-radius:14px; background:#fff; }
.heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:16px; }
.actions { display:flex; gap:12px; }
.panel-kicker { margin:0; color:#176b97; font-size:12px; font-weight:700; letter-spacing:.08em; }
h2 { margin:8px 0; }
p { color:#5d6b7e; }
.hint { margin:0 0 4px 100px; font-size:13px; color:#7c8798; }
.full-width { width:100%; }
</style>
