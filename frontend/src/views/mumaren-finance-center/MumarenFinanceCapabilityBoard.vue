<template>
  <section class="capability-board">
    <header>
      <p class="panel-kicker">牧马人模块直接移植范围</p>
      <h2>{{ title }}</h2>
      <p>{{ summary }}</p>
    </header>

    <el-alert
      type="warning"
      :closable="false"
      title="以下能力的独立后端适配尚未完成"
      description="页面仅展示已核实的牧马人功能边界；在接口、独立数据表和权限校验就绪前不可录入，也不会调用旧华邦财务接口。"
      show-icon
    />

    <div class="capability-grid">
      <article v-for="capability in capabilities" :key="capability.title" class="capability-card">
        <div class="card-title-row">
          <h3>{{ capability.title }}</h3>
          <el-tag :type="capability.availability === 'available' ? 'success' : 'info'" effect="plain">
            {{ capability.availability === "available" ? "已接入" : "后端适配待完成" }}
          </el-tag>
        </div>
        <p>{{ capability.description }}</p>
        <p class="source">来源：{{ capability.sourceModule }}</p>
        <p v-if="capability.unavailableReason" class="reason">{{ capability.unavailableReason }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { MumarenFinanceCapability } from "@/config/mumarenFinanceCenter";

defineProps<{
  title: string;
  summary: string;
  capabilities: readonly MumarenFinanceCapability[];
}>();
</script>

<style scoped>
.capability-board { display: grid; gap: 18px; padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; color: #172033; }
header > p:not(.panel-kicker), .capability-card p { color: #5d6b7e; line-height: 1.65; }
.capability-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
.capability-card { padding: 18px; border: 1px solid #e1e7ef; border-radius: 12px; background: #fbfdff; }
.card-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
h3 { margin: 0; color: #172033; font-size: 16px; }
.source { color: #718096 !important; font-size: 12px; word-break: break-all; }
.reason { color: #9b5b00 !important; font-size: 13px; font-weight: 600; }
</style>
