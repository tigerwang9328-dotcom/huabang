<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">出纳管理</p>
        <h2>银行余额调节表</h2>
        <p>银行流水与账面余额的对账差异核销;会话内维护,刷新清空。</p>
      </div>
      <div class="heading-actions">
        <el-button type="primary" @click="openDialog">新增对账记录</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon title="完整数据接口待后端补,本会话数据刷新后清空" />

    <el-table :data="records" empty-text="暂无对账记录" stripe show-summary :summary-method="summary">
      <el-table-column prop="account_name" label="账户" min-width="180" />
      <el-table-column prop="reconcile_date" label="对账日期" width="130" />
      <el-table-column label="账面余额" width="150" align="right">
        <template #default="{ row }">{{ money(row.book_balance) }}</template>
      </el-table-column>
      <el-table-column label="银行余额" width="150" align="right">
        <template #default="{ row }">{{ money(row.bank_balance) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="150" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-warn': Math.abs(row.difference) > 0.001 }">{{ money(row.difference) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'pending' ? 'warning' : 'success'" size="small">
            {{ row.status === "pending" ? "待调节" : "已调节" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || "—" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'pending'"
            link
            type="primary"
            size="small"
            @click="reconcile(row)"
          >调节</el-button>
          <el-popconfirm title="确定删除该对账记录?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增对账记录" width="480px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="账户名称">
          <el-input v-model="form.account_name" placeholder="如 招行基本户" />
        </el-form-item>
        <el-form-item label="对账日期">
          <el-date-picker v-model="form.reconcile_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="账面余额">
          <el-input-number v-model="form.book_balance" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="银行余额">
          <el-input-number v-model="form.bank_balance" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
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

interface ReconciliationRecord {
  id: number;
  account_name: string;
  reconcile_date: string;
  book_balance: number;
  bank_balance: number;
  difference: number;
  status: "pending" | "reconciled";
  remark: string;
  created_at: string;
}

const records = ref<ReconciliationRecord[]>([]);
const dialogVisible = ref(false);
let seed = 1;

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const form = reactive({
  account_name: "",
  reconcile_date: new Date().toISOString().slice(0, 10),
  book_balance: 0,
  bank_balance: 0,
  remark: "",
});

const openDialog = () => {
  form.account_name = "";
  form.reconcile_date = new Date().toISOString().slice(0, 10);
  form.book_balance = 0;
  form.bank_balance = 0;
  form.remark = "";
  dialogVisible.value = true;
};

const save = () => {
  if (!form.account_name) {
    ElMessage.warning("请填写账户名称");
    return;
  }
  const book = Number(form.book_balance || 0);
  const bank = Number(form.bank_balance || 0);
  records.value.push({
    id: seed++,
    account_name: form.account_name,
    reconcile_date: form.reconcile_date,
    book_balance: book,
    bank_balance: bank,
    difference: Number((book - bank).toFixed(2)),
    status: "pending",
    remark: form.remark,
    created_at: new Date().toISOString(),
  });
  dialogVisible.value = false;
  ElMessage.success("对账记录已新增");
};

const reconcile = (row: ReconciliationRecord) => {
  if (row.status !== "pending") return;
  row.status = "reconciled";
  ElMessage.success("已调节");
};

const remove = (row: ReconciliationRecord) => {
  const idx = records.value.findIndex((r) => r.id === row.id);
  if (idx >= 0) records.value.splice(idx, 1);
  ElMessage.success("对账记录已删除");
};

const summary = ({ columns, data }: { columns: any[]; data: ReconciliationRecord[] }) => {
  const sums: (string | number)[] = [];
  columns.forEach((_, i) => {
    sums[i] = i === 0 ? "合计" : "";
  });
  const idxBook = columns.findIndex((c) => c.label === "账面余额");
  const idxBank = columns.findIndex((c) => c.label === "银行余额");
  const idxDiff = columns.findIndex((c) => c.label === "差异");
  if (idxBook >= 0) sums[idxBook] = money(data.reduce((s, r) => s + Number(r.book_balance || 0), 0));
  if (idxBank >= 0) sums[idxBank] = money(data.reduce((s, r) => s + Number(r.bank_balance || 0), 0));
  if (idxDiff >= 0) sums[idxDiff] = money(data.reduce((s, r) => s + Number(r.difference || 0), 0));
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
.diff-warn { color: #d9504a; font-weight: 600; }
@media (max-width: 640px) { .heading { flex-direction: column; } }
</style>
