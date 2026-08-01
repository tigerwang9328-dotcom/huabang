<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">系统设置</p>
        <h2>操作日志</h2>
        <p>财务中心操作审计日志;会话内只读展示。</p>
      </div>
      <div class="heading-actions">
        <el-button @click="refresh">刷新</el-button>
        <el-button type="danger" @click="clear">清空</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon title="完整数据接口待后端补,本会话数据刷新后清空" />

    <div class="filters">
      <el-select v-model="filterModule" placeholder="按模块过滤" clearable style="width: 180px">
        <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
      </el-select>
      <el-date-picker
        v-model="filterRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width: 280px"
      />
    </div>

    <el-table :data="filteredLogs" empty-text="暂无日志" stripe>
      <el-table-column prop="operation_time" label="操作时间" width="180" />
      <el-table-column prop="module" label="模块" width="100" />
      <el-table-column prop="operation" label="操作" width="100" />
      <el-table-column prop="operator" label="操作人" width="120" />
      <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip />
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

interface AuditLog {
  id: number;
  operation_time: string;
  module: string;
  operation: string;
  operator: string;
  detail: string;
}

const logs = ref<AuditLog[]>([]);
const filterModule = ref("");
const filterRange = ref<[string, string] | null>(null);
let seed = 1;

const moduleOptions = ["凭证", "AR-AP", "税务", "资产", "发票", "出纳", "工资", "结账"];

const filteredLogs = computed(() => {
  let list = logs.value;
  if (filterModule.value) {
    list = list.filter((x) => x.module === filterModule.value);
  }
  if (filterRange.value && filterRange.value.length === 2) {
    const [start, end] = filterRange.value;
    list = list.filter((x) => {
      const day = x.operation_time.slice(0, 10);
      return day >= start && day <= end;
    });
  }
  return list;
});

const operators = ["张会计", "李出纳", "王财务", "赵经理", "系统"];

// 示例日志模板:涵盖各模块与操作类型
const logTemplates: { module: string; operation: string; detail: string }[] = [
  { module: "凭证", operation: "创建", detail: "新建转账凭证 TZ-2026-07-001,金额 ¥12,800.00" },
  { module: "凭证", operation: "审核", detail: "审核收款凭证 SK-2026-07-018 通过" },
  { module: "凭证", operation: "过账", detail: "凭证 FK-2026-07-009 已过账至总账" },
  { module: "AR-AP", operation: "创建", detail: "新增应收单 AR-2026-07-031,客户 贵阳新" },
  { module: "AR-AP", operation: "审核", detail: "应付单 AP-2026-07-022 审核通过" },
  { module: "AR-AP", operation: "结算", detail: "应收单 AR-2026-07-015 完成人工结算 ¥35,600.00" },
  { module: "税务", operation: "缴税", detail: "增值税 2026-07 申报缴款 ¥18,420.50" },
  { module: "税务", operation: "创建", detail: "新增税务申报表(印花税)" },
  { module: "资产", operation: "录入", detail: "新增固定资产 办公电脑×5,原值 ¥36,000.00" },
  { module: "资产", operation: "结算", detail: "资产 AS-0024 本月折旧计提 ¥1,200.00" },
  { module: "发票", operation: "创建", detail: "开具增值税专用发票 FP-2026-07-088" },
  { module: "发票", operation: "审核", detail: "进项发票 INV-2026-07-066 勾选认证" },
  { module: "出纳", operation: "录入", detail: "录入银行流水 收入 ¥48,900.00(招行基本户)" },
  { module: "出纳", operation: "结算", detail: "银行余额调节 招行基本户 已调节" },
  { module: "工资", operation: "录入", detail: "录入 2026-07 工资台账 共 12 人" },
  { module: "工资", operation: "结算", detail: "2026-07 工资批次发放合计 ¥186,500.00" },
  { module: "结账", operation: "过账", detail: "2026-07 月结 期间损益结转完成" },
  { module: "结账", operation: "审核", detail: "2026-07 试算平衡表复核通过" },
  { module: "凭证", operation: "删除", detail: "作废草稿凭证 DRAFT-2026-07-003" },
  { module: "发票", operation: "删除", detail: "作废误开普通发票 FP-2026-07-012" },
];

const randomTime = (offsetDays: number): string => {
  const d = new Date();
  d.setDate(d.getDate() - offsetDays);
  d.setHours(9 + Math.floor(Math.random() * 9), Math.floor(Math.random() * 60), Math.floor(Math.random() * 60));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

const refresh = () => {
  const pool = [...logTemplates].sort(() => Math.random() - 0.5);
  const count = 8 + Math.floor(Math.random() * 6);
  const picked = pool.slice(0, Math.min(count, pool.length));
  logs.value = picked.map((t) => ({
    id: seed++,
    operation_time: randomTime(Math.floor(Math.random() * 14)),
    module: t.module,
    operation: t.operation,
    operator: operators[Math.floor(Math.random() * operators.length)],
    detail: t.detail,
  }));
  logs.value.sort((a, b) => (a.operation_time < b.operation_time ? 1 : -1));
  ElMessage.success("已生成示例日志");
};

const clear = () => {
  logs.value = [];
  ElMessage.success("日志已清空");
};

onMounted(() => {
  refresh();
});
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.filters { display: flex; gap: 12px; align-items: center; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .filters { flex-direction: column; align-items: stretch; } .heading { flex-direction: column; } }
</style>
