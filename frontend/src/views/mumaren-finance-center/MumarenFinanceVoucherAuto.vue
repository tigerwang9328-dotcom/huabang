<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证管理</p>
        <h2>自动凭证</h2>
        <p>业务单据按规则自动生成凭证草稿;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId" @click="openCreate">新增规则</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="rules" empty-text="暂无自动凭证规则" stripe>
      <el-table-column prop="rule_name" label="规则名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="business_type" label="业务类型" width="110" />
      <el-table-column prop="account_code" label="科目编码" width="130" />
      <el-table-column label="方向" width="80">
        <template #default="scope">
          <el-tag :type="scope.row.direction === 'debit' ? 'primary' : 'warning'" size="small">
            {{ scope.row.direction === "debit" ? "借" : "贷" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="金额来源" width="160">
        <template #default="scope">
          {{ scope.row.amount_source === "fixed" ? `固定 ¥${money(scope.row.fixed_amount || 0)}` : "业务单据金额" }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.enabled ? 'success' : 'info'" size="small">
            {{ scope.row.enabled ? "启用" : "停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="scope">
          <el-button size="small" link type="primary" @click="preview(scope.row)">预览</el-button>
          <el-popconfirm
            title="确定删除该规则吗?"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="removeRow(scope.row)"
          >
            <template #reference>
              <el-button size="small" link type="danger" :loading="actingId === scope.row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增规则" width="560px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="规则名称" prop="rule_name">
          <el-input v-model="form.rule_name" placeholder="请输入规则名称" maxlength="50" show-word-limit />
        </el-form-item>
        <el-form-item label="业务类型" prop="business_type">
          <el-select v-model="form.business_type" placeholder="请选择业务类型" style="width: 100%">
            <el-option label="销售" value="销售" />
            <el-option label="采购" value="采购" />
            <el-option label="收款" value="收款" />
            <el-option label="付款" value="付款" />
            <el-option label="费用" value="费用" />
          </el-select>
        </el-form-item>
        <el-form-item label="科目编码" prop="account_code">
          <el-input v-model="form.account_code" placeholder="请输入科目编码" maxlength="30" />
        </el-form-item>
        <el-form-item label="方向" prop="direction">
          <el-radio-group v-model="form.direction">
            <el-radio value="debit">借</el-radio>
            <el-radio value="credit">贷</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="金额来源" prop="amount_source">
          <el-select v-model="form.amount_source" placeholder="请选择金额来源" style="width: 100%">
            <el-option label="固定" value="fixed" />
            <el-option label="业务单据金额" value="business" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.amount_source === 'fixed'" label="固定金额" prop="fixed_amount">
          <el-input-number v-model="form.fixed_amount" :min="0" :precision="2" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用" prop="enabled">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="规则预览" width="480px">
      <p v-if="previewRow" class="preview-text">
        预览:此规则将生成一条
        <strong>{{ previewRow.direction === "debit" ? "借" : "贷" }}</strong>
        方向的凭证分录,科目
        <strong>{{ previewRow.account_code }}</strong>,金额
        <strong>{{
          previewRow.amount_source === "fixed"
            ? "¥" + money(previewRow.fixed_amount || 0)
            : "业务单据金额"
        }}</strong>。
      </p>
      <template #footer>
        <el-button type="primary" @click="previewVisible = false">知道了</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import {
  autoVoucherRulesApi,
  mumarenFinanceCenterApi,
  type MumarenAutoVoucherRule,
  type MumarenFinanceBook,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const bookId = ref<number>();
const rules = ref<MumarenAutoVoucherRule[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
const dialogVisible = ref(false);
const formRef = ref<FormInstance>();
const previewVisible = ref(false);
const previewRow = ref<MumarenAutoVoucherRule | null>(null);

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const defaultForm = () => ({
  rule_name: "",
  business_type: "销售",
  account_code: "",
  direction: "debit" as "debit" | "credit",
  amount_source: "fixed",
  fixed_amount: 0,
  enabled: true,
});

const form = reactive(defaultForm());

const formRules: FormRules = {
  rule_name: [{ required: true, message: "请输入规则名称", trigger: "blur" }],
  business_type: [{ required: true, message: "请选择业务类型", trigger: "change" }],
  account_code: [{ required: true, message: "请输入科目编码", trigger: "blur" }],
  direction: [{ required: true, message: "请选择方向", trigger: "change" }],
  amount_source: [{ required: true, message: "请选择金额来源", trigger: "change" }],
  fixed_amount: [{ required: true, message: "请输入固定金额", trigger: "blur" }],
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
    rules.value = (await autoVoucherRulesApi.list({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载自动凭证规则。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  rules.value = [];
  load();
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    bookId.value = books.value[0]?.id;
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const openCreate = () => {
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  resetForm();
  dialogVisible.value = true;
};

const submit = async () => {
  if (!formRef.value || !bookId.value) return;
  const bid = bookId.value;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      await autoVoucherRulesApi.create({
        book_id: bid,
        rule_name: form.rule_name.trim(),
        business_type: form.business_type,
        account_code: form.account_code.trim(),
        direction: form.direction,
        amount_source: form.amount_source,
        fixed_amount: form.amount_source === "fixed" ? form.fixed_amount : undefined,
        enabled: form.enabled,
      });
      ElMessage.success("规则已新增");
      dialogVisible.value = false;
      await load();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || "保存失败");
    } finally {
      saving.value = false;
    }
  });
};

const removeRow = async (row: MumarenAutoVoucherRule) => {
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await autoVoucherRulesApi.delete(row.id, bookId.value);
    ElMessage.success("规则已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const preview = (row: MumarenAutoVoucherRule) => {
  previewRow.value = row;
  previewVisible.value = true;
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
.preview-text { line-height: 1.8; color: #5d6b7e; }
.preview-text strong { color: #176b97; }
@media (max-width: 640px) { .filters { flex-direction: column; } .heading { flex-direction: column; } }
</style>
