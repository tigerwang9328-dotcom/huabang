<template>
  <div class="diagnosis-page">
    <section class="diag-hero">
      <p>AI BUSINESS DIAGNOSIS</p>
      <h1>总体经营诊断</h1>
      <span>基于经营概览、销售、库存、人力与任务数据生成诊断建议。当前为规则诊断底座，后续接入大模型深度分析。</span>
    </section>
    <section class="diag-grid">
      <div v-for="item in items" :key="item.title" class="diag-card" :class="item.level">
        <small>{{ item.scope }}</small>
        <strong>{{ item.title }}</strong>
        <p>{{ item.desc }}</p>
      </div>
    </section>
    <section class="diag-roadmap">
      <h2>分模块诊断规划</h2>
      <div class="roadmap-row" v-for="r in roadmap" :key="r.name">
        <span>{{ r.name }}</span>
        <p>{{ r.desc }}</p>
        <em>规划中</em>
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
const items = [
  { scope: "总体", title: "经营诊断入口已建立", desc: "后续将把销售、商品、库存、财务、人力、任务闭环统一进入AI诊断。", level: "ok" },
  { scope: "数据", title: "坚持不造假原则", desc: "纯利润、固定成本、库龄、人效等未接入字段，会明确标注待接入。", level: "warn" },
  { scope: "动作", title: "建议下一步接任务闭环", desc: "AI诊断结果应能一键生成任务，推送责任人并复查指标改善。", level: "info" },
];
const roadmap = [
  { name: "销售诊断", desc: "按线上、线下、门店、订单数、客单价、件单数定位销售问题。" },
  { name: "商品诊断", desc: "识别爆款、慢款、断码、滞销和补货机会。" },
  { name: "库存诊断", desc: "诊断库存金额、库存数量、库龄、缺货、高库存和异常库存。" },
  { name: "人力诊断", desc: "结合考勤、排班、导购归属和人效看人员效率。" },
  { name: "财务诊断", desc: "结合固定成本、商品成本、费用和现金安全天数输出利润风险。" },
];
</script>
<style scoped>
.diagnosis-page { padding: 0 24px 28px; background:#F6F8FB; min-height:100vh; color:#0F172A; }
.diag-hero { padding:32px 0 24px; border-bottom:1px solid #E2E8F0; }
.diag-hero p { margin:0 0 8px; color:#C0762A; font-size:11px; letter-spacing:.16em; font-weight:800; }
.diag-hero h1 { margin:0 0 8px; font-size:30px; }
.diag-hero span { color:#64748B; font-size:13px; }
.diag-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:22px; }
.diag-card, .diag-roadmap { background:#fff; border:1px solid #E2E8F0; border-radius:16px; padding:20px; box-shadow:0 12px 32px rgba(15,23,42,.04); }
.diag-card small { color:#94A3B8; } .diag-card strong { display:block; margin:8px 0; font-size:18px; } .diag-card p { color:#64748B; line-height:1.6; margin:0; }
.diag-card.ok { background:#F0FDF4; border-color:#BBF7D0; } .diag-card.warn { background:#FFFBEB; border-color:#FDE68A; } .diag-card.info { background:#EFF6FF; border-color:#BFDBFE; }
.diag-roadmap { margin-top:22px; } .diag-roadmap h2 { margin:0 0 14px; font-size:20px; }
.roadmap-row { display:grid; grid-template-columns:120px 1fr 72px; gap:16px; align-items:center; padding:14px 0; border-top:1px solid #EEF2F7; }
.roadmap-row span { font-weight:800; } .roadmap-row p { margin:0; color:#64748B; font-size:13px; } .roadmap-row em { font-style:normal; color:#C0762A; background:#FFF7ED; border-radius:999px; padding:4px 10px; font-size:12px; text-align:center; }
@media(max-width:900px){ .diag-grid{grid-template-columns:1fr;} .roadmap-row{grid-template-columns:1fr;} }
</style>
