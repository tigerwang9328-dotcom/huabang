<template>
  <section class="finance-center-shell">
    <header class="finance-center-header">
      <div>
        <p class="eyebrow">牧马人财务模块</p>
        <h1>财务中心</h1>
        <p class="subtitle">凭证按"草稿 → 审核 → 人工过账"流转;历史数据只读。</p>
      </div>
      <span class="status-chip">独立账务区</span>
    </header>

    <main class="finance-center-content">
      <router-view />
    </main>
  </section>
</template>

<script setup lang="ts">
// 导航已集成到主侧边栏"财务中心"菜单项下(MainLayout.vue),此处仅渲染内容区。
</script>

<style scoped>
.finance-center-shell { max-width: 1240px; margin: 0 auto; color: #172033; }
.finance-center-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; padding: 28px 30px; border-radius: 16px; background: linear-gradient(124deg, #0f2946, #163e5c); color: #fff; box-shadow: 0 14px 30px rgba(16, 43, 70, .14); }
.eyebrow { margin: 0 0 6px; color: #d7b879; font-size: 12px; font-weight: 700; letter-spacing: .12em; }
h1 { margin: 0; font-size: 28px; line-height: 1.2; }
.subtitle { margin: 10px 0 0; color: #d9e2ea; font-size: 14px; }
.status-chip { margin-top: 5px; padding: 6px 10px; border: 1px solid rgba(215, 184, 121, .55); border-radius: 99px; color: #f3d698; font-size: 12px; white-space: nowrap; }

.finance-center-content { margin-top: 20px; min-height: 420px; }

@media (max-width: 640px) { .finance-center-header { padding: 22px; flex-direction: column; } h1 { font-size: 24px; } }
</style>
