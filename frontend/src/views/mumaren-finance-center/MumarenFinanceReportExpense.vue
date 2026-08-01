<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">财务报表</p>
        <h2>费用明细表</h2>
        <p>按期间、科目展示费用发生明细;支持会话内补充登记。</p>
      </div>
      <div class="heading-actions">
        <el-button type="primary" @click="openCreate">登记费用</el-button>
      </div>
    </div>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="完整数据接口待后端补,本会话数据刷新后清空"
    />

    <el-table :data="records" empty-text="暂无费用明细" stripe show-summary :summary-method="getSummaries">
      <el-table-column prop="period" label="期间" width="120" />
      <el-table-column prop="account_code" label="科目编码" width="140" />
      <el-table-column prop="account_name" label="科目名称" min-width="180" show-overflow-tooltip />
      <el-table-column label="金额" width="160" align="right">
        <template #default="scope">¥{{ money(scope.row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-popconfirm
            title="确定删除该记录吗?"
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

    <el-dialog v-model="dialogVisible" title="登记费用" width="520px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="期间" prop="period">
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" placeholder="请选择期间" style="width: 100%" />
        </el-form-item>
        <el-form-item label="科目编码" prop="account_code">
          <el-input v-model="form.account_code" placeholder="请输入科目编码" maxlength="30" />
        </el-form-item>
        <el-form-item label="科目名称" prop="account_name">
          <el-input v-model="form.account_name" placeholder="请输入科目名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="金额" prop="amount">
          <el-input-number v-model="form.amount" :min="0" :precision="2" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="请输入备注" maxlength="200" show-word-limit />
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

interface ExpenseRecord {
  id: number;
  period: string;
  account_code: string;
  account_name: string;
  amount: number;
  remark: string;
  created_at: string;
}

const records = ref<ExpenseRecord[]>([]);

const dialogVisible = ref(false);
const formRef = ref<FormInstance>();

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const defaultForm = () => ({
  period: "",
  account_code: "",
  account_name: "",
  amount: 0,
  remark: "",
});

const form = reactive(defaultForm());

const formRules: FormRules = {
  period: [{ required: true, message: "请选择期间", trigger: "change" }],
  account_code: [{ required: true, message: "请输入科目编码", trigger: "blur" }],
  account_name: [{ required: true, message: "请输入科目名称", trigger: "blur" }],
  amount: [{ required: true, message: "请输入金额", trigger: "blur" }],
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
    const row: ExpenseRecord = {
      id: Date.now(),
      period: form.period,
      account_code: form.account_code.trim(),
      account_name: form.account_name.trim(),
      amount: form.amount,
      remark: form.remark.trim(),
      created_at: now.toLocaleString("zh-CN", { hour12: false }),
    };
    records.value.push(row);
    ElMessage.success("费用已登记");
    dialogVisible.value = false;
  });
};

const removeRow = (row: ExpenseRecord) => {
  records.value = records.value.filter((item) => item.id !== row.id);
  ElMessage.success("记录已删除");
};

const getSummaries = (param: { columns: any[]; data: ExpenseRecord[] }) => {
  const { columns, data } = param;
  const sums: string[] = [];
  columns.forEach((column, index) => {
    if (index === 0) {
      sums[index] = "合计";
      return;
    }
    if (column.property === "amount") {
      const total = data.reduce((sum, item) => sum + (item.amount || 0), 0);
      sums[index] = "¥" + money(total);
    } else {
      sums[index] = "";
    }
  });
  return sums;
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
