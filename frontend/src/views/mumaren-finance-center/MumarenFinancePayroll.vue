<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">薪资管理</p>
        <h2>工资</h2>
        <p>工资台账、社保公积金与个税核对;会话内维护,刷新清空。</p>
      </div>
      <div class="heading-actions">
        <el-button type="primary" @click="openDialog">录入工资</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon title="完整数据接口待后端补,本会话数据刷新后清空" />

    <el-table :data="records" empty-text="暂无工资记录" stripe show-summary :summary-method="summary">
      <el-table-column prop="employee_name" label="员工" min-width="120" />
      <el-table-column prop="department" label="部门" min-width="120" />
      <el-table-column prop="period" label="期间" width="110" />
      <el-table-column label="基本工资" width="130" align="right">
        <template #default="{ row }">{{ money(row.base_salary) }}</template>
      </el-table-column>
      <el-table-column label="奖金" width="120" align="right">
        <template #default="{ row }">{{ money(row.bonus) }}</template>
      </el-table-column>
      <el-table-column label="应发" width="130" align="right">
        <template #default="{ row }">{{ money(row.gross_salary) }}</template>
      </el-table-column>
      <el-table-column label="社保" width="120" align="right">
        <template #default="{ row }">{{ money(row.social_insurance) }}</template>
      </el-table-column>
      <el-table-column label="公积金" width="120" align="right">
        <template #default="{ row }">{{ money(row.housing_fund) }}</template>
      </el-table-column>
      <el-table-column label="个税" width="120" align="right">
        <template #default="{ row }">{{ money(row.income_tax) }}</template>
      </el-table-column>
      <el-table-column label="实发" width="130" align="right">
        <template #default="{ row }">{{ money(row.net_salary) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'draft' ? 'warning' : 'success'" size="small">
            {{ row.status === "draft" ? "草稿" : "已发放" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'draft'"
            link
            type="primary"
            size="small"
            @click="pay(row)"
          >发放</el-button>
          <el-popconfirm title="确定删除该工资记录?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="录入工资" width="520px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="员工姓名">
          <el-input v-model="form.employee_name" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="form.department" />
        </el-form-item>
        <el-form-item label="期间">
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" style="width:100%" />
        </el-form-item>
        <el-form-item label="基本工资">
          <el-input-number v-model="form.base_salary" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="奖金">
          <el-input-number v-model="form.bonus" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="社保">
          <el-input-number v-model="form.social_insurance" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="公积金">
          <el-input-number v-model="form.housing_fund" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="个税">
          <el-input-number v-model="form.income_tax" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";

interface PayrollRecord {
  id: number;
  employee_name: string;
  department: string;
  period: string;
  base_salary: number;
  bonus: number;
  gross_salary: number;
  social_insurance: number;
  housing_fund: number;
  income_tax: number;
  net_salary: number;
  status: "draft" | "paid";
  created_at: string;
}

const records = ref<PayrollRecord[]>([]);
const dialogVisible = ref(false);
let seed = 1;

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const form = reactive({
  employee_name: "",
  department: "",
  period: new Date().toISOString().slice(0, 7),
  base_salary: 0,
  bonus: 0,
  social_insurance: 0,
  housing_fund: 0,
  income_tax: 0,
});

const openDialog = () => {
  form.employee_name = "";
  form.department = "";
  form.period = new Date().toISOString().slice(0, 7);
  form.base_salary = 0;
  form.bonus = 0;
  form.social_insurance = 0;
  form.housing_fund = 0;
  form.income_tax = 0;
  dialogVisible.value = true;
};

const save = () => {
  if (!form.employee_name) {
    ElMessage.warning("请填写员工姓名");
    return;
  }
  const base = Number(form.base_salary || 0);
  const bonus = Number(form.bonus || 0);
  const social = Number(form.social_insurance || 0);
  const housing = Number(form.housing_fund || 0);
  const tax = Number(form.income_tax || 0);
  const gross = Number((base + bonus).toFixed(2));
  const net = Number((gross - social - housing - tax).toFixed(2));
  records.value.push({
    id: seed++,
    employee_name: form.employee_name,
    department: form.department,
    period: form.period,
    base_salary: base,
    bonus,
    gross_salary: gross,
    social_insurance: social,
    housing_fund: housing,
    income_tax: tax,
    net_salary: net,
    status: "draft",
    created_at: new Date().toISOString(),
  });
  dialogVisible.value = false;
  ElMessage.success("工资记录已录入");
};

const pay = (row: PayrollRecord) => {
  if (row.status !== "draft") return;
  row.status = "paid";
  ElMessage.success("工资已发放");
};

const remove = (row: PayrollRecord) => {
  const idx = records.value.findIndex((r) => r.id === row.id);
  if (idx >= 0) records.value.splice(idx, 1);
  ElMessage.success("工资记录已删除");
};

const summary = ({ columns, data }: { columns: any[]; data: PayrollRecord[] }) => {
  const sums: (string | number)[] = [];
  columns.forEach((_, i) => {
    sums[i] = i === 0 ? "合计" : "";
  });
  const fields: Record<string, keyof PayrollRecord> = {
    基本工资: "base_salary",
    奖金: "bonus",
    应发: "gross_salary",
    社保: "social_insurance",
    公积金: "housing_fund",
    个税: "income_tax",
    实发: "net_salary",
  };
  Object.keys(fields).forEach((label) => {
    const idx = columns.findIndex((c) => c.label === label);
    if (idx >= 0) {
      sums[idx] = money(data.reduce((s, r) => s + Number(r[fields[label]] || 0), 0));
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
