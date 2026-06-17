<template>
  <div class="dashboard">
    <div class="stat-date">
      数据日期：{{ overview.stat_date || "加载中..." }}
      <el-tag v-if="overview.no_data" type="warning" size="small" style="margin-left:8px">暂无数据</el-tag>
      <el-tag v-if="overview.data_tip" type="info" size="small" style="margin-left:8px">{{ overview.data_tip }}</el-tag>
    </div>

    <!-- 核心KPI卡片 -->
    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="6" v-for="card in kpiCards" :key="card.label">
        <div class="kpi-card">
          <div class="kpi-label">{{ card.label }}</div>
          <div class="kpi-value" :class="{ no-data: card.value === null }">
            {{ card.value !== null ? (card.prefix || "") + formatNumber(card.value, card.decimals) + (card.suffix || "") : "--" }}
          </div>
          <div class="kpi-tip" v-if="card.tip">{{ card.tip }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 销售趋势 + 任务汇总 -->
    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="16">
        <div class="card">
          <div class="card-title">近7天销售趋势</div>
          <div class="chart-placeholder" v-if="!trend.length">暂无趋势数据</div>
          <div v-else class="trend-list">
            <div v-for="item in trend" :key="item.date" class="trend-row">
              <span class="trend-date">{{ item.date }}</span>
              <span class="trend-val">¥{{ formatNumber(item.total_sales) }}</span>
              <el-progress :percentage="Math.min(100, (item.total_sales/maxSales)*100)" :show-text="false" style="flex:1; margin:0 12px" />
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="card">
          <div class="card-title">任务状态汇总</div>
          <div v-for="(val, key) in taskSummary" :key="key" class="task-stat-row">
            <span class="task-stat-label">{{ taskStatusLabel[key] || key }}</span>
            <el-badge :value="val" :type="taskStatusType[key] || info" />
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 门店排行 -->
    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="24">
        <div class="card">
          <div class="card-title">门店销售排行（昨日 Top 10）</div>
          <el-table :data="storeRank" stripe size="small">
            <el-table-column label="排名" type="index" width="60" />
            <el-table-column prop="store_code" label="门店编码" width="120" />
            <el-table-column prop="net_sales" label="净销售额" :formatter="(r:any)=>formatMoney(r.net_sales)" />
            <el-table-column prop="order_count" label="订单数" width="80" />
            <el-table-column prop="avg_order_value" label="客单价" :formatter="(r:any)=>formatMoney(r.avg_order_value)" />
            <el-table-column prop="items_per_order" label="连带率" :formatter="(r:any)=>r.items_per_order?.toFixed(1)||--" />
          </el-table>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { dashboardApi } from "@/api/dashboard";

const overview = ref<any>({});
const trend = ref<any[]>([]);
const storeRank = ref<any[]>([]);
const taskSummary = ref<any>({});
const loading = ref(true);

const taskStatusLabel: Record<string, string> = {
  pending: "待处理", processing: "处理中", overdue: "已逾期",
  feedback_submitted: "待复查", review_passed: "复查通过",
  draft: "草稿", closed: "已关闭",
};
const taskStatusType: Record<string, string> = {
  pending: "warning", overdue: "danger", processing: "primary",
  review_passed: "success", feedback_submitted: "info",
};

const kpiCards = computed(() => [
  { label: "总销售额", value: overview.value.total_sales, prefix: "¥", decimals: 0 },
  { label: "线下销售额", value: overview.value.offline_sales, prefix: "¥", decimals: 0 },
  { label: "线上销售额", value: overview.value.online_sales, prefix: "¥", decimals: 0 },
  { label: "线上占比", value: overview.value.online_ratio ? overview.value.online_ratio * 100 : null, suffix: "%", decimals: 1 },
  { label: "订单数", value: overview.value.order_count, decimals: 0 },
  { label: "销售件数", value: overview.value.item_count, decimals: 0 },
  { label: "客单价", value: overview.value.avg_order_value, prefix: "¥", decimals: 1 },
  { label: "连带率", value: overview.value.items_per_order, suffix: "件/单", decimals: 2 },
  { label: "毛利额", value: overview.value.gross_profit, prefix: "¥", decimals: 0, tip: overview.value.data_tip },
  { label: "毛利率", value: overview.value.gross_margin ? overview.value.gross_margin * 100 : null, suffix: "%", decimals: 1, tip: overview.value.data_tip },
  { label: "库存金额", value: overview.value.total_inventory_amount, prefix: "¥", decimals: 0 },
  { label: "90天+库存", value: overview.value.age_90_plus_amount, prefix: "¥", decimals: 0 },
  { label: "待处理任务", value: overview.value.pending_task_count, decimals: 0 },
  { label: "逾期任务", value: overview.value.overdue_task_count, decimals: 0 },
  { label: "重大异常", value: null, decimals: 0 },
  { label: "折扣率", value: overview.value.avg_discount_rate ? overview.value.avg_discount_rate * 100 : null, suffix: "%", decimals: 1 },
]);

const maxSales = computed(() => Math.max(...trend.value.map((t: any) => t.total_sales || 0), 1));

const formatNumber = (v: any, decimals = 2) => {
  if (v === null || v === undefined) return "--";
  if (v >= 10000) return (v / 10000).toFixed(decimals) + "万";
  return Number(v).toFixed(decimals);
};
const formatMoney = (v: any) => v ? `¥${formatNumber(v, 0)}` : "--";

onMounted(async () => {
  try {
    const [r1, r2, r3, r4] = await Promise.all([
      dashboardApi.getOverview(),
      dashboardApi.getSalesTrend({ days: 7 }),
      dashboardApi.getStoreRank({ top_n: 10 }),
      dashboardApi.getTaskSummary(),
    ]);
    overview.value = r1.data.data || {};
    trend.value = r2.data.data?.trend || [];
    storeRank.value = r3.data.data?.rank || [];
    taskSummary.value = r4.data.data || {};
  } catch (e) {
    console.error("驾驶舱数据加载失败", e);
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.dashboard { padding: 0; }
.stat-date { color: #666; font-size: 13px; }
.kpi-card {
  background: #fff; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 0;
  min-height: 90px;
}
.kpi-label { color: #666; font-size: 13px; margin-bottom: 8px; }
.kpi-value { font-size: 24px; font-weight: 600; color: #333; }
.kpi-value.no-data { color: #ccc; font-size: 20px; }
.kpi-tip { color: #e6a23c; font-size: 11px; margin-top: 4px; }
.card {
  background: #fff; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.card-title { font-size: 14px; font-weight: 600; color: #333; margin-bottom: 16px; }
.chart-placeholder { color: #ccc; text-align: center; padding: 40px 0; }
.trend-row { display: flex; align-items: center; margin-bottom: 10px; font-size: 13px; }
.trend-date { width: 90px; color: #666; }
.trend-val { width: 80px; text-align: right; font-weight: 500; }
.task-stat-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f5f5f5; }
.task-stat-label { color: #666; font-size: 13px; }
</style>
