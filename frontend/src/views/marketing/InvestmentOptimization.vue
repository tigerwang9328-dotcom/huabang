<template>
  <div class="investment-page" v-loading="loading">
    <header class="page-head">
      <div>
        <p class="eyebrow">LIFEDATA · 本地投放决策</p>
        <h1>投流优化</h1>
        <p class="subline">以实际核销为终点，判断下一笔预算该投给谁。</p>
      </div>
      <div class="freshness">
        <span class="status-dot" :class="data.collector?.status"></span>
        {{ data.collector?.status === 'online' ? '采集器在线' : '采集器离线' }}
        <small>最近数据 {{ formatTime(data.period?.latest_capture_at) }}</small>
        <el-button size="small" @click="load">刷新数据</el-button>
      </div>
    </header>

    <el-alert
      v-if="data.data_quality?.is_estimated_verify_attribution"
      title="实际核销ROI为账户同期估算；平台广告归因与账户经营数据尚未完全对应到同一条素材。"
      type="warning"
      show-icon
      :closable="false"
    />

    <section class="decision-ledger">
      <div class="ledger-cell"><span>01 投放消耗</span><strong>{{ money(summary.ad_cost_fen) }}</strong></div>
      <b class="arrow">→</b>
      <div class="ledger-cell"><span>02 广告成交</span><strong>{{ money(summary.ad_pay_gmv_fen) }}</strong><em>ROI {{ ratio(summary.ad_pay_roi) }}</em></div>
      <b class="arrow">→</b>
      <div class="ledger-cell verified"><span>03 实际核销</span><strong>{{ money(summary.verify_gmv_fen) }}</strong><em>实际核销ROI {{ ratio(summary.verify_roi) }}</em></div>
      <b class="arrow">→</b>
      <div class="ledger-cell refund"><span>04 退款</span><strong>{{ money(summary.refund_gmv_fen) }}</strong><em>退款率 {{ percent(summary.refund_rate) }}</em></div>
    </section>

    <section class="grid-main">
      <article class="ai-decision" :class="recommendation.action">
        <div class="section-label">AI 下一步建议</div>
        <h2>{{ recommendation.title || '等待完整数据' }}</h2>
        <p class="action-copy">建议动作：{{ actionLabel(recommendation.action) }}</p>
        <div class="budget" v-if="recommendation.budget">
          <span>建议测试预算</span>
          <strong>¥{{ recommendation.budget.min_yuan }}–{{ recommendation.budget.max_yuan }}</strong>
          <small>{{ recommendation.review_window_hours }} 小时后复查</small>
        </div>
        <ul><li v-for="item in recommendation.evidence || []" :key="item">{{ item }}</li></ul>
        <div class="stop-loss"><b>止损条件</b>{{ recommendation.stop_loss }}</div>
        <div class="decision-foot">
          <span>置信度：{{ recommendation.confidence === 'medium' ? '中' : '低' }}</span>
          <el-button type="primary" @click="confirmSuggestion">人工确认后执行</el-button>
        </div>
      </article>

      <article class="quality-panel">
        <div class="section-label">数据质量</div>
        <h3>{{ data.data_quality?.missing?.length ? '部分维度待补齐' : '核心口径已齐全' }}</h3>
        <p v-if="data.data_quality?.missing?.length">缺失：{{ data.data_quality.missing.join('、') }}</p>
        <dl>
          <div><dt>核销券数</dt><dd>{{ summary.verify_cert_count ?? '—' }}</dd></div>
          <div><dt>单张核销成本</dt><dd>{{ money(summary.cost_per_verify_fen) }}</dd></div>
          <div><dt>统计周期</dt><dd>{{ data.period?.label || '近7日' }}</dd></div>
        </dl>
      </article>
    </section>

    <section class="analysis-section">
      <div class="section-head"><div><span>素材效能</span><h2>钱花在哪条视频，核销是否跟上</h2></div><small>按消耗从高到低</small></div>
      <el-table :data="data.materials || []" stripe empty-text="等待广告素材接口返回可关联数据">
        <el-table-column prop="title" label="素材" min-width="240" show-overflow-tooltip />
        <el-table-column label="消耗" width="120"><template #default="{ row }">{{ money(row.ad_cost_fen) }}</template></el-table-column>
        <el-table-column label="广告成交" width="130"><template #default="{ row }">{{ money(row.ad_pay_gmv_fen) }}</template></el-table-column>
        <el-table-column prop="play_count" label="播放" width="110" />
        <el-table-column label="成交ROI" width="110"><template #default="{ row }">{{ ratio(calcRatio(row.ad_pay_gmv_fen, row.ad_cost_fen)) }}</template></el-table-column>
        <el-table-column label="判断" width="120"><template #default="{ row }"><el-tag :type="materialType(row)">{{ materialLabel(row) }}</el-tag></template></el-table-column>
      </el-table>
    </section>

    <section class="analysis-section demographics">
      <div class="section-head"><div><span>人群分析</span><h2>年龄 × 性别消耗结构</h2></div><small>下一步将叠加成交与核销</small></div>
      <div v-if="data.demographics?.length" class="demo-list">
        <div v-for="row in data.demographics" :key="row.age" class="demo-row">
          <b>{{ row.age }}</b>
          <div class="bar-track"><span class="male" :style="{ width: barWidth(row.male_cost_fen) }"></span></div>
          <span>男 {{ money(row.male_cost_fen) }}</span>
          <div class="bar-track"><span class="female" :style="{ width: barWidth(row.female_cost_fen) }"></span></div>
          <span>女 {{ money(row.female_cost_fen) }}</span>
        </div>
      </div>
      <el-empty v-else description="等待年龄性别接口数据" :image-size="70" />
    </section>

    <section class="split-analysis">
      <article class="analysis-section">
        <div class="section-head"><div><span>地域分析</span><h2>贵阳及周边消耗分布</h2></div><small>不虚构小区级数据</small></div>
        <div v-if="data.regions?.length" class="region-list">
          <div v-for="row in data.regions" :key="row.name" class="region-row">
            <b>{{ row.name }}</b><div class="bar-track"><span class="region-bar" :style="{ width: regionWidth(row.ad_cost_fen) }"></span></div>
            <span>{{ money(row.ad_cost_fen) }}</span><em>{{ percent(row.cost_rate) }}</em>
          </div>
        </div>
        <el-empty v-else description="等待地域接口数据" :image-size="70" />
      </article>
      <article class="analysis-section">
        <div class="section-head"><div><span>时间趋势</span><h2>每日消耗与广告成交</h2></div><small>核销存在滞后</small></div>
        <div v-if="data.trends?.length" class="trend-list">
          <div v-for="row in data.trends" :key="row.date" class="trend-row">
            <span>{{ row.date.slice(5) }}</span><div class="trend-bars"><i :style="{ width: trendWidth(row.ad_cost_fen) }"></i><b :style="{ width: trendWidth(row.ad_pay_gmv_fen) }"></b></div>
            <em>{{ money(row.ad_cost_fen) }} / {{ money(row.ad_pay_gmv_fen) }}</em>
          </div>
        </div>
        <el-empty v-else description="等待每日趋势数据" :image-size="70" />
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { lifeDataAnalysisApi } from '@/api/lifeDataAnalysis'

const loading = ref(false)
const data = ref<any>({ summary: {}, ai_recommendation: {}, data_quality: { missing: [] }, materials: [], demographics: [] })
const summary = computed(() => data.value.summary || {})
const recommendation = computed(() => data.value.ai_recommendation || {})
const money = (fen: number | null | undefined) => fen == null ? '—' : `¥${(fen / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const ratio = (value: number | null | undefined) => value == null ? '—' : Number(value).toFixed(2)
const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const calcRatio = (a: number, b: number) => b ? a / b : null
const formatTime = (value?: string) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
const actionLabel = (action?: string) => ({ increase_budget: '小步加投', maintain_and_observe: '维持观察', reduce_and_observe: '降低预算并观察', collect_more_data: '补齐数据' }[action || ''] || '等待判断')
const materialLabel = (row: any) => { const roi = calcRatio(row.ad_pay_gmv_fen, row.ad_cost_fen); return roi == null ? '待观察' : roi >= 1.5 ? '值得验证' : roi >= 1 ? '继续观察' : '建议止损' }
const materialType = (row: any) => { const roi = calcRatio(row.ad_pay_gmv_fen, row.ad_cost_fen); return roi != null && roi >= 1.5 ? 'success' : roi != null && roi < 1 ? 'danger' : 'warning' }
const maxDemoCost = computed(() => Math.max(1, ...(data.value.demographics || []).flatMap((row: any) => [row.male_cost_fen || 0, row.female_cost_fen || 0])))
const barWidth = (value: number) => `${Math.max(2, (Number(value || 0) / maxDemoCost.value) * 100)}%`
const maxRegionCost = computed(() => Math.max(1, ...(data.value.regions || []).map((row: any) => row.ad_cost_fen || 0)))
const regionWidth = (value: number) => `${Math.max(2, (Number(value || 0) / maxRegionCost.value) * 100)}%`
const maxTrendValue = computed(() => Math.max(1, ...(data.value.trends || []).flatMap((row: any) => [row.ad_cost_fen || 0, row.ad_pay_gmv_fen || 0])))
const trendWidth = (value: number) => `${Math.max(1, (Number(value || 0) / maxTrendValue.value) * 100)}%`

async function load() {
  loading.value = true
  try { const response = await lifeDataAnalysisApi.getOverview(); data.value = response.data.data }
  catch (_) { ElMessage.error('投流数据加载失败，请检查采集器状态') }
  finally { loading.value = false }
}
async function confirmSuggestion() {
  await ElMessageBox.alert('第一阶段不会自动投放。请按建议人工创建小额测试，并在任务管理中反馈消耗、核销和退款。', '人工确认', { confirmButtonText: '我知道了' })
}
onMounted(load)
</script>

<style scoped>
.investment-page{--ink:#142033;--paper:#f6f4ee;--line:#d8d3c8;--blue:#2457d6;--green:#087a55;--orange:#b55b19;--red:#b33a35;min-height:100%;padding:28px;background:var(--paper);color:var(--ink)}
.page-head{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:20px}.eyebrow,.section-label{font-size:11px;font-weight:800;letter-spacing:.14em;color:#687386}.page-head h1{font-size:38px;line-height:1;margin:7px 0}.subline{margin:0;color:#5d6674}.freshness{display:flex;align-items:center;gap:8px;font-size:13px}.freshness small{color:#737b86}.status-dot{width:8px;height:8px;border-radius:50%;background:var(--red)}.status-dot.online{background:var(--green)}
.decision-ledger{display:grid;grid-template-columns:1fr auto 1fr auto 1.25fr auto 1fr;align-items:stretch;margin:20px 0;border:1px solid var(--ink);background:#fff}.ledger-cell{padding:18px 20px;display:flex;flex-direction:column;gap:5px}.ledger-cell span{font-size:12px;color:#6d7480}.ledger-cell strong{font-size:27px;font-variant-numeric:tabular-nums}.ledger-cell em{font-style:normal;font-size:12px}.ledger-cell.verified{background:var(--ink);color:#fff}.ledger-cell.refund{color:var(--red)}.arrow{display:grid;place-items:center;color:#98a0ab}
.grid-main{display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:18px}.ai-decision,.quality-panel,.analysis-section{background:#fff;border:1px solid var(--line);padding:24px}.ai-decision{border-top:5px solid var(--orange)}.ai-decision.increase_budget{border-top-color:var(--green)}.ai-decision h2{font-size:25px;margin:9px 0 4px}.action-copy{color:#5f6875}.budget{display:flex;gap:16px;align-items:baseline;margin:18px 0;padding:14px 0;border-block:1px solid var(--line)}.budget strong{font-size:25px}.budget small{color:#6c7480}.ai-decision ul{padding-left:18px;line-height:1.8}.stop-loss{display:flex;gap:12px;padding:12px;background:#fff4e8;color:#764116}.decision-foot{display:flex;justify-content:space-between;align-items:center;margin-top:18px}.quality-panel h3{font-size:20px}.quality-panel dl>div{display:flex;justify-content:space-between;padding:13px 0;border-bottom:1px solid var(--line)}.quality-panel dd{font-weight:750;font-variant-numeric:tabular-nums}
.analysis-section{margin-top:18px}.section-head{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:18px}.section-head span{font-size:11px;letter-spacing:.12em;color:#6b7480}.section-head h2{margin:5px 0 0;font-size:20px}.section-head small{color:#7b838e}.demo-list{display:grid;gap:13px}.demo-row{display:grid;grid-template-columns:70px 1fr 120px 1fr 120px;gap:12px;align-items:center;font-size:13px}.bar-track{height:10px;background:#ebe8df;overflow:hidden}.bar-track span{display:block;height:100%}.male{background:var(--blue)}.female{background:var(--orange)}
.split-analysis{display:grid;grid-template-columns:1fr 1fr;gap:18px}.region-list,.trend-list{display:grid;gap:12px}.region-row{display:grid;grid-template-columns:90px 1fr 95px 55px;gap:10px;align-items:center;font-size:13px}.region-row em,.trend-row em{font-style:normal;color:#687386;text-align:right}.region-bar{background:var(--green)}.trend-row{display:grid;grid-template-columns:52px 1fr 165px;gap:10px;align-items:center;font-size:12px}.trend-bars{display:grid;gap:3px}.trend-bars i,.trend-bars b{display:block;height:5px;min-width:2px}.trend-bars i{background:var(--orange)}.trend-bars b{background:var(--green)}
@media(max-width:1100px){.decision-ledger{grid-template-columns:1fr 1fr}.arrow{display:none}.grid-main{grid-template-columns:1fr}.demo-row{grid-template-columns:60px 1fr 100px}.demo-row .bar-track:nth-of-type(2),.demo-row span:last-child{display:none}}
@media(max-width:900px){.split-analysis{grid-template-columns:1fr}}
@media(max-width:720px){.investment-page{padding:16px}.page-head{align-items:flex-start;flex-direction:column}.freshness{flex-wrap:wrap}.decision-ledger{grid-template-columns:1fr}.demo-row{grid-template-columns:55px 1fr 95px}.region-row{grid-template-columns:70px 1fr 85px}.region-row em{display:none}.trend-row{grid-template-columns:45px 1fr}.trend-row em{display:none}}
</style>
