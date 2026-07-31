<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">期末结账</p>
        <h2>结账</h2>
        <p>期末结账能力待接入：暂不可用，不伪装可操作。</p>
      </div>
    </div>

    <el-alert
      type="warning"
      :closable="false"
      title="期末结账独立后端适配尚未完成"
      description="在期间结账接口、预检规则与独立权限校验就绪前，本页不提供任何结账/反结账操作，也不会调用旧华邦财务接口。"
      show-icon
    />

    <div class="capability-grid">
      <article v-for="capability in closingCapabilities" :key="capability.title" class="capability-card">
        <div class="card-title-row">
          <h3>{{ capability.title }}</h3>
          <el-tag type="info" effect="plain">后端适配待完成</el-tag>
        </div>
        <p>{{ capability.description }}</p>
        <p class="reason">{{ capability.unavailableReason }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
// 期末结账为外壳页：所有能力均标注暂不可用，不调用任何后端接口。
const closingCapabilities = [
  {
    title: "期间结账预检",
    description: "结账前对凭证完整性、借贷平衡、未审核单据进行预检。",
    unavailableReason: "等待独立结账预检接口接入，当前不可操作。",
  },
  {
    title: "期末结账",
    description: "按会计期间执行期末结账，结账后该期间凭证不可再修改。",
    unavailableReason: "等待独立结账接口接入，当前不可结账。",
  },
  {
    title: "结账状态查询",
    description: "查询各账簿各期间的结账状态与结账人。",
    unavailableReason: "等待独立结账状态查询接口接入，当前不可查询。",
  },
] as const;
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 18px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; line-height: 1.65; }
.capability-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
.capability-card { padding: 18px; border: 1px solid #e1e7ef; border-radius: 12px; background: #fbfdff; }
.card-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
h3 { margin: 0; color: #172033; font-size: 16px; }
.reason { color: #9b5b00 !important; font-size: 13px; font-weight: 600; }
</style>
