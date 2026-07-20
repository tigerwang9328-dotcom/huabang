<template>
  <div class="finance-module">
    <header class="module-header">
      <div>
        <p class="module-kicker">财务中心</p>
        <h1>{{ module.label }}</h1>
      </div>
      <el-tag :type="statusMeta.type" effect="plain">{{ statusMeta.label }}</el-tag>
    </header>

    <section class="module-summary">
      <div>
        <span>数据来源</span>
        <strong>{{ module.source }}</strong>
      </div>
      <div>
        <span>当前范围</span>
        <strong>{{ module.currentScope }}</strong>
      </div>
    </section>

    <section v-if="module.key === 'archive'" class="module-panel">
      <HistoricalFinance />
    </section>

    <section v-else-if="module.key === 'vouchers'" class="module-panel">
      <FormalLedger />
    </section>

    <section v-else-if="module.key === 'ledger' || module.key === 'reports'" class="module-panel">
      <div class="linked-actions">
        <router-link v-if="module.key === 'ledger'" to="/app/fin/history/account-balances">科目余额</router-link>
        <router-link v-if="module.key === 'ledger'" to="/app/fin/formal-ledger">正式账簿</router-link>
        <router-link v-if="module.key === 'reports'" to="/app/fin/history/statements">历史报表</router-link>
        <router-link v-if="module.key === 'reports'" to="/app/fin/formal-ledger">生成报表</router-link>
      </div>
      <div class="object-grid">
        <div v-for="item in module.primaryObjects" :key="item" class="object-tile">{{ item }}</div>
      </div>
    </section>

    <section v-else class="module-panel">
      <div class="object-grid">
        <div v-for="item in module.primaryObjects" :key="item" class="object-tile">{{ item }}</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import FormalLedger from "@/views/finance/FormalLedger.vue";
import HistoricalFinance from "@/views/finance/HistoricalFinance.vue";
import { financeCenterModuleMap, type FinanceModuleStatus } from "@/config/financeCenterModules";

const route = useRoute();
const module = computed(() => financeCenterModuleMap[String(route.meta.financeModuleKey)] || financeCenterModuleMap["data-cockpit"]);
const statusMap: Record<FinanceModuleStatus, { label: string; type: "success" | "warning" | "info" }> = {
  ready: { label: "已上线", type: "success" },
  partial: { label: "部分上线", type: "warning" },
  foundation: { label: "底座已建", type: "info" },
};
const statusMeta = computed(() => statusMap[module.value.status]);
</script>

<style scoped>
.finance-module { min-width: 0; color: #1f2937; }
.module-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.module-kicker { margin: 0 0 4px; color: #64748b; font-size: 12px; }
.module-header h1 { margin: 0; font-size: 24px; line-height: 1.25; letter-spacing: 0; }
.module-summary { display: grid; grid-template-columns: minmax(220px, .8fr) minmax(280px, 1.2fr); gap: 12px; margin-bottom: 14px; }
.module-summary > div, .module-panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.module-summary > div { padding: 14px; }
.module-summary span { display: block; color: #64748b; font-size: 12px; margin-bottom: 6px; }
.module-summary strong { display: block; font-size: 14px; line-height: 1.55; font-weight: 600; }
.module-panel { padding: 16px; }
.linked-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.linked-actions a { color: #2563eb; border: 1px solid #bfdbfe; background: #eff6ff; border-radius: 6px; padding: 7px 10px; text-decoration: none; font-size: 13px; }
.object-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.object-tile { min-height: 54px; display: flex; align-items: center; padding: 12px; border: 1px solid #e5e7eb; border-radius: 6px; background: #f8fafc; color: #334155; font-weight: 600; }
@media (max-width: 860px) {
  .module-header { align-items: flex-start; flex-direction: column; }
  .module-summary { grid-template-columns: 1fr; }
}
</style>
