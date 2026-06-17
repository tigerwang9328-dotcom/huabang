<template>
  <div class="page-container">
    <div class="page-header"><h2>财务利润中心</h2></div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="费用补录" name="expense">
        <el-card>
          <el-form :model="expenseForm" label-width="100px" style="max-width:500px">
            <el-form-item label="费用日期" required><el-date-picker v-model="expenseForm.expense_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
            <el-form-item label="关联门店"><el-input v-model="expenseForm.store_code" placeholder="留空=公司级费用" /></el-form-item>
            <el-form-item label="费用类型" required>
              <el-select v-model="expenseForm.expense_type">
                <el-option label="租金" value="rent" /><el-option label="人工" value="labor" />
                <el-option label="水电" value="utilities" /><el-option label="物流" value="logistics" />
                <el-option label="管理费用" value="admin" /><el-option label="其他" value="other" />
              </el-select>
            </el-form-item>
            <el-form-item label="费用金额" required><el-input-number v-model="expenseForm.expense_amount" :min="0.01" :precision="2" style="width:100%" /></el-form-item>
            <el-form-item label="数据类型">
              <el-radio-group v-model="expenseForm.data_type">
                <el-radio value="estimate">预估值</el-radio>
                <el-radio value="actual">财务核准</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="备注"><el-input v-model="expenseForm.description" /></el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitExpense" :loading="submitting">提交录入</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="现金补录" name="cash">
        <el-card>
          <el-form :model="cashForm" label-width="100px" style="max-width:500px">
            <el-form-item label="记录日期" required><el-date-picker v-model="cashForm.record_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
            <el-form-item label="账户类型">
              <el-select v-model="cashForm.account_type">
                <el-option label="银行账户" value="bank" /><el-option label="现金" value="cash" />
              </el-select>
            </el-form-item>
            <el-form-item label="账户名称"><el-input v-model="cashForm.account_name" /></el-form-item>
            <el-form-item label="余额" required><el-input-number v-model="cashForm.balance" :precision="2" style="width:100%" /></el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitCash" :loading="submitting">提交录入</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="现金安全天数" name="cash_safety">
        <el-card v-loading="loadingCash">
          <div v-if="cashSafety">
            <el-statistic title="现金余额合计" :value="cashSafety.total_cash_balance" prefix="¥" />
            <el-statistic title="近30天日均支出" :value="cashSafety.daily_avg_expense_30d||0" prefix="¥" style="margin-top:16px" />
            <el-statistic title="现金安全天数" :value="cashSafety.cash_safety_days||0" suffix="天" style="margin-top:16px">
              <template #title>
                <span>现金安全天数</span>
                <el-tag :type="cashSafety.risk_level==\"critical\"?\"danger\":cashSafety.risk_level==\"warning\"?\"warning\":\"success\"" size="small" style="margin-left:8px">
                  {{ cashSafety.risk_level }}
                </el-tag>
              </template>
            </el-statistic>
            <p style="color:#999; font-size:12px; margin-top:16px">{{ cashSafety.note }}</p>
          </div>
          <el-empty v-else description="暂无现金数据，请先补录" />
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { financeApi } from "@/api/finance";
import { ElMessage } from "element-plus";
const activeTab = ref("expense");
const submitting = ref(false);
const loadingCash = ref(false);
const cashSafety = ref<any>(null);
const expenseForm = reactive({ expense_date: "", store_code: "", expense_type: "", expense_amount: 0, data_type: "estimate", description: "" });
const cashForm = reactive({ record_date: "", account_type: "bank", account_name: "", balance: 0 });
const submitExpense = async () => {
  if (!expenseForm.expense_date || !expenseForm.expense_type || !expenseForm.expense_amount) return ElMessage.warning("请填写必填项");
  submitting.value = true;
  try {
    await financeApi.createExpense(expenseForm);
    ElMessage.success("费用录入成功（" + (expenseForm.data_type === "actual" ? "财务核准" : "预估值") + "）");
  } finally { submitting.value = false; }
};
const submitCash = async () => {
  if (!cashForm.record_date || !cashForm.balance) return ElMessage.warning("请填写必填项");
  submitting.value = true;
  try {
    await financeApi.createCash(cashForm);
    ElMessage.success("现金余额录入成功");
    loadCashSafety();
  } finally { submitting.value = false; }
};
const loadCashSafety = async () => {
  loadingCash.value = true;
  try {
    const res = await financeApi.getCashSafety();
    cashSafety.value = res.data.data;
  } catch {} finally { loadingCash.value = false; }
};
onMounted(loadCashSafety);
</script>
<style scoped>
.page-container { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 18px; color: #333; }
</style>
