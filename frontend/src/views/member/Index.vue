<template>
  <div class="member-page command-light-page">
    <section class="member-header">
      <div>
        <div class="eyebrow">协同 / 会员运营</div>
        <h1>会员运营</h1>
        <p>基于百胜小票会员线索、会员档案和回访名单，跟踪会员销售与触达状态。</p>
      </div>
      <div class="header-meta">
        <el-tag :type="statusTagType" effect="light" round>
          <span class="live-dot"></span>
          {{ statusText }}
        </el-tag>
        <span>最新小票日期：{{ summary.latest_ticket_date || "-" }}</span>
        <span>同步时间：{{ formatTime(summary.updated_at) }}</span>
      </div>
    </section>

    <el-alert
      v-if="!dataStatus.member_profile_synced"
      type="warning"
      show-icon
      :closable="false"
      title="会员档案暂未同步"
      description="当前先展示百胜小票中的会员线索；生日会员、沉睡会员、RFM分层需要会员档案同步后启用。"
    />

    <section class="summary-grid" v-loading="overviewLoading">
      <div class="metric-card" v-for="card in metricCards" :key="card.label">
        <div class="metric-label">{{ card.label }}</div>
        <div class="metric-value">{{ card.value }}</div>
        <div class="metric-sub">{{ card.sub }}</div>
      </div>
    </section>

    <section class="filter-band">
      <div class="filter-left">
        <el-radio-group v-model="preset" size="small" @change="applyPreset">
          <el-radio-button label="latest">最新日</el-radio-button>
          <el-radio-button label="last7">近7天</el-radio-button>
          <el-radio-button label="last30">近30天</el-radio-button>
          <el-radio-button label="custom">自定义</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          range-separator="至"
          :clearable="false"
          :disabled="preset !== 'custom'"
          size="small"
          @change="handleDateChange"
        />
        <el-input
          v-model="keyword"
          clearable
          size="small"
          class="keyword-input"
          :placeholder="['actions','profile','assets','transactions','segments','risks','wakeups'].includes(activeTab) ? '搜索会员编号/姓名' : '搜索会员线索/门店'"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
      </div>
      <div class="filter-actions">
        <el-button v-if="isSegmentTab && canExportSensitive" size="small" :icon="Download" @click="exportSegmentData">导出</el-button>
        <el-button v-if="isSegmentTab && canRebuildSegments" size="small" :loading="segmentRebuilding" @click="rebuildSegments">重算分层</el-button>
        <el-button v-if="activeTab === 'actions' && canRebuildSegments" size="small" :loading="actionRebuilding" @click="rebuildActions">生成今日行动</el-button>
        <el-button size="small" :icon="Search" type="primary" @click="fetchActiveTab">查询</el-button>
        <el-button size="small" :icon="Refresh" :loading="activeLoading" @click="refresh">刷新</el-button>
      </div>
    </section>

    <section class="table-panel">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane v-if="canViewSensitiveMembers" label="今日行动" name="actions">
          <div class="action-summary-grid" v-loading="actionOverviewLoading">
            <div class="action-summary-item"><span>待确认草稿</span><strong>{{ formatCount(actionOverview.draft_actions) }}</strong><small>联系前须主管确认</small></div>
            <div class="action-summary-item"><span>触达率</span><strong>{{ formatPercent(actionOverview.contact_rate) }}</strong><small>{{ actionOverview.contacted_actions || 0 }} / {{ actionOverview.confirmed_actions || 0 }} 已确认行动</small></div>
            <div class="action-summary-item"><span>到店率</span><strong>{{ formatPercent(actionOverview.arrival_rate) }}</strong><small>到店 / 已联系</small></div>
            <div class="action-summary-item"><span>成交率</span><strong>{{ formatPercent(actionOverview.conversion_rate) }}</strong><small>仅核验百胜小票</small></div>
            <div class="action-summary-item"><span>行动成交额</span><strong>{{ formatMoney(actionOverview.attributed_sales) }}</strong><small>已关联并核验小票</small></div>
            <div class="action-summary-item"><span>自然复购</span><strong>{{ formatCount(actionOverview.natural_repurchase_actions) }}</strong><small>时间相邻不归因行动</small></div>
          </div>
          <el-alert type="info" :closable="false" show-icon :title="actionOverview.attribution_note || '只有关联且核验通过的百胜小票计入行动成交，其他后续消费列为自然复购。'" class="segment-alert" />
          <el-table :data="actionRows" v-loading="actionLoading" border stripe size="small">
            <el-table-column prop="member_action.member_no" label="会员编号" min-width="125" />
            <el-table-column label="联系理由" min-width="210"><template #default="{ row }">{{ row.member_action?.contact_reason || "-" }}</template></el-table-column>
            <el-table-column label="建议商品" min-width="170"><template #default="{ row }">{{ productNames(row.member_action?.recommended_products) || "暂无有库存推荐" }}</template></el-table-column>
            <el-table-column label="责任人" width="120"><template #default="{ row }"><span>{{ row.assignee_name || "待主管选择" }}</span></template></el-table-column>
            <el-table-column label="状态" width="105"><template #default="{ row }"><el-tag size="small" :type="actionStatusType(row.status)">{{ actionStatusName(row.status) }}</el-tag></template></el-table-column>
            <el-table-column prop="due_date" label="截止日期" width="108" />
            <el-table-column label="操作" width="92" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openTask(row.id)">查看任务</el-button></template></el-table-column>
          </el-table>
          <el-empty v-if="!actionLoading && !actionRows.length" description="暂无VIP行动草稿，可点击生成今日行动" />
          <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next" :total="actionTotal" v-model:current-page="actionPage" v-model:page-size="actionPageSize" :page-sizes="[20,50,100]" @current-change="fetchMemberActions" @size-change="resetActionPage" /></div>
        </el-tab-pane>

        <el-tab-pane v-if="canViewSegments" label="会员分层" name="segments">
          <el-alert v-if="segmentError" type="error" :closable="false" show-icon :title="segmentError" class="segment-alert" />
          <div class="segment-summary-grid" v-loading="segmentOverviewLoading">
            <div class="segment-summary-item"><span>已分层会员</span><strong>{{ formatCount(segmentOverview.summary?.labelled_members) }}</strong></div>
            <div class="segment-summary-item"><span>风险会员</span><strong>{{ formatCount(segmentOverview.summary?.risk_members) }}</strong></div>
            <div class="segment-summary-item"><span>可唤醒</span><strong>{{ formatCount(segmentOverview.summary?.wakeup_members) }}</strong></div>
            <div class="segment-summary-item"><span>高价值</span><strong>{{ formatCount(segmentOverview.labels?.high_value) }}</strong></div>
            <div class="segment-summary-item"><span>高余额</span><strong>{{ formatCount(segmentOverview.labels?.high_balance) }}</strong></div>
            <div class="segment-summary-item"><span>沉睡会员</span><strong>{{ formatCount(segmentOverview.labels?.dormant) }}</strong></div>
          </div>
          <el-table :data="segmentRows" v-loading="segmentLoading" border stripe size="small">
            <el-table-column prop="member_no" label="会员编号" min-width="130" />
            <el-table-column prop="member_name" label="会员" min-width="100" />
            <el-table-column prop="store_name" label="归属门店" min-width="165" show-overflow-tooltip />
            <el-table-column label="当前余额" width="115" align="right"><template #default="{ row }">{{ formatSensitiveMoney(row, "current_balance") }}</template></el-table-column>
            <el-table-column label="累计消费" width="115" align="right"><template #default="{ row }">{{ formatSensitiveMoney(row, "total_amount") }}</template></el-table-column>
            <el-table-column label="最近消费" width="106"><template #default="{ row }">{{ row.sensitive_redacted ? "无权限" : (row.last_consume_date || "-") }}</template></el-table-column>
            <el-table-column label="会员标签" min-width="260">
              <template #default="{ row }"><div class="tag-list"><el-tag v-for="tag in row.labels" :key="tag.code" size="small" effect="light">{{ tag.name }}</el-tag><span v-if="!row.labels?.length" class="muted">暂无标签</span></div></template>
            </el-table-column>
            <el-table-column label="数据证据" width="92" align="center">
              <template #default="{ row }"><el-popover placement="left" :width="360" trigger="click"><pre class="evidence-text">{{ formatEvidence(row) }}</pre><template #reference><el-button link type="primary">查看</el-button></template></el-popover></template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!segmentLoading && !segmentRows.length" description="暂无会员分层快照" />
          <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next" :total="segmentTotal" v-model:current-page="segmentPage" v-model:page-size="segmentPageSize" :page-sizes="[20,50,100,200]" @current-change="fetchSegments" @size-change="resetSegmentPage" /></div>
        </el-tab-pane>

        <el-tab-pane v-if="canViewSegments" label="风险名单" name="risks">
          <el-alert v-if="segmentError" type="error" :closable="false" show-icon :title="segmentError" class="segment-alert" />
          <el-table :data="riskRows" v-loading="riskLoading" border stripe size="small">
            <el-table-column prop="member_no" label="会员编号" min-width="130" />
            <el-table-column prop="member_name" label="会员" min-width="100" />
            <el-table-column prop="store_name" label="归属门店" min-width="165" show-overflow-tooltip />
            <el-table-column label="当前余额" width="115" align="right"><template #default="{ row }"><span :class="{ negative: !row.sensitive_redacted && row.current_balance < 0 }">{{ formatSensitiveMoney(row, "current_balance") }}</span></template></el-table-column>
            <el-table-column label="最近消费" width="106"><template #default="{ row }">{{ row.sensitive_redacted ? "无权限" : (row.last_consume_date || "-") }}</template></el-table-column>
            <el-table-column label="风险" min-width="300"><template #default="{ row }"><div class="tag-list"><el-tag v-for="risk in row.risks" :key="risk.code" :type="riskTagType(risk.severity)" size="small" effect="light">{{ risk.name }}</el-tag></div></template></el-table-column>
            <el-table-column label="数据证据" width="92" align="center"><template #default="{ row }"><el-popover placement="left" :width="360" trigger="click"><pre class="evidence-text">{{ formatEvidence(row) }}</pre><template #reference><el-button link type="primary">查看</el-button></template></el-popover></template></el-table-column>
          </el-table>
          <el-empty v-if="!riskLoading && !riskRows.length" description="当前没有会员风险" />
          <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next" :total="riskTotal" v-model:current-page="segmentPage" v-model:page-size="segmentPageSize" :page-sizes="[20,50,100,200]" @current-change="fetchRisks" @size-change="resetSegmentPage" /></div>
        </el-tab-pane>

        <el-tab-pane v-if="canViewSegments" label="唤醒名单" name="wakeups">
          <el-alert v-if="segmentError" type="error" :closable="false" show-icon :title="segmentError" class="segment-alert" />
          <el-table :data="wakeupRows" v-loading="wakeupLoading" border stripe size="small">
            <el-table-column prop="wakeup_priority" label="优先级" width="72" align="center" />
            <el-table-column prop="member_no" label="会员编号" min-width="125" />
            <el-table-column prop="member_name" label="会员" min-width="95" />
            <el-table-column prop="store_name" label="建议门店" min-width="155" show-overflow-tooltip />
            <el-table-column label="联系理由" min-width="220"><template #default="{ row }">{{ itemNames(row.wakeup_reasons) || "-" }}</template></el-table-column>
            <el-table-column label="偏好品类/款式" min-width="170"><template #default="{ row }">{{ preferenceNames(row.preferences) || "数据待补充" }}</template></el-table-column>
            <el-table-column label="建议商品" min-width="170"><template #default="{ row }">{{ productNames(row.suggested_products) || "数据待补充" }}</template></el-table-column>
            <el-table-column label="责任人" width="118"><template #default="{ row }"><el-tag v-if="row.responsibility_status === 'unconfirmed'" type="warning" size="small">待确认责任人</el-tag><span v-else>{{ row.responsible_employee_no || "未分配" }}</span></template></el-table-column>
            <el-table-column label="数据证据" width="92" align="center"><template #default="{ row }"><el-popover placement="left" :width="360" trigger="click"><pre class="evidence-text">{{ formatEvidence(row) }}</pre><template #reference><el-button link type="primary">查看</el-button></template></el-popover></template></el-table-column>
          </el-table>
          <el-empty v-if="!wakeupLoading && !wakeupRows.length" description="当前没有可唤醒会员" />
          <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next" :total="wakeupTotal" v-model:current-page="segmentPage" v-model:page-size="segmentPageSize" :page-sizes="[20,50,100,200]" @current-change="fetchWakeups" @size-change="resetSegmentPage" /></div>
        </el-tab-pane>

        <el-tab-pane label="VIP销售" name="sales">
          <div class="vip-sales-grid" v-loading="salesLoading">
            <div class="sales-metric" v-for="card in vipSalesCards" :key="card.label">
              <span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.sub }}</small>
            </div>
          </div>
          <div class="sales-analysis-layout">
            <div class="analysis-block">
              <div class="block-title"><h3>VIP门店排行</h3><span>{{ vipSales.date_range?.start_date || "-" }} 至 {{ vipSales.date_range?.end_date || "-" }}</span></div>
              <el-table :data="vipSales.stores || []" border stripe size="small" v-loading="salesLoading">
                <el-table-column type="index" label="排名" width="62" align="center" />
                <el-table-column prop="store_name" label="门店" min-width="170"><template #default="{ row }"><span>{{ row.store_name }}</span><span class="muted-code">{{ row.store_code }}</span></template></el-table-column>
                <el-table-column label="VIP销售额" width="120" align="right"><template #default="{ row }">{{ formatMoney(row.vip_sales) }}</template></el-table-column>
                <el-table-column prop="vip_orders" label="订单" width="72" align="right" />
                <el-table-column label="客单价" width="100" align="right"><template #default="{ row }">{{ formatMoney(row.avg_order_value) }}</template></el-table-column>
                <el-table-column prop="attachment_rate" label="连带率" width="82" align="right" />
                <el-table-column label="平均折扣" width="92" align="right"><template #default="{ row }">{{ formatPercent(row.avg_discount_rate) }}</template></el-table-column>
                <el-table-column label="退货率" width="82" align="right"><template #default="{ row }">{{ formatPercent(row.return_rate) }}</template></el-table-column>
              </el-table>
            </div>
            <div class="analysis-block compact-trend">
              <div class="block-title"><h3>VIP销售趋势</h3><span>按日</span></div>
              <el-table :data="vipSales.trend || []" border stripe size="small" max-height="360" v-loading="salesLoading">
                <el-table-column prop="biz_date" label="日期" width="104" />
                <el-table-column label="销售额" min-width="100" align="right"><template #default="{ row }">{{ formatMoney(row.vip_sales) }}</template></el-table-column>
                <el-table-column prop="vip_orders" label="订单" width="68" align="right" />
                <el-table-column prop="attachment_rate" label="连带率" width="76" align="right" />
              </el-table>
            </div>
          </div>
          <div class="pending-strip">
            <span><b>VIP毛利</b><el-tag size="small" type="info">待接入</el-tag> 小票与商品成本尚无可靠逐单关联</span>
            <span><b>品类/款式</b><el-tag size="small" type="info">待接入</el-tag> 商品明细暂不能可靠关联VIP小票</span>
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="canViewSensitiveMembers" label="VIP资产" name="assets">
          <el-table :data="assetRows" v-loading="assetLoading" border stripe size="small">
            <el-table-column prop="member_no" label="会员编号" min-width="130" />
            <el-table-column prop="member_name" label="会员" min-width="100" />
            <el-table-column prop="phone" label="手机号" width="125" />
            <el-table-column prop="register_store_name" label="注册门店" min-width="170" show-overflow-tooltip />
            <el-table-column prop="member_level" label="等级" width="90" />
            <el-table-column label="当前余额" width="125" sortable align="right"><template #default="{ row }"><strong :class="{ negative: !row.sensitive_redacted && row.current_balance < 0 }">{{ formatSensitiveMoney(row, "current_balance") }}</strong></template></el-table-column>
            <el-table-column label="累计消费" width="125" align="right"><template #default="{ row }">{{ formatSensitiveMoney(row, "total_amount") }}</template></el-table-column>
            <el-table-column prop="last_consume_date" label="最近消费" width="110" />
            <el-table-column label="状态" width="96"><template #default="{ row }"><el-tag :type="assetStatusType(row.balance_status)" size="small">{{ assetStatusName(row.balance_status) }}</el-tag></template></el-table-column>
          </el-table>
          <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next" :total="assetTotal" v-model:current-page="assetPage" v-model:page-size="assetPageSize" :page-sizes="[20,50,100,200]" @current-change="fetchAssets" @size-change="resetAssetPage" /></div>
        </el-tab-pane>

        <el-tab-pane v-if="canViewSensitiveMembers" label="余额变动" name="transactions">
          <el-table :data="transactionRows" v-loading="transactionLoading" border stripe size="small">
            <el-table-column prop="occurred_at" label="发生时间" width="160" />
            <el-table-column prop="member_no" label="会员编号" min-width="125" />
            <el-table-column prop="member_name" label="会员" min-width="100" />
            <el-table-column prop="store_name" label="门店" min-width="160" show-overflow-tooltip />
            <el-table-column label="类型" width="90"><template #default="{ row }">{{ transactionType(row.business_type) }}</template></el-table-column>
            <el-table-column label="变动前" width="110" align="right"><template #default="{ row }">{{ formatMoney(row.money_before) }}</template></el-table-column>
            <el-table-column label="变动金额" width="110" align="right"><template #default="{ row }"><strong :class="row.money_change < 0 ? 'negative' : 'positive'">{{ formatMoney(row.money_change) }}</strong></template></el-table-column>
            <el-table-column label="变动后" width="110" align="right"><template #default="{ row }">{{ formatMoney(row.money_after) }}</template></el-table-column>
            <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
          </el-table>
          <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next" :total="transactionTotal" v-model:current-page="transactionPage" v-model:page-size="transactionPageSize" :page-sizes="[20,50,100,200]" @current-change="fetchTransactions" @size-change="resetTransactionPage" /></div>
        </el-tab-pane>

        <el-tab-pane label="小票会员线索" name="pos">
          <el-table :data="posRows" v-loading="posLoading" border stripe size="small">
            <el-table-column type="index" label="排名" width="68" align="center" />
            <el-table-column prop="member_key" label="会员标识" min-width="130" />
            <el-table-column prop="last_store_name" label="最近门店" min-width="190" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.last_store_name }}</span>
                <span class="muted-code">{{ row.last_store_code }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="total_sales" label="销售额" width="120" sortable align="right">
              <template #default="{ row }">{{ formatMoney(row.total_sales) }}</template>
            </el-table-column>
            <el-table-column prop="total_actual" label="实收金额" width="120" sortable align="right">
              <template #default="{ row }">{{ formatMoney(row.total_actual) }}</template>
            </el-table-column>
            <el-table-column prop="order_count" label="订单数" width="90" sortable align="right" />
            <el-table-column prop="sales_qty" label="件数" width="90" sortable align="right">
              <template #default="{ row }">{{ formatQty(row.sales_qty) }}</template>
            </el-table-column>
            <el-table-column prop="avg_order_value" label="客单价" width="110" sortable align="right">
              <template #default="{ row }">{{ formatMoney(row.avg_order_value) }}</template>
            </el-table-column>
            <el-table-column prop="first_consume_date" label="首次消费" width="112" />
            <el-table-column prop="last_consume_date" label="最近消费" width="112" />
          </el-table>
          <div class="pagination-row">
            <el-pagination
              background
              layout="total, sizes, prev, pager, next, jumper"
              :total="posTotal"
              v-model:current-page="posPage"
              v-model:page-size="pageSize"
              :page-sizes="[20, 50, 100, 200]"
              @current-change="fetchPosMembers"
              @size-change="handlePageSizeChange"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="canViewSensitiveMembers" label="会员档案" name="profile">
          <el-table :data="profileRows" v-loading="profileLoading" border stripe size="small">
            <el-table-column prop="member_no" label="会员编号" min-width="130" />
            <el-table-column prop="member_name" label="会员姓名" min-width="110" />
            <el-table-column prop="phone" label="手机号" width="130" />
            <el-table-column prop="member_level" label="等级" width="100" />
            <el-table-column prop="register_store_name" label="注册门店" min-width="180" show-overflow-tooltip />
            <el-table-column prop="total_amount" label="累计消费" width="120" align="right">
              <template #default="{ row }">{{ formatMoney(row.total_amount) }}</template>
            </el-table-column>
            <el-table-column prop="total_count" label="消费次数" width="100" align="right" />
            <el-table-column prop="last_consume_date" label="最近消费" width="112" />
            <el-table-column prop="rfm_segment" label="分层" width="110" />
          </el-table>
          <el-empty v-if="!profileLoading && profileRows.length === 0" description="会员档案未同步，暂无档案数据" />
          <div class="pagination-row" v-if="profileTotal > 0">
            <el-pagination
              background
              layout="total, sizes, prev, pager, next, jumper"
              :total="profileTotal"
              v-model:current-page="profilePage"
              v-model:page-size="profilePageSize"
              :page-sizes="[20, 50, 100, 200]"
              @current-change="fetchProfiles"
              @size-change="handleProfilePageSizeChange"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="canViewSensitiveMembers" label="回访名单" name="visits">
          <el-table :data="visitRows" v-loading="visitLoading" border stripe size="small">
            <el-table-column prop="visit_date" label="回访日期" width="112" />
            <el-table-column prop="member_no" label="会员编号" min-width="130" />
            <el-table-column prop="member_name" label="会员姓名" min-width="110" />
            <el-table-column prop="store_name" label="建议门店" min-width="170" show-overflow-tooltip />
            <el-table-column prop="visit_reason" label="原因" width="110" />
            <el-table-column prop="priority" label="优先级" width="90" align="right" />
            <el-table-column prop="sleep_days" label="沉睡天数" width="100" align="right" />
            <el-table-column prop="visit_status" label="状态" width="100" />
            <el-table-column prop="ai_suggestion" label="建议话术" min-width="220" show-overflow-tooltip />
          </el-table>
          <el-empty v-if="!visitLoading && visitRows.length === 0" description="回访名单未生成，暂无回访数据" />
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Download, Refresh, Search } from "@element-plus/icons-vue";
import { memberApi } from "@/api/member";
import { isRouteRequestCanceled } from "@/api/request";
import { useAuthStore } from "@/stores/auth";

type Preset = "latest" | "last7" | "last30" | "custom";
type TabName = "actions" | "segments" | "risks" | "wakeups" | "sales" | "assets" | "transactions" | "pos" | "profile" | "visits";

const authStore = useAuthStore();
const router = useRouter();

const overviewLoading = ref(false);
const posLoading = ref(false);
const profileLoading = ref(false);
const visitLoading = ref(false);
const assetLoading = ref(false);
const transactionLoading = ref(false);
const salesLoading = ref(false);
const segmentOverviewLoading = ref(false);
const segmentLoading = ref(false);
const riskLoading = ref(false);
const wakeupLoading = ref(false);
const segmentRebuilding = ref(false);
const actionOverviewLoading = ref(false);
const actionLoading = ref(false);
const actionRebuilding = ref(false);
const activeTab = ref<TabName>(authStore.hasPermission("member:sensitive:view") ? "actions" : "sales");
const preset = ref<Preset>("latest");
const keyword = ref("");
const dateRange = ref<[string, string]>(["", ""]);
const pageSize = ref(20);
const posPage = ref(1);
const posTotal = ref(0);
const profilePage = ref(1);
const profilePageSize = ref(20);
const profileTotal = ref(0);
const summary = ref<any>({});
const dataStatus = ref<any>({});
const posRows = ref<any[]>([]);
const profileRows = ref<any[]>([]);
const visitRows = ref<any[]>([]);
const assetOverview = ref<any>({});
const assetRows = ref<any[]>([]); const assetTotal = ref(0); const assetPage = ref(1); const assetPageSize = ref(20);
const transactionRows = ref<any[]>([]); const transactionTotal = ref(0); const transactionPage = ref(1); const transactionPageSize = ref(20);
const vipSales = ref<any>({ summary: {}, stores: [], trend: [] });
const segmentOverview = ref<any>({ summary: {}, labels: {}, risks: {} });
const segmentRows = ref<any[]>([]);
const riskRows = ref<any[]>([]);
const wakeupRows = ref<any[]>([]);
const segmentTotal = ref(0);
const riskTotal = ref(0);
const wakeupTotal = ref(0);
const segmentPage = ref(1);
const segmentPageSize = ref(20);
const segmentError = ref("");
const actionOverview = ref<any>({});
const actionRows = ref<any[]>([]);
const actionTotal = ref(0);
const actionPage = ref(1);
const actionPageSize = ref(20);

function parseDate(value: string) {
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime()) ? new Date() : d;
}

function toDateString(d: Date) {
  const copy = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return copy.toISOString().slice(0, 10);
}

function shiftDate(value: string, days: number) {
  const d = parseDate(value);
  d.setDate(d.getDate() + days);
  return toDateString(d);
}

function formatMoney(value: any) {
  const n = Number(value || 0);
  if (Math.abs(n) >= 10000) return `¥${(n / 10000).toFixed(2)}万`;
  return `¥${Math.round(n).toLocaleString("zh-CN")}`;
}

function formatSensitiveMoney(row: any, key: string) {
  return row?.sensitive_redacted ? "无权限" : formatMoney(row?.[key]);
}

function formatOverviewSensitiveMoney(value: any) {
  return assetOverview.value.sensitive_redacted ? "无权限" : formatMoney(value);
}

function formatQty(value: any) {
  const n = Number(value || 0);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function formatPercent(value: any) {
  const n = Number(value || 0);
  return n ? `${(n * 100).toFixed(1)}%` : "0%";
}

function formatTime(value: any) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

function formatCount(value: any) { return Number(value || 0).toLocaleString("zh-CN"); }
function itemNames(items: any[]) { return (items || []).map(item => item?.name || item?.code).filter(Boolean).join("、"); }
function preferenceNames(items: any[]) { return (items || []).map(item => item?.name || item?.product_name).filter(Boolean).join("、"); }
function productNames(items: any[]) { return (items || []).map(item => item?.product_name || item?.product_code).filter(Boolean).join("、"); }
function riskTagType(value: string) { return value === "critical" ? "danger" : value === "risk" ? "warning" : "info"; }
function formatEvidence(row: any) { return JSON.stringify({ labels: row.labels || [], risks: row.risks || [], metrics: row.metrics || {}, data_quality: row.data_quality || {} }, null, 2); }
function actionStatusName(value: string) { return ({ draft: "待确认", pending: "待处理", processing: "处理中", feedback_submitted: "待复查", review_passed: "复查通过", overdue: "已逾期", closed: "已关闭", cancelled: "已取消" } as any)[value] || value; }
function actionStatusType(value: string) { return ({ draft: "warning", pending: "info", processing: "primary", feedback_submitted: "warning", review_passed: "success", overdue: "danger", closed: "info", cancelled: "info" } as any)[value] || "info"; }

const statusText = computed(() => (dataStatus.value.member_profile_synced ? "会员档案已同步" : "展示小票会员线索"));
const statusTagType = computed(() => (dataStatus.value.member_profile_synced ? "success" : "warning"));
const isSegmentTab = computed(() => ["segments", "risks", "wakeups"].includes(activeTab.value));
const canViewSegments = computed(() => authStore.hasPermission("member:segment:view"));
const canViewSensitiveMembers = computed(() => authStore.hasPermission("member:sensitive:view"));
const canExportSensitive = computed(() => authStore.hasPermission("member:sensitive:export"));
const canRebuildSegments = computed(() => authStore.hasPermission("member:segment:rebuild"));
const activeLoading = computed(() => {
  if (activeTab.value === "actions") return actionLoading.value;
  if (activeTab.value === "segments") return segmentLoading.value;
  if (activeTab.value === "risks") return riskLoading.value;
  if (activeTab.value === "wakeups") return wakeupLoading.value;
  if (activeTab.value === "assets") return assetLoading.value;
  if (activeTab.value === "sales") return salesLoading.value;
  if (activeTab.value === "transactions") return transactionLoading.value;
  if (activeTab.value === "profile") return profileLoading.value;
  if (activeTab.value === "visits") return visitLoading.value;
  return posLoading.value;
});

async function fetchMemberActions() {
  if (!canViewSensitiveMembers.value) return;
  actionOverviewLoading.value = true;
  actionLoading.value = true;
  try {
    const params: any = { page: actionPage.value, page_size: actionPageSize.value };
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const [overviewResponse, listResponse] = await Promise.all([
      memberApi.getActionOverview({ days: 30 }),
      memberApi.listActions(params),
    ]);
    if (!overviewResponse.data?.success) throw new Error(overviewResponse.data?.message || "会员行动概览加载失败");
    if (!listResponse.data?.success) throw new Error(listResponse.data?.message || "会员行动列表加载失败");
    actionOverview.value = overviewResponse.data.data || {};
    actionRows.value = listResponse.data.data?.items || [];
    actionTotal.value = listResponse.data.data?.total || 0;
  } catch (e: any) {
    if (isRouteRequestCanceled(e)) return;
    ElMessage.error(e?.message || "会员行动加载失败");
  } finally {
    actionOverviewLoading.value = false;
    actionLoading.value = false;
  }
}

function resetActionPage() { actionPage.value = 1; fetchMemberActions(); }
function openTask(id: number) { router.push(`/app/task/${id}`); }

async function rebuildActions() {
  actionRebuilding.value = true;
  try {
    const { data } = await memberApi.rebuildActions();
    if (!data?.success) throw new Error(data?.message || "今日行动生成失败");
    ElMessage.success(`已生成 ${data.data?.created_count || 0} 个行动草稿`);
    actionPage.value = 1;
    await fetchMemberActions();
  } catch (e: any) {
    if (isRouteRequestCanceled(e)) return;
    ElMessage.error(e?.message || "今日行动生成失败");
  } finally {
    actionRebuilding.value = false;
  }
}

const metricCards = computed(() => {
  const cards = [];
  if (canViewSensitiveMembers.value) {
    cards.push(
      { label: "VIP正余额", value: formatOverviewSensitiveMoney(assetOverview.value.total_balance), sub: "百胜会员主档 CZ_DQJE" },
      { label: "有余额会员", value: Number(assetOverview.value.balance_member_count || 0).toLocaleString("zh-CN"), sub: `${assetOverview.value.negative_balance_count || 0} 人负余额单列` },
      { label: "90天沉睡余额", value: formatOverviewSensitiveMoney(assetOverview.value.dormant_balance_90d), sub: `${assetOverview.value.dormant_member_90d || 0} 位会员` },
      { label: "近30天充值", value: formatOverviewSensitiveMoney(assetOverview.value.recharge_30d), sub: `${assetOverview.value.recharge_member_30d || 0} 位充值会员` },
    );
  }
  cards.push(
    { label: "会员档案数", value: Number(summary.value.profile_members || 0).toLocaleString("zh-CN"), sub: "dim_member" },
    { label: "会员销售额", value: formatMoney(summary.value.member_sales), sub: `占比 ${formatPercent(summary.value.member_sales_ratio)}` },
  );
  return cards;
});

function metricValue(key: string) { return vipSales.value.summary?.[key]?.value; }
function metricStatus(key: string) { return vipSales.value.summary?.[key]?.status || "pending_data"; }
const vipSalesCards = computed(() => [
  { label: "VIP销售额", value: formatMoney(metricValue("vip_sales_amount")), sub: `占比 ${formatPercent(metricValue("vip_sales_ratio"))}` },
  { label: "VIP实收", value: formatMoney(metricValue("vip_actual_amount")), sub: "百胜小票" },
  { label: "订单 / 件数", value: `${metricValue("order_count") || 0} / ${formatQty(metricValue("sales_quantity"))}`, sub: "有效VIP小票" },
  { label: "客单价", value: formatMoney(metricValue("avg_order_value")), sub: "销售额 / 订单" },
  { label: "连带率", value: Number(metricValue("attachment_rate") || 0).toFixed(2), sub: "件数 / 订单" },
  { label: "复购率", value: formatPercent(metricValue("repurchase_rate")), sub: `${metricValue("repurchase_member_count") || 0} 位复购会员` },
  { label: "平均折扣", value: formatPercent(metricValue("avg_discount_rate")), sub: "销售额 / 吊牌额" },
  { label: "退货率", value: formatPercent(metricValue("return_rate")), sub: `${formatMoney(metricValue("return_amount"))} 退货` },
  { label: "充值消费转化", value: formatPercent(metricValue("recharge_consume_conversion_rate")), sub: `${metricValue("recharge_consume_member_count") || 0} / ${metricValue("recharge_member_count") || 0} 人` },
  { label: "VIP毛利", value: metricStatus("gross_profit") === "pending_data" ? "待接入" : formatMoney(metricValue("gross_profit")), sub: "成本逐单关联" },
]);

async function fetchOverview() {
  overviewLoading.value = true;
  try {
    const { data } = await memberApi.getOverview();
    if (!data?.success) {
      ElMessage.error(data?.message || "会员概览加载失败");
      return;
    }
    summary.value = data.data?.summary || {};
    dataStatus.value = data.data?.data_status || {};
    if (canViewSensitiveMembers.value) {
      const { data: assetData } = await memberApi.getAssetOverview();
      assetOverview.value = {
        ...(assetData?.data?.summary || {}),
        sensitive_redacted: Boolean(assetData?.data?.sensitive_redacted || assetData?.data?.summary?.sensitive_redacted),
      };
    } else {
      assetOverview.value = {};
    }
    if (!dateRange.value[0] && summary.value.latest_ticket_date) applyPreset();
  } catch (e: any) {
    if (isRouteRequestCanceled(e)) return;
    ElMessage.error(e?.message || "会员概览加载失败");
  } finally {
    overviewLoading.value = false;
  }
}

async function fetchSegmentOverview() {
  if (!canViewSegments.value) return;
  segmentOverviewLoading.value = true;
  try {
    const { data } = await memberApi.getSegmentOverview();
    if (!data?.success) throw new Error(data?.message || "会员分层概览加载失败");
    segmentOverview.value = data.data || { summary: {}, labels: {}, risks: {} };
  } catch (e: any) {
    if (isRouteRequestCanceled(e)) return;
    segmentError.value = e?.message || "会员分层概览加载失败";
  } finally {
    segmentOverviewLoading.value = false;
  }
}

async function fetchSegmentKind(kind: "segments" | "risks" | "wakeups") {
  if (!canViewSegments.value) return;
  const loading = kind === "segments" ? segmentLoading : kind === "risks" ? riskLoading : wakeupLoading;
  loading.value = true;
  segmentError.value = "";
  try {
    const params: any = { page: segmentPage.value, page_size: segmentPageSize.value };
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const requestCall = kind === "segments" ? memberApi.listSegments : kind === "risks" ? memberApi.listSegmentRisks : memberApi.listWakeups;
    const { data } = await requestCall(params);
    if (!data?.success) throw new Error(data?.message || "会员名单加载失败");
    const payload = data.data || {};
    if (kind === "segments") { segmentRows.value = payload.items || []; segmentTotal.value = payload.total || 0; }
    if (kind === "risks") { riskRows.value = payload.items || []; riskTotal.value = payload.total || 0; }
    if (kind === "wakeups") { wakeupRows.value = payload.items || []; wakeupTotal.value = payload.total || 0; }
  } catch (e: any) {
    if (isRouteRequestCanceled(e)) return;
    segmentError.value = e?.message || "会员名单加载失败";
  } finally {
    loading.value = false;
  }
}

function fetchSegments() { return fetchSegmentKind("segments"); }
function fetchRisks() { return fetchSegmentKind("risks"); }
function fetchWakeups() { return fetchSegmentKind("wakeups"); }
function resetSegmentPage() { segmentPage.value = 1; fetchActiveTab(); }

async function rebuildSegments() {
  segmentRebuilding.value = true;
  try {
    const { data } = await memberApi.rebuildSegments();
    if (!data?.success) throw new Error(data?.message || "会员分层重算失败");
    ElMessage.success(`分层已重算：${data.data?.member_count || 0} 位会员`);
    await fetchSegmentOverview();
    await fetchActiveTab();
  } catch (e: any) {
    if (isRouteRequestCanceled(e)) return;
    ElMessage.error(e?.message || "会员分层重算失败");
  } finally {
    segmentRebuilding.value = false;
  }
}

async function exportSegmentData() {
  const kind = activeTab.value === "risks" ? "risks" : activeTab.value === "wakeups" ? "wakeups" : "segments";
  try {
    const response = await memberApi.exportSegments({ kind, keyword: keyword.value.trim() || undefined });
    const blob = new Blob([response.data], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `member_${kind}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (e: any) {
    if (isRouteRequestCanceled(e)) return;
    ElMessage.error(e?.message || "会员数据导出失败");
  }
}

async function fetchAssets() {
  assetLoading.value = true;
  try {
    const params: any = { page: assetPage.value, page_size: assetPageSize.value };
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await memberApi.listAssets(params);
    assetRows.value = data?.data?.items || []; assetTotal.value = data?.data?.total || 0;
  } catch (e) {
    if (!isRouteRequestCanceled(e)) throw e;
  } finally { assetLoading.value = false; }
}

async function fetchTransactions() {
  transactionLoading.value = true;
  try {
    const params: any = { page: transactionPage.value, page_size: transactionPageSize.value };
    if (dateRange.value[0]) params.start_date = dateRange.value[0];
    if (dateRange.value[1]) params.end_date = dateRange.value[1];
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await memberApi.listAssetTransactions(params);
    transactionRows.value = data?.data?.items || []; transactionTotal.value = data?.data?.total || 0;
  } catch (e) {
    if (!isRouteRequestCanceled(e)) throw e;
  } finally { transactionLoading.value = false; }
}

async function fetchSalesAnalysis() {
  salesLoading.value = true;
  try {
    const params: any = {};
    if (dateRange.value[0]) params.start_date = dateRange.value[0];
    if (dateRange.value[1]) params.end_date = dateRange.value[1];
    const { data } = await memberApi.getSalesAnalysis(params);
    if (!data?.success) return ElMessage.error(data?.message || "VIP销售分析加载失败");
    vipSales.value = data.data || { summary: {}, stores: [], trend: [] };
  } catch (e: any) {
    if (!isRouteRequestCanceled(e)) ElMessage.error(e?.message || "VIP销售分析加载失败");
  }
  finally { salesLoading.value = false; }
}

function resetAssetPage() { assetPage.value = 1; fetchAssets(); }
function resetTransactionPage() { transactionPage.value = 1; fetchTransactions(); }
function assetStatusName(value: string) { return ({ negative: "负余额", dormant: "沉睡", high: "高余额", normal: "正常" } as any)[value] || value; }
function assetStatusType(value: string) { return ({ negative: "danger", dormant: "warning", high: "success", normal: "info" } as any)[value] || "info"; }
function transactionType(value: string) { return ({ recharge: "充值", consume: "消费", refund: "退款" } as any)[value] || value; }

function applyPreset() {
  const anchor = summary.value.latest_ticket_date || toDateString(new Date());
  if (preset.value === "latest") dateRange.value = [anchor, anchor];
  if (preset.value === "last7") dateRange.value = [shiftDate(anchor, -6), anchor];
  if (preset.value === "last30") dateRange.value = [shiftDate(anchor, -29), anchor];
  if (preset.value !== "custom") fetchDateSensitiveTab();
}

function handleDateChange() {
  if (preset.value === "custom") fetchDateSensitiveTab();
}

function fetchDateSensitiveTab() {
  if (activeTab.value === "sales") return fetchSalesAnalysis();
  if (activeTab.value === "transactions") return fetchTransactions();
  if (activeTab.value === "pos") return fetchPosMembers();
}

async function fetchPosMembers() {
  posLoading.value = true;
  try {
    const params: any = {
      page: posPage.value,
      page_size: pageSize.value,
    };
    if (dateRange.value[0]) params.start_date = dateRange.value[0];
    if (dateRange.value[1]) params.end_date = dateRange.value[1];
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await memberApi.listPosMembers(params);
    if (!data?.success) {
      ElMessage.error(data?.message || "会员线索加载失败");
      return;
    }
    const payload = data.data || {};
    posRows.value = payload.items || [];
    posTotal.value = payload.total || 0;
    if (payload.date_range?.start_date && payload.date_range?.end_date) {
      dateRange.value = [payload.date_range.start_date, payload.date_range.end_date];
    }
  } catch (e: any) {
    if (isRouteRequestCanceled(e)) return;
    ElMessage.error(e?.message || "会员线索加载失败");
  } finally {
    posLoading.value = false;
  }
}

async function fetchProfiles() {
  profileLoading.value = true;
  try {
    const params: any = { page: profilePage.value, page_size: profilePageSize.value };
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await memberApi.listMembers(params);
    const payload = data?.success ? (data.data || {}) : {};
    profileRows.value = payload.items || [];
    profileTotal.value = payload.total || 0;
  } catch (e) {
    if (!isRouteRequestCanceled(e)) throw e;
  } finally {
    profileLoading.value = false;
  }
}

async function fetchVisits() {
  visitLoading.value = true;
  try {
    const { data } = await memberApi.listVisits({ page: 1, page_size: 100 });
    visitRows.value = data?.success ? (data.data?.items || []) : [];
  } catch (e) {
    if (!isRouteRequestCanceled(e)) throw e;
  } finally {
    visitLoading.value = false;
  }
}

function fetchActiveTab() {
  if (activeTab.value === "actions") return fetchMemberActions();
  if (activeTab.value === "segments") return fetchSegments();
  if (activeTab.value === "risks") return fetchRisks();
  if (activeTab.value === "wakeups") return fetchWakeups();
  if (activeTab.value === "sales") return fetchSalesAnalysis();
  if (activeTab.value === "assets") return fetchAssets();
  if (activeTab.value === "transactions") return fetchTransactions();
  if (activeTab.value === "profile") return fetchProfiles();
  if (activeTab.value === "visits") return fetchVisits();
  return fetchPosMembers();
}

async function refresh() {
  const overviewRequests = [fetchOverview()];
  if (canViewSegments.value) overviewRequests.push(fetchSegmentOverview());
  await Promise.all(overviewRequests);
  await fetchActiveTab();
}

function handleTabChange() {
  if (activeTab.value === "actions") actionPage.value = 1;
  if (isSegmentTab.value) segmentPage.value = 1;
  fetchActiveTab();
}

function handleSearch() {
  if (activeTab.value === "actions") actionPage.value = 1;
  if (isSegmentTab.value) segmentPage.value = 1;
  if (activeTab.value === "assets") assetPage.value = 1;
  if (activeTab.value === "transactions") transactionPage.value = 1;
  if (activeTab.value === "profile") profilePage.value = 1;
  if (activeTab.value === "pos") posPage.value = 1;
  fetchActiveTab();
}

function handlePageSizeChange() {
  posPage.value = 1;
  fetchPosMembers();
}

function handleProfilePageSizeChange() {
  profilePage.value = 1;
  fetchProfiles();
}

onMounted(async () => {
  const overviewRequests = [fetchOverview()];
  if (canViewSegments.value) overviewRequests.push(fetchSegmentOverview());
  await Promise.all(overviewRequests);
  if (canViewSensitiveMembers.value) await fetchMemberActions();
  else await fetchSalesAnalysis();
});
</script>

<style scoped>
.member-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  color: #111827;
}

.member-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.eyebrow {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}

.member-header h1 {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
  font-weight: 800;
  letter-spacing: 0;
}

.member-header p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.header-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
  white-space: nowrap;
}

.live-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 6px;
  border-radius: 999px;
  background: #22c55e;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  min-height: 92px;
  padding: 14px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.metric-label {
  font-size: 12px;
  color: #64748b;
}

.metric-value {
  margin-top: 8px;
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.1;
}

.metric-sub {
  margin-top: 7px;
  color: #94a3b8;
  font-size: 12px;
}

.filter-band,
.table-panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.filter-band {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 12px;
}

.filter-left {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.keyword-input {
  width: 190px;
}

.filter-actions {
  display: flex;
  gap: 8px;
}

.table-panel {
  padding: 12px 14px 14px;
}

.muted-code {
  margin-left: 8px;
  color: #94a3b8;
  font-size: 12px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
.segment-alert { margin-bottom:10px; }
.action-summary-grid { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:8px; margin-bottom:12px; }
.action-summary-item { min-width:0; min-height:78px; padding:10px 12px; display:flex; flex-direction:column; gap:5px; border:1px solid #E5E7EB; border-radius:8px; background:#F8FAFC; }
.action-summary-item span,.action-summary-item small { color:#64748B; font-size:12px; }
.action-summary-item strong { color:#0F172A; font-size:19px; line-height:1.2; }
.segment-summary-grid { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:8px; margin-bottom:12px; }
.segment-summary-item { min-width:0; min-height:68px; padding:10px 12px; display:flex; flex-direction:column; gap:7px; border:1px solid #E5E7EB; border-radius:8px; background:#F8FAFC; }
.segment-summary-item span { color:#64748B; font-size:12px; }
.segment-summary-item strong { color:#0F172A; font-size:20px; line-height:1; }
.tag-list { display:flex; flex-wrap:wrap; gap:5px; }
.evidence-text { max-height:360px; margin:0; overflow:auto; white-space:pre-wrap; word-break:break-word; color:#334155; font-size:12px; line-height:1.5; }
.muted { color:#94A3B8; font-size:12px; }
.negative { color:#DC2626; }
.positive { color:#059669; }
.vip-sales-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:8px; margin-bottom:12px; }
.sales-metric { min-width:0; min-height:82px; padding:11px 12px; border:1px solid #E5E7EB; border-radius:8px; background:#F8FAFC; display:flex; flex-direction:column; gap:5px; }
.sales-metric span,.sales-metric small { color:#64748B; font-size:12px; }
.sales-metric strong { color:#0F172A; font-size:18px; line-height:1.2; overflow-wrap:anywhere; }
.sales-analysis-layout { display:grid; grid-template-columns:minmax(0,2fr) minmax(340px,1fr); gap:12px; }
.analysis-block { min-width:0; border:1px solid #E5E7EB; border-radius:8px; padding:10px; }
.block-title { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
.block-title h3 { margin:0; font-size:14px; }
.block-title span { color:#94A3B8; font-size:12px; }
.pending-strip { display:flex; gap:18px; flex-wrap:wrap; margin-top:10px; padding:10px 12px; background:#F8FAFC; border:1px solid #E5E7EB; border-radius:8px; color:#64748B; font-size:12px; }
.pending-strip span { display:flex; align-items:center; gap:7px; }

@media (max-width: 1280px) {
  .summary-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .vip-sales-grid { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .segment-summary-grid { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .action-summary-grid { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .sales-analysis-layout { grid-template-columns:1fr; }
}

@media (max-width: 900px) {
  .member-header,
  .filter-band {
    flex-direction: column;
    align-items: stretch;
  }

  .header-meta {
    align-items: flex-start;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .vip-sales-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .segment-summary-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .action-summary-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
</style>
