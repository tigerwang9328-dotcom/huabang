<template>
  <section class="workspace">
    <el-card shadow="never" class="hero">
      <template #header>
        <div class="title-row">
          <div>
            <p class="eyebrow">财务中心 / V2.0</p>
            <h1>会计工作台</h1>
          </div>
          <el-tag type="warning" effect="light">当前为只读验收阶段</el-tag>
        </div>
      </template>
      <p>
        新账采用“草稿 → 财务人员审核 → 人工过账”。历史金蝶数据与当前账严格隔离；在最终切换 Gate 通过前，不开放 V2 制单、审核或过账。
      </p>
      <el-alert
        :title="gateMessage"
        :type="books.length ? 'warning' : 'info'"
        :closable="false"
        show-icon
      />
    </el-card>

    <el-card shadow="never" class="book-card">
      <template #header>
        <div class="title-row">
          <strong>当前账账簿</strong>
          <el-button :loading="loading" text type="primary" @click="loadBooks">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="books" empty-text="尚未建立 V2 当前账账簿">
        <el-table-column prop="book_code" label="账簿编码" min-width="140" />
        <el-table-column prop="book_name" label="账簿名称" min-width="220" />
        <el-table-column prop="status" label="状态" min-width="120" />
        <el-table-column label="正式报表">
          <template #default="{ row }">
            <el-tag :type="row.formal_report_blocked ? 'danger' : 'success'" effect="plain">
              {{ row.formal_report_blocked ? "已阻断" : "可出具" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="books.length" class="workspace-filter">
        <el-select v-model="selectedBookId" aria-label="选择 V2 当前账账簿" @change="loadWorkspace">
          <el-option v-for="book in books" :key="book.id" :label="`${book.book_code} · ${book.book_name}`" :value="book.id" />
        </el-select>
        <el-button :loading="workspaceLoading" text type="primary" @click="loadWorkspace">刷新账期与凭证</el-button>
      </div>
    </el-card>

    <el-card v-loading="monitoringLoading" shadow="never" class="monitoring-card">
      <template #header>
        <div class="title-row">
          <div>
            <strong>运行监控与告警 Gate</strong>
            <p class="subtle">仅显示脱敏的 V2 聚合值；未接入的采集器会明确标记，不以 0 代替。</p>
          </div>
          <el-button :loading="monitoringLoading" text type="primary" @click="loadMonitoring">刷新</el-button>
        </div>
      </template>
      <el-alert v-if="monitoringError" class="history-error" :title="`监控读取失败：${monitoringError}`" type="error" :closable="false" show-icon />
      <el-alert v-else-if="monitoringSummary" :title="monitoringSummary.message" type="info" :closable="false" show-icon />
      <el-table :data="monitoringSummary?.metric_policies || []" max-height="360" empty-text="尚未取得 V2 监控策略">
        <el-table-column label="指标" min-width="170"><template #default="{ row }">{{ metricLabel(row.metric_key) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.availability === 'available' ? 'success' : 'info'" effect="plain">{{ row.availability === 'available' ? '已接入' : '未接入' }}</el-tag></template></el-table-column>
        <el-table-column label="当前值" width="100"><template #default="{ row }">{{ row.availability === 'available' ? row.value : '—' }}</template></el-table-column>
        <el-table-column prop="threshold" label="告警阈值" min-width="170" />
        <el-table-column prop="close_condition" label="关闭条件" min-width="270" show-overflow-tooltip />
        <el-table-column label="说明" min-width="250" show-overflow-tooltip><template #default="{ row }">{{ row.unavailable_reason || `负责人：${row.owner}；通知：${row.notification_route}${row.notification_configured ? '（已接入）' : '（待接入）'}` }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-card v-loading="historyLoading" shadow="never" class="history-card">
      <template #header>
        <div class="title-row">
          <div>
            <strong>历史金蝶凭证（只读存档）</strong>
            <p class="subtle">仅展示已完成校验并发布的 fin_history 数据，不参与 V2 当前账制单或过账。</p>
          </div>
          <el-button :loading="historyLoading" text type="primary" @click="loadHistoryVouchers">刷新</el-button>
        </div>
      </template>
      <el-alert
        title="每条凭证及其分录均带“历史数据”标记；原始金蝶账套只读保留，导入失败或未发布批次不会出现在这里。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert v-if="historyLoadError" class="history-error" :title="`历史凭证读取失败：${historyLoadError}`" type="error" :closable="false" show-icon />
      <el-table :data="historyVouchers" max-height="360" empty-text="尚未发布可查询的历史金蝶凭证">
        <el-table-column prop="voucher_date" label="日期" min-width="110" />
        <el-table-column prop="voucher_no" label="凭证号" min-width="110" />
        <el-table-column prop="voucher_group" label="字" min-width="70" />
        <el-table-column prop="fiscal_period" label="期间" min-width="80" />
        <el-table-column prop="total_debit" label="借方合计" min-width="110" />
        <el-table-column prop="total_credit" label="贷方合计" min-width="110" />
        <el-table-column prop="source_database" label="来源账套" min-width="150" />
        <el-table-column label="数据标记" min-width="100">
          <template #default="{ row }"><el-tag :type="row.historical_marker ? 'info' : 'danger'" effect="plain">{{ row.historical_marker ? "历史数据" : "标记异常" }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }"><el-button text type="primary" @click="viewHistoryVoucher(row)">查看分录</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="selectedBookId" v-loading="workspaceLoading" shadow="never">
      <template #header><strong>当前账工作区（只读）</strong></template>
      <el-alert title="这里展示的是 fin_current 的账期、可制单科目和凭证状态；写入仍受后端 Gate 强制控制。" type="info" :closable="false" show-icon />
      <el-alert
        class="gate-alert"
        :title="writeGateMessage"
        :type="draftEnabled || reviewEnabled || postEnabled ? 'warning' : 'info'"
        :closable="false"
        show-icon
      />
      <section class="opening-section">
        <div class="section-head">
          <div><h2>期初余额批次</h2><span>预演和最终期初均须人工核对；锁定批次本身不开放当前账写入。</span></div>
          <div class="close-actions">
            <el-button :loading="openingLoading" text type="primary" @click="loadOpeningBalances">刷新批次</el-button>
            <el-button type="primary" @click="openOpeningBalanceEditor">新建期初批次</el-button>
          </div>
        </div>
        <el-alert title="最终期初只能在旧系统冻结、最终增量导入并完成逐余额核对后锁定。当前账写入仍受功能 Gate 控制。" type="warning" :closable="false" show-icon />
        <el-table :data="openingBalances" max-height="240" empty-text="尚未创建期初余额批次">
          <el-table-column prop="batch_kind" label="类型" min-width="100"><template #default="{ row }">{{ row.batch_kind === 'final' ? '最终期初' : '预演期初' }}</template></el-table-column>
          <el-table-column prop="status" label="状态" min-width="100" />
          <el-table-column prop="history_coverage_end_date" label="历史截止日" min-width="120" />
          <el-table-column prop="go_live_date" label="启用日" min-width="120" />
          <el-table-column label="覆盖连续" min-width="100"><template #default="{ row }">{{ row.coverage_continuous ? '是' : '否（须获批断档）' }}</template></el-table-column>
          <el-table-column prop="approved_by" label="锁定人" min-width="110"><template #default="{ row }">{{ row.approved_by || '—' }}</template></el-table-column>
          <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button v-if="row.status === 'draft'" text type="primary" @click="validateOpeningBalance(row)">验证</el-button><el-button v-else-if="row.status === 'validated'" text type="danger" @click="confirmOpeningBalanceLock(row)">锁定</el-button></template></el-table-column>
        </el-table>
      </section>
      <section v-if="draftEnabled" class="draft-section">
        <div class="section-head"><h2>人工凭证草稿</h2><span>保存后仍需提交、审核和人工过账</span></div>
        <div class="draft-meta">
          <el-select v-model="draft.period_id" placeholder="选择开放期间">
            <el-option v-for="period in openPeriods" :key="period.id" :label="period.period_code" :value="period.id" />
          </el-select>
          <el-date-picker v-model="draft.voucher_date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
          <el-button type="primary" :loading="draftSaving" @click="saveDraft">保存草稿</el-button>
        </div>
        <el-table :data="draft.entries" max-height="260" empty-text="请至少保留两条分录">
          <el-table-column label="科目" min-width="220"><template #default="{ row }"><el-select v-model="row.account_version_id" filterable placeholder="选择可制单科目"><el-option v-for="account in accounts" :key="account.id" :label="`${account.account_code} · ${account.account_name}`" :value="account.id" /></el-select></template></el-table-column>
          <el-table-column label="摘要" min-width="160"><template #default="{ row }"><el-input v-model="row.summary" maxlength="512" /></template></el-table-column>
          <el-table-column label="借方" width="150"><template #default="{ row }"><el-input-number v-model="row.debit_amount" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
          <el-table-column label="贷方" width="150"><template #default="{ row }"><el-input-number v-model="row.credit_amount" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
          <el-table-column width="80"><template #default="{ $index }"><el-button text type="danger" :disabled="draft.entries.length <= 2" @click="removeDraftLine($index)">删除</el-button></template></el-table-column>
        </el-table>
        <el-button text type="primary" @click="addDraftLine">添加分录</el-button>
      </section>
      <div class="workspace-grid">
        <section>
          <h2>会计期间</h2>
          <el-table :data="periods" max-height="240" empty-text="当前账尚无会计期间">
            <el-table-column prop="period_code" label="期间" min-width="100" />
            <el-table-column prop="status" label="状态" min-width="90" />
            <el-table-column prop="start_date" label="开始" min-width="110" />
            <el-table-column prop="end_date" label="结束" min-width="110" />
            <el-table-column label="结账" width="100" fixed="right"><template #default="{ row }"><el-button text type="primary" @click="viewPeriodCloseReadiness(row)">检查</el-button></template></el-table-column>
          </el-table>
        </section>
        <section>
          <h2>可制单科目</h2>
          <el-table :data="accounts" max-height="240" empty-text="当前账尚无可制单科目">
            <el-table-column prop="account_code" label="编码" min-width="100" />
            <el-table-column prop="account_name" label="科目" min-width="150" />
            <el-table-column prop="normal_balance" label="余额方向" min-width="90" />
          </el-table>
        </section>
      </div>
      <section class="voucher-section">
        <h2>凭证工作流</h2>
        <el-table :data="vouchers" max-height="300" empty-text="当前账尚无凭证">
          <el-table-column prop="voucher_date" label="日期" min-width="110" />
          <el-table-column prop="voucher_no" label="凭证号" min-width="110"><template #default="{ row }">{{ row.voucher_no || "待人工过账编号" }}</template></el-table-column>
          <el-table-column prop="status" label="状态" min-width="100" />
          <el-table-column prop="total_debit" label="借方合计" min-width="110" />
          <el-table-column prop="total_credit" label="贷方合计" min-width="110" />
          <el-table-column prop="prepared_by" label="制单人" min-width="100" />
          <el-table-column prop="reviewer_id" label="审核人" min-width="100" />
          <el-table-column prop="posted_by" label="过账人" min-width="100" />
          <el-table-column label="操作" min-width="250" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="viewVoucher(row)">查看明细</el-button>
              <el-button v-for="action in availableActions(row)" :key="action" size="small" text type="primary" :loading="commandLoading === `${row.id}:${action}`" @click="runCommand(row, action)">{{ actionLabel(action) }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </el-card>

    <el-drawer v-model="historyDrawerOpen" :title="`历史凭证分录${selectedHistoryVoucher ? ` · ${selectedHistoryVoucher.voucher_no}` : ''}`" size="760px">
      <el-alert title="分录来自已发布的历史导入批次，仅供核对；不能在此修改、审核或过账。" type="info" :closable="false" show-icon />
      <el-table v-loading="historyLineLoading" :data="historyVoucherLines" max-height="620" empty-text="该历史凭证没有可查询分录">
        <el-table-column prop="line_no" label="行号" width="70" />
        <el-table-column prop="account_code" label="科目编码" min-width="110" />
        <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
        <el-table-column prop="debit_amount" label="借方" min-width="110" />
        <el-table-column prop="credit_amount" label="贷方" min-width="110" />
        <el-table-column prop="currency_code" label="币种" width="80" />
        <el-table-column label="数据标记" width="100"><template #default="{ row }"><el-tag :type="row.historical_marker ? 'info' : 'danger'" effect="plain">{{ row.historical_marker ? "历史数据" : "标记异常" }}</el-tag></template></el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="voucherDrawerOpen" :title="`当前账凭证明细${selectedVoucher ? ` · ${selectedVoucher.voucher_no || `凭证#${selectedVoucher.id}`}` : ''}`" size="860px">
      <el-alert title="当前账凭证的分录与操作事件均来自 fin_current；历史金蝶凭证须在独立历史档案中查看。" type="info" :closable="false" show-icon />
      <template v-if="selectedVoucher">
        <el-descriptions class="close-summary" :column="2" border>
          <el-descriptions-item label="状态">{{ selectedVoucher.status }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ selectedVoucher.version }}</el-descriptions-item>
          <el-descriptions-item label="日期">{{ selectedVoucher.voucher_date }}</el-descriptions-item>
          <el-descriptions-item label="制单人">{{ selectedVoucher.prepared_by }}</el-descriptions-item>
          <el-descriptions-item label="审核人">{{ selectedVoucher.reviewer_id || "—" }}</el-descriptions-item>
          <el-descriptions-item label="过账人">{{ selectedVoucher.posted_by || "—" }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="selectedVoucher?.status === 'draft' && draftEnabled" class="detail-actions">
          <el-button type="primary" @click="beginVoucherDraftEdit">编辑草稿</el-button>
        </div>
        <section v-if="voucherEditOpen" class="draft-section">
          <div class="section-head"><h2>编辑草稿</h2><span>保存会整体替换当前草稿分录，并以版本号防止并发覆盖。</span></div>
          <div class="draft-meta">
            <el-date-picker v-model="voucherEdit.voucher_date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
            <el-button type="primary" :loading="voucherEditSaving" @click="saveVoucherDraftEdit">保存草稿修改</el-button>
          </div>
          <el-table :data="voucherEdit.entries" max-height="260" empty-text="请至少保留两条分录">
            <el-table-column label="科目" min-width="220"><template #default="{ row }"><el-select v-model="row.account_version_id" filterable placeholder="选择可制单科目"><el-option v-for="account in accounts" :key="account.id" :label="`${account.account_code} · ${account.account_name}`" :value="account.id" /></el-select></template></el-table-column>
            <el-table-column label="摘要" min-width="160"><template #default="{ row }"><el-input v-model="row.summary" maxlength="512" /></template></el-table-column>
            <el-table-column label="借方" width="150"><template #default="{ row }"><el-input-number v-model="row.debit_amount" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
            <el-table-column label="贷方" width="150"><template #default="{ row }"><el-input-number v-model="row.credit_amount" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
            <el-table-column width="80"><template #default="{ $index }"><el-button text type="danger" :disabled="voucherEdit.entries.length <= 2" @click="removeVoucherEditLine($index)">删除</el-button></template></el-table-column>
          </el-table>
          <el-button text type="primary" @click="addVoucherEditLine">添加分录</el-button>
        </section>
        <section class="voucher-detail-section">
          <h2>分录</h2>
          <el-table v-loading="voucherDetailLoading" :data="selectedVoucher.lines" max-height="300" empty-text="该凭证没有分录">
            <el-table-column prop="line_no" label="行号" width="70" /><el-table-column prop="account_version_id" label="科目版本" min-width="110" />
            <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip /><el-table-column prop="debit_amount" label="借方" min-width="110" /><el-table-column prop="credit_amount" label="贷方" min-width="110" />
            <el-table-column prop="currency_code" label="币种" width="80" />
          </el-table>
        </section>
        <section class="voucher-detail-section">
          <h2>不可变操作记录</h2>
          <el-table :data="selectedVoucher.operation_events" max-height="260" empty-text="尚无操作记录">
            <el-table-column prop="created_at" label="时间" min-width="170" /><el-table-column prop="action" label="操作" min-width="150" />
            <el-table-column prop="actor_id" label="操作人" min-width="110" /><el-table-column prop="reason" label="原因" min-width="180" show-overflow-tooltip />
            <el-table-column prop="command_id" label="命令幂等键" min-width="180" show-overflow-tooltip />
          </el-table>
        </section>
      </template>
      <el-skeleton v-else-if="voucherDetailLoading" :rows="6" animated />
    </el-drawer>

    <el-drawer v-model="periodCloseDrawerOpen" :title="`结账检查${selectedClosePeriod ? ` · ${selectedClosePeriod.period_code}` : ''}`" size="720px">
      <el-alert title="结账前必须全部通过未过账、借贷平衡、来源异常和余额重算检查；人工操作仍受独立 period_close Gate 控制。" type="warning" :closable="false" show-icon />
      <template v-if="periodCloseReadiness">
        <el-descriptions class="close-summary" :column="2" border>
          <el-descriptions-item label="期间状态">{{ periodCloseReadiness.status }}</el-descriptions-item>
          <el-descriptions-item label="可开始结账">{{ periodCloseReadiness.ready_to_start_close ? "是" : "否" }}</el-descriptions-item>
          <el-descriptions-item label="未过账凭证">{{ periodCloseReadiness.checks.unposted_voucher_count }}</el-descriptions-item>
          <el-descriptions-item label="借贷不平凭证">{{ periodCloseReadiness.checks.unbalanced_voucher_count }}</el-descriptions-item>
          <el-descriptions-item label="来源异常">{{ periodCloseReadiness.checks.source_exception_count }}</el-descriptions-item>
          <el-descriptions-item label="余额差异">{{ periodCloseReadiness.checks.ledger_difference_count }}</el-descriptions-item>
          <el-descriptions-item label="已过账借贷">{{ periodCloseReadiness.checks.posted_debit }} / {{ periodCloseReadiness.checks.posted_credit }}</el-descriptions-item>
          <el-descriptions-item label="余额表借贷">{{ periodCloseReadiness.checks.ledger_debit }} / {{ periodCloseReadiness.checks.ledger_credit }}</el-descriptions-item>
          <el-descriptions-item label="需要损益结转证据">{{ periodCloseReadiness.checks.profit_closing_evidence_required ? "是" : "否" }}</el-descriptions-item>
          <el-descriptions-item label="已登记损益结转凭证">{{ periodCloseReadiness.checks.profit_closing_evidence_count }}</el-descriptions-item>
        </el-descriptions>
        <p class="close-note">来源异常口径：{{ periodCloseReadiness.checks.source_exception_scope }}</p>
        <el-button text type="primary" :loading="trialBalanceLoading" @click="loadTrialBalance">查看 V2 当前账试算表</el-button>
        <el-alert v-if="trialBalance" class="history-error" :title="trialBalance.formal_report_message" type="info" :closable="false" show-icon />
        <el-table v-if="trialBalance" :data="trialBalance.rows" max-height="300" empty-text="当前期间暂无已重建余额">
          <el-table-column prop="account_code" label="科目编码" min-width="110" /><el-table-column prop="account_name" label="科目名称" min-width="160" />
          <el-table-column prop="opening_debit" label="期初借" min-width="100" /><el-table-column prop="opening_credit" label="期初贷" min-width="100" />
          <el-table-column prop="period_debit" label="本期借" min-width="100" /><el-table-column prop="period_credit" label="本期贷" min-width="100" />
          <el-table-column prop="closing_debit" label="期末借" min-width="100" /><el-table-column prop="closing_credit" label="期末贷" min-width="100" />
        </el-table>
        <div v-if="periodCloseEnabled && periodCloseReadiness.status === 'open' && periodCloseReadiness.checks.profit_closing_evidence_missing_count" class="close-actions">
          <el-select v-model="selectedProfitClosingVoucherId" placeholder="选择已过账的手工损益结转凭证" clearable style="width: 320px">
            <el-option v-for="voucher in closePostedVouchers" :key="voucher.id" :label="`${voucher.voucher_no || `凭证#${voucher.id}`} · 借${voucher.total_debit} / 贷${voucher.total_credit}`" :value="voucher.id" />
          </el-select>
        </div>
        <div v-if="periodCloseEnabled" class="close-actions">
          <el-button v-for="action in availablePeriodActions()" :key="action" type="primary" :loading="periodCommandLoading === action" @click="runPeriodCommand(action)">{{ periodActionLabel(action) }}</el-button>
        </div>
        <el-alert v-else class="history-error" :title="writeReadiness?.commands.period_close.reason || '结账写入 Gate 未开启'" type="info" :closable="false" show-icon />
      </template>
      <el-skeleton v-else-if="periodCloseLoading" :rows="5" animated />
    </el-drawer>

    <el-drawer v-model="openingBalanceEditorOpen" title="新建期初余额批次" size="820px">
      <el-alert title="此操作只创建待核对批次，不会开启制单、审核或过账。请使用来源系统的逐科目、维度、币种余额；缺依据的余额不得默认填零。" type="info" :closable="false" show-icon />
      <div class="draft-meta opening-meta">
        <el-select v-model="openingBalance.batch_kind" aria-label="期初批次类型"><el-option label="预演期初" value="provisional" /><el-option label="最终期初" value="final" /></el-select>
        <el-date-picker v-model="openingBalance.history_coverage_end_date" type="date" value-format="YYYY-MM-DD" placeholder="历史截止日" :clearable="false" />
        <el-date-picker v-model="openingBalance.go_live_date" type="date" value-format="YYYY-MM-DD" placeholder="V2 启用日" :clearable="false" />
        <el-switch v-model="openingBalance.coverage_continuous" active-text="历史连续" inactive-text="存在断档" />
      </div>
      <el-table :data="openingBalance.lines" max-height="430" empty-text="请至少录入两条平衡的期初明细">
        <el-table-column label="科目" min-width="220"><template #default="{ row }"><el-select v-model="row.account_version_id" filterable placeholder="选择可制单科目"><el-option v-for="account in accounts" :key="account.id" :label="`${account.account_code} · ${account.account_name}`" :value="account.id" /></el-select></template></el-table-column>
        <el-table-column label="维度集 ID" width="150"><template #default="{ row }"><el-input-number v-model="row.dimension_set_id" :min="1" controls-position="right" /></template></el-table-column>
        <el-table-column label="借方" width="135"><template #default="{ row }"><el-input-number v-model="row.debit_amount" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
        <el-table-column label="贷方" width="135"><template #default="{ row }"><el-input-number v-model="row.credit_amount" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
        <el-table-column label="来源" min-width="140"><template #default="{ row }"><el-input v-model="row.source_system" maxlength="32" placeholder="如 kingdee" /></template></el-table-column>
        <el-table-column width="72"><template #default="{ $index }"><el-button text type="danger" :disabled="openingBalance.lines.length <= 2" @click="removeOpeningBalanceLine($index)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="close-actions"><el-button text type="primary" @click="addOpeningBalanceLine">添加明细</el-button><el-button type="primary" :loading="openingBalanceSaving" @click="saveOpeningBalance">保存待核对批次</el-button></div>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  financeV2Api,
  type FinanceV2Account,
  type FinanceV2Book,
  type FinanceV2HistoryVoucher,
  type FinanceV2HistoryVoucherLine,
  type FinanceV2MonitoringSummary,
  type FinanceV2OpeningBalanceBatch,
  type FinanceV2OpeningBalanceLineInput,
  type FinanceV2PeriodCommandInput,
  type FinanceV2PeriodCloseReadiness,
  type FinanceV2TrialBalance,
  type FinanceV2Period,
  type FinanceV2Voucher,
  type FinanceV2VoucherDetail,
  type FinanceV2VoucherLineInput,
  type FinanceV2WriteReadiness,
} from "@/api/financeV2";

const books = ref<FinanceV2Book[]>([]);
const selectedBookId = ref<number>();
const periods = ref<FinanceV2Period[]>([]);
const accounts = ref<FinanceV2Account[]>([]);
const vouchers = ref<FinanceV2Voucher[]>([]);
const selectedVoucher = ref<FinanceV2VoucherDetail>();
const historyVouchers = ref<FinanceV2HistoryVoucher[]>([]);
const historyVoucherLines = ref<FinanceV2HistoryVoucherLine[]>([]);
const selectedHistoryVoucher = ref<FinanceV2HistoryVoucher>();
const selectedClosePeriod = ref<FinanceV2Period>();
const writeReadiness = ref<FinanceV2WriteReadiness>();
const periodCloseReadiness = ref<FinanceV2PeriodCloseReadiness>();
const trialBalance = ref<FinanceV2TrialBalance>();
const monitoringSummary = ref<FinanceV2MonitoringSummary>();
const closePostedVouchers = ref<FinanceV2Voucher[]>([]);
const openingBalances = ref<FinanceV2OpeningBalanceBatch[]>([]);
const selectedProfitClosingVoucherId = ref<number>();
const loading = ref(false);
const historyLoading = ref(false);
const historyLineLoading = ref(false);
const periodCloseLoading = ref(false);
const trialBalanceLoading = ref(false);
const monitoringLoading = ref(false);
const openingLoading = ref(false);
const openingBalanceSaving = ref(false);
const workspaceLoading = ref(false);
const draftSaving = ref(false);
const commandLoading = ref("");
const periodCommandLoading = ref("");
const loadError = ref("");
const historyLoadError = ref("");
const monitoringError = ref("");
const historyDrawerOpen = ref(false);
const voucherDrawerOpen = ref(false);
const voucherDetailLoading = ref(false);
const voucherEditOpen = ref(false);
const voucherEditSaving = ref(false);
const periodCloseDrawerOpen = ref(false);
const openingBalanceEditorOpen = ref(false);
const today = () => new Date().toISOString().slice(0, 10);
const newRequestId = () => globalThis.crypto?.randomUUID?.() || `finance-v2-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const draft = reactive({ book_id: 0, period_id: 0, voucher_date: today(), request_id: newRequestId(), entries: [] as FinanceV2VoucherLineInput[] });
const openingBalance = reactive({ batch_kind: "provisional" as "provisional" | "final", history_coverage_end_date: "", go_live_date: "", coverage_continuous: true, lines: [] as FinanceV2OpeningBalanceLineInput[] });
const voucherEdit = reactive({ voucher_date: "", expected_version: 0, entries: [] as FinanceV2VoucherLineInput[] });

const draftEnabled = computed(() => Boolean(writeReadiness.value?.commands.draft.enabled));
const reviewEnabled = computed(() => Boolean(writeReadiness.value?.commands.review.enabled));
const postEnabled = computed(() => Boolean(writeReadiness.value?.commands.post.enabled));
const periodCloseEnabled = computed(() => Boolean(writeReadiness.value?.commands.period_close.enabled));
const openPeriods = computed(() => periods.value.filter((period) => period.status === "open"));
const writeGateMessage = computed(() => {
  if (!writeReadiness.value) return "正在读取服务器写入 Gate；未确认前不显示可写操作。";
  const disabled = Object.entries(writeReadiness.value.commands).filter(([, value]) => !value.enabled).map(([command]) => command);
  return disabled.length ? `当前禁用：${disabled.join("、")}。实际写入仍由后端再次校验。` : "已按当前用户和账簿确认 Gate；每次写入仍由后端强制复核。";
});

const gateMessage = computed(() => {
  if (loadError.value) return `无法读取 V2 账簿：${loadError.value}`;
  if (!books.value.length) return "尚未导入或批准 V2 当前账数据；这不是零余额，也不代表可开始制单。";
  return "生产写入开关仍应保持关闭，直至历史核对、最终期初、旧入口冻结与人工验收全部通过。";
});

async function loadBooks() {
  loading.value = true;
  loadError.value = "";
  try {
    const response = await financeV2Api.listBooks();
    books.value = response.data || [];
    if (!selectedBookId.value && books.value.length) selectedBookId.value = books.value[0].id;
    await Promise.all([loadWorkspace(), loadHistoryVouchers()]);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "请求失败";
  } finally {
    loading.value = false;
  }
}

async function loadHistoryVouchers() {
  historyLoading.value = true;
  historyLoadError.value = "";
  try {
    const response = await financeV2Api.listHistoryVouchers({ limit: 100 });
    historyVouchers.value = response.data || [];
  } catch (error) {
    historyVouchers.value = [];
    historyLoadError.value = error instanceof Error ? error.message : "请求失败";
  } finally {
    historyLoading.value = false;
  }
}

async function loadMonitoring() {
  monitoringLoading.value = true;
  monitoringError.value = "";
  try {
    const response = await financeV2Api.getMonitoringSummary();
    monitoringSummary.value = response.data;
  } catch (error) {
    monitoringSummary.value = undefined;
    monitoringError.value = error instanceof Error ? error.message : "请求失败";
  } finally {
    monitoringLoading.value = false;
  }
}

async function loadOpeningBalances() {
  if (!selectedBookId.value) {
    openingBalances.value = [];
    return;
  }
  openingLoading.value = true;
  try {
    const response = await financeV2Api.listOpeningBalances(selectedBookId.value);
    openingBalances.value = response.data || [];
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "期初余额批次读取失败");
  } finally {
    openingLoading.value = false;
  }
}

function emptyOpeningBalanceLine(): FinanceV2OpeningBalanceLineInput {
  return { account_version_id: 0, dimension_set_id: 0, debit_amount: 0, credit_amount: 0, source_system: "kingdee" };
}

function openOpeningBalanceEditor() {
  openingBalance.batch_kind = "provisional";
  openingBalance.history_coverage_end_date = "";
  openingBalance.go_live_date = "";
  openingBalance.coverage_continuous = true;
  openingBalance.lines.splice(0, openingBalance.lines.length, emptyOpeningBalanceLine(), emptyOpeningBalanceLine());
  openingBalanceEditorOpen.value = true;
}

function addOpeningBalanceLine() {
  openingBalance.lines.push(emptyOpeningBalanceLine());
}

function removeOpeningBalanceLine(index: number) {
  openingBalance.lines.splice(index, 1);
}

async function saveOpeningBalance() {
  if (!selectedBookId.value) return;
  if (!openingBalance.history_coverage_end_date || !openingBalance.go_live_date) return ElMessage.warning("请填写历史截止日与 V2 启用日");
  openingBalanceSaving.value = true;
  try {
    await financeV2Api.createOpeningBalance(selectedBookId.value, {
      batch_kind: openingBalance.batch_kind,
      history_coverage_end_date: openingBalance.history_coverage_end_date,
      go_live_date: openingBalance.go_live_date,
      coverage_continuous: openingBalance.coverage_continuous,
      command_id: newRequestId(),
      lines: openingBalance.lines.map((line) => ({ ...line })),
    });
    ElMessage.success("期初余额待核对批次已保存；当前账写入仍受功能 Gate 控制");
    openingBalanceEditorOpen.value = false;
    await loadOpeningBalances();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "期初余额批次保存失败");
  } finally {
    openingBalanceSaving.value = false;
  }
}

async function confirmOpeningBalanceLock(batch: FinanceV2OpeningBalanceBatch) {
  if (!selectedBookId.value) return;
  let reason: string;
  try {
    const response = await ElMessageBox.prompt("锁定会写入审批审计记录。仅在旧系统冻结、最终增量核对完成后执行。", "锁定期初余额", { inputPattern: /\S+/, inputErrorMessage: "必须填写锁定原因", confirmButtonText: "锁定", cancelButtonText: "取消" });
    reason = response.value;
  } catch {
    return;
  }
  try {
    await financeV2Api.lockOpeningBalance(selectedBookId.value, batch.id, { command_id: newRequestId(), expected_version: batch.version, reason });
    ElMessage.success("期初余额已锁定；请继续完成功能 Gate 和切换核对");
    await Promise.all([loadOpeningBalances(), loadWorkspace()]);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "期初余额锁定失败，请刷新后确认批次版本");
  }
}

async function validateOpeningBalance(batch: FinanceV2OpeningBalanceBatch) {
  if (!selectedBookId.value) return;
  let reason: string;
  try {
    const response = await ElMessageBox.prompt("验证将检查借贷平衡与来源字段，不会改变账簿启用边界。", "验证期初余额", { inputPattern: /\S+/, inputErrorMessage: "必须填写核对说明", confirmButtonText: "验证", cancelButtonText: "取消" });
    reason = response.value;
  } catch {
    return;
  }
  try {
    await financeV2Api.validateOpeningBalance(selectedBookId.value, batch.id, { command_id: newRequestId(), expected_version: batch.version, reason });
    ElMessage.success("期初余额已验证；最终期初仍须经切换 Gate 锁定");
    await loadOpeningBalances();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "期初余额验证失败，请刷新后检查明细");
  }
}

const metricLabel = (key: string) => ({
  posting_attempt_failed: "过账失败",
  voucher_unbalanced_blocked: "借贷不平阻断",
  history_import_conflicted: "历史导入冲突",
  source_inbox_backlog: "来源收件箱积压",
  exception_queue_backlog: "异常队列积压",
  lock_wait: "锁等待",
  deadlock: "死锁",
  period_close_failed: "结账失败",
  export_failure: "导出异常",
  api_5xx_rate: "API 5xx 比率",
  balance_difference_alert: "余额差异",
} as Record<string, string>)[key] || key;

async function viewHistoryVoucher(voucher: FinanceV2HistoryVoucher) {
  selectedHistoryVoucher.value = voucher;
  historyVoucherLines.value = [];
  historyDrawerOpen.value = true;
  historyLineLoading.value = true;
  try {
    const response = await financeV2Api.listHistoryVoucherLines(voucher.id, { limit: 500 });
    historyVoucherLines.value = response.data || [];
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "历史凭证分录读取失败");
  } finally {
    historyLineLoading.value = false;
  }
}

async function loadVoucherDetail(voucherId: number) {
  voucherDetailLoading.value = true;
  try {
    const response = await financeV2Api.getVoucherDetail(voucherId);
    selectedVoucher.value = response.data;
  } catch (error) {
    selectedVoucher.value = undefined;
    ElMessage.error(error instanceof Error ? error.message : "当前账凭证明细读取失败");
  } finally {
    voucherDetailLoading.value = false;
  }
}

async function viewVoucher(voucher: FinanceV2Voucher) {
  selectedVoucher.value = undefined;
  voucherEditOpen.value = false;
  voucherDrawerOpen.value = true;
  await loadVoucherDetail(voucher.id);
}

function beginVoucherDraftEdit() {
  if (!selectedVoucher.value) return;
  voucherEdit.voucher_date = selectedVoucher.value.voucher_date;
  voucherEdit.expected_version = selectedVoucher.value.version;
  voucherEdit.entries.splice(0, voucherEdit.entries.length, ...selectedVoucher.value.lines.map((line) => ({
    account_version_id: line.account_version_id || 0,
    dimension_set_id: line.dimension_set_id || undefined,
    summary: line.summary,
    debit_amount: line.debit_amount,
    credit_amount: line.credit_amount,
    currency_code: line.currency_code,
    exchange_rate: line.exchange_rate,
  })));
  voucherEditOpen.value = true;
}

function addVoucherEditLine() {
  voucherEdit.entries.push({ account_version_id: 0, summary: "", debit_amount: 0, credit_amount: 0 });
}

function removeVoucherEditLine(index: number) {
  voucherEdit.entries.splice(index, 1);
}

async function saveVoucherDraftEdit() {
  if (!selectedVoucher.value || selectedVoucher.value.status !== "draft" || !draftEnabled.value) return;
  voucherEditSaving.value = true;
  try {
    await financeV2Api.updateDraft(selectedVoucher.value.id, {
      voucher_date: voucherEdit.voucher_date,
      entries: voucherEdit.entries.map((entry) => ({ ...entry })),
      command_id: newRequestId(),
      expected_version: voucherEdit.expected_version,
    });
    ElMessage.success("凭证草稿已更新");
    voucherEditOpen.value = false;
    await Promise.all([loadVoucherDetail(selectedVoucher.value.id), loadWorkspace()]);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "草稿更新失败，请刷新后确认凭证版本");
  } finally {
    voucherEditSaving.value = false;
  }
}

async function viewPeriodCloseReadiness(period: FinanceV2Period) {
  if (!selectedBookId.value) return;
  selectedClosePeriod.value = period;
  periodCloseReadiness.value = undefined;
  trialBalance.value = undefined;
  closePostedVouchers.value = [];
  selectedProfitClosingVoucherId.value = undefined;
  periodCloseDrawerOpen.value = true;
  periodCloseLoading.value = true;
  try {
    const [readinessResponse, voucherResponse] = await Promise.all([
      financeV2Api.getPeriodCloseReadiness(selectedBookId.value, period.id),
      financeV2Api.listVouchers(selectedBookId.value, { period_id: period.id, status: "posted", limit: 200 }),
    ]);
    periodCloseReadiness.value = readinessResponse.data;
    closePostedVouchers.value = voucherResponse.data || [];
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "结账检查读取失败");
  } finally {
    periodCloseLoading.value = false;
  }
}

async function loadTrialBalance() {
  if (!selectedBookId.value || !selectedClosePeriod.value) return;
  trialBalanceLoading.value = true;
  try {
    const response = await financeV2Api.getTrialBalance(selectedBookId.value, selectedClosePeriod.value.id);
    trialBalance.value = response.data;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "试算表读取失败");
  } finally {
    trialBalanceLoading.value = false;
  }
}

async function loadWorkspace() {
  if (!selectedBookId.value) {
    periods.value = [];
    accounts.value = [];
    vouchers.value = [];
    writeReadiness.value = undefined;
    openingBalances.value = [];
    return;
  }
  workspaceLoading.value = true;
  try {
    const [periodResponse, accountResponse, voucherResponse, readinessResponse, openingResponse] = await Promise.all([
      financeV2Api.listPeriods(selectedBookId.value),
      financeV2Api.listAccounts(selectedBookId.value),
      financeV2Api.listVouchers(selectedBookId.value),
      financeV2Api.getWriteReadiness(selectedBookId.value),
      financeV2Api.listOpeningBalances(selectedBookId.value),
    ]);
    periods.value = periodResponse.data || [];
    accounts.value = accountResponse.data || [];
    vouchers.value = voucherResponse.data || [];
    writeReadiness.value = readinessResponse.data;
    openingBalances.value = openingResponse.data || [];
    draft.book_id = selectedBookId.value;
    if (!openPeriods.value.some((period) => period.id === draft.period_id)) draft.period_id = openPeriods.value[0]?.id || 0;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "工作区读取失败";
  } finally {
    workspaceLoading.value = false;
  }
}

function addDraftLine() {
  draft.entries.push({ account_version_id: 0, summary: "", debit_amount: 0, credit_amount: 0 });
}

function removeDraftLine(index: number) {
  draft.entries.splice(index, 1);
}

function resetDraft() {
  draft.request_id = newRequestId();
  draft.voucher_date = today();
  draft.entries.splice(0, draft.entries.length, ...[0, 1].map(() => ({ account_version_id: 0, summary: "", debit_amount: 0, credit_amount: 0 })));
}

async function saveDraft() {
  if (!draft.book_id || !draft.period_id) return ElMessage.warning("请选择账簿和开放期间");
  draftSaving.value = true;
  try {
    await financeV2Api.createDraft({ ...draft, entries: draft.entries.map((entry) => ({ ...entry })) });
    ElMessage.success("凭证草稿已保存");
    resetDraft();
    await loadWorkspace();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存草稿失败");
  } finally {
    draftSaving.value = false;
  }
}

const actionLabel = (action: string) => ({ submit: "提交", start_review: "领取审核", approve: "批准", reject: "驳回", reopen: "重新打开", withdraw: "撤回", cancel: "取消", post: "人工过账" } as Record<string, string>)[action] || action;
const actionGate = (action: string) => action === "post" ? postEnabled.value : ["start_review", "approve", "reject"].includes(action) ? reviewEnabled.value : draftEnabled.value;
function availableActions(voucher: FinanceV2Voucher) {
  const candidates: Record<string, string[]> = { draft: ["submit", "cancel"], submitted: ["start_review", "cancel"], reviewing: ["approve", "reject", "cancel"], rejected: ["reopen"], approved: ["withdraw", "cancel", "post"] };
  return (candidates[voucher.status] || []).filter(actionGate);
}

const periodActionLabel = (action: string) => ({ register_profit_closing: "登记损益结转凭证", start_close: "开始结账", complete_close: "完成结账", request_reopen: "申请反结账", approve_reopen: "批准反结账" } as Record<string, string>)[action] || action;
type FinanceV2PeriodAction = FinanceV2PeriodCommandInput["action"];
function availablePeriodActions(): FinanceV2PeriodAction[] {
  const status = periodCloseReadiness.value?.status;
  if (status === "open" && periodCloseReadiness.value?.checks.profit_closing_evidence_missing_count) return ["register_profit_closing"];
  if (status === "open" && periodCloseReadiness.value?.ready_to_start_close) return ["start_close"];
  if (status === "closing") return ["complete_close"];
  if (status === "closed") return ["request_reopen"];
  if (status === "reopening") return ["approve_reopen"];
  return [];
}

async function runPeriodCommand(action: FinanceV2PeriodAction) {
  if (!selectedBookId.value || !selectedClosePeriod.value || !periodCloseReadiness.value) return;
  const reasonRequired = ["register_profit_closing", "request_reopen", "approve_reopen"].includes(action);
  const voucherId = action === "register_profit_closing" ? selectedProfitClosingVoucherId.value : undefined;
  if (action === "register_profit_closing" && !voucherId) return ElMessage.warning("请选择已过账的手工损益结转凭证");
  let reason: string | undefined;
  if (reasonRequired) {
    try {
      const response = await ElMessageBox.prompt(`${periodActionLabel(action)}原因将写入不可变审计记录。`, periodActionLabel(action), { inputPattern: /\S+/, inputErrorMessage: "必须填写原因", confirmButtonText: "确认", cancelButtonText: "取消" });
      reason = response.value;
    } catch {
      return;
    }
  }
  periodCommandLoading.value = action;
  try {
    await financeV2Api.executePeriodCommand(selectedBookId.value, selectedClosePeriod.value.id, {
      action,
      command_id: newRequestId(),
      expected_version: periodCloseReadiness.value.version,
      reason,
      voucher_id: voucherId,
    });
    ElMessage.success(`${periodActionLabel(action)}已提交`);
    await loadWorkspace();
    const refreshed = periods.value.find((period) => period.id === selectedClosePeriod.value?.id);
    if (refreshed) await viewPeriodCloseReadiness(refreshed);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : `${periodActionLabel(action)}失败，请刷新后确认状态`);
  } finally {
    periodCommandLoading.value = "";
  }
}

async function runCommand(voucher: FinanceV2Voucher, action: string) {
  const reasonRequired = ["reject", "reopen", "withdraw", "cancel", "post"].includes(action);
  let reason: string | undefined;
  if (reasonRequired) {
    try {
      const response = await ElMessageBox.prompt(`${actionLabel(action)}原因将写入审计记录。`, actionLabel(action), { inputPattern: /\S+/, inputErrorMessage: "必须填写原因", confirmButtonText: "确认", cancelButtonText: "取消" });
      reason = response.value;
    } catch {
      return;
    }
  }
  const key = `${voucher.id}:${action}`;
  commandLoading.value = key;
  try {
    await financeV2Api.executeCommand(voucher.id, { action, command_id: newRequestId(), expected_version: voucher.version, reason });
    ElMessage.success(`${actionLabel(action)}已提交`);
    await loadWorkspace();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : `${actionLabel(action)}失败，请刷新后确认凭证状态`);
  } finally {
    commandLoading.value = "";
  }
}

onMounted(() => Promise.all([loadBooks(), loadMonitoring()]));
</script>

<style scoped>
.workspace { display: grid; gap: 16px; }
.hero p { margin: 0 0 16px; color: var(--el-text-color-regular); line-height: 1.7; }
.title-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.title-row h1 { margin: 2px 0 0; font-size: 22px; }
.eyebrow { margin: 0; color: var(--el-color-primary); font-size: 12px; font-weight: 600; }
.book-card { min-height: 260px; }
.monitoring-card { min-height: 220px; }
.history-card { min-height: 260px; }
.subtle { margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
.history-error { margin-top: 12px; }
.close-summary { margin-top: 16px; }
.close-note { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.close-actions { display: flex; gap: 10px; margin-top: 16px; }
.workspace-filter { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.gate-alert { margin-top: 16px; }
.opening-section { margin-top: 20px; }
.opening-meta { flex-wrap: wrap; }
.draft-section { margin-top: 20px; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.section-head h2 { margin: 0; font-size: 15px; }.section-head span { color: var(--el-text-color-secondary); font-size: 12px; }
.draft-meta { display: flex; gap: 12px; margin-bottom: 12px; }
.workspace-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
.workspace-grid h2, .voucher-section h2 { margin: 0 0 10px; font-size: 15px; }
.voucher-section { margin-top: 20px; }
.voucher-detail-section { margin-top: 20px; }
.voucher-detail-section h2 { margin: 0 0 10px; font-size: 15px; }
.detail-actions { margin-top: 16px; }
@media (max-width: 900px) { .workspace-grid { grid-template-columns: 1fr; } .draft-meta { flex-direction: column; } }
</style>
