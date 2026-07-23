<template>
  <div class="fc-settings">
    <div class="page-header">
      <h2>设置</h2>
    </div>

    <el-tabs v-model="activeTab">
      <!-- 自动凭证规则 -->
      <el-tab-pane label="自动凭证规则" name="auto_rules">
        <div class="filter-bar">
          <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="loadRules">
            <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
          </el-select>
          <el-button type="primary" @click="openRuleCreate">新建规则</el-button>
        </div>

        <el-table :data="rules" stripe size="small" v-loading="ruleLoading">
          <el-table-column prop="rule_name" label="规则名称" min-width="150" />
          <el-table-column prop="business_type" label="业务类型" width="120" />
          <el-table-column prop="source_system" label="来源系统" width="120" />
          <el-table-column prop="effective_from" label="生效期间" width="110" />
          <el-table-column prop="priority" label="优先级" width="80" align="center" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openRunRule(row)">运行</el-button>
              <el-button link type="primary" size="small" @click="openRuleEdit(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-card shadow="never" class="sub-card" v-if="runs.length > 0">
          <template #header><span class="card-title">运行历史</span></template>
          <el-table :data="runs" stripe size="small">
            <el-table-column prop="period" label="期间" width="110" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column prop="draft_count" label="草稿数" width="80" align="center" />
            <el-table-column prop="exception_count" label="异常数" width="80" align="center" />
            <el-table-column prop="created_at" label="时间" width="170" />
            <el-table-column label="异常" min-width="200">
              <template #default="{ row }">
                <span v-if="row.exceptions?.length">{{ row.exceptions.map((e: any) => e.message || JSON.stringify(e)).join("; ") }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 报表映射 -->
      <el-tab-pane label="报表映射" name="report_mapping">
        <div class="filter-bar">
          <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="loadMappingData">
            <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
          </el-select>
        </div>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-card shadow="never" class="sub-card">
              <template #header><span class="card-title">科目列表</span></template>
              <el-table :data="accounts" stripe size="small" max-height="400">
                <el-table-column prop="account_code" label="科目编码" width="120" />
                <el-table-column prop="account_name" label="科目名称" min-width="160" />
              </el-table>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never" class="sub-card">
              <template #header><span class="card-title">映射关系</span></template>
              <div class="mapping-form">
                <el-form :model="mappingForm" label-width="80px" inline>
                  <el-form-item label="科目">
                    <el-select v-model="mappingForm.account_id" filterable style="width: 180px;">
                      <el-option v-for="a in accounts" :key="a.id" :label="`${a.account_code} ${a.account_name}`" :value="a.id" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="报表行">
                    <el-select v-model="mappingForm.statement_line_id" filterable style="width: 180px;">
                      <el-option v-for="s in statementLines" :key="s.id" :label="`${s.line_code} ${s.line_name}`" :value="s.id" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="符号">
                    <el-select v-model="mappingForm.amount_sign" style="width: 100px;">
                      <el-option label="正" :value="1" />
                      <el-option label="负" :value="-1" />
                    </el-select>
                  </el-form-item>
                  <el-form-item>
                    <el-button type="primary" @click="handleMapAccount">添加映射</el-button>
                  </el-form-item>
                </el-form>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 操作日志 -->
      <el-tab-pane label="操作日志" name="op_logs">
        <div class="filter-bar">
          <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="loadLogs">
            <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
          </el-select>
          <el-select v-model="logActionFilter" placeholder="操作类型" clearable style="width: 140px;" @change="loadLogs">
            <el-option label="创建" value="create" />
            <el-option label="更新" value="update" />
            <el-option label="删除" value="delete" />
            <el-option label="过账" value="post" />
            <el-option label="结账" value="close" />
            <el-option label="反结账" value="reopen" />
          </el-select>
        </div>

        <el-table :data="logs" stripe size="small" v-loading="logLoading">
          <el-table-column prop="created_at" label="时间" width="170" />
          <el-table-column prop="actor_name" label="操作人" width="120" />
          <el-table-column prop="action" label="操作" min-width="140" />
          <el-table-column prop="target_type" label="目标类型" width="120" />
          <el-table-column prop="target_id" label="目标ID" width="100" />
          <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
        </el-table>
        <el-pagination
          v-if="logTotal > 0"
          v-model:current-page="logPage"
          v-model:page-size="logPageSize"
          :total="logTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, prev, pager, next, sizes"
          @change="loadLogs"
          style="margin-top: 16px; justify-content: flex-end;"
        />
      </el-tab-pane>

      <!-- 权限矩阵 -->
      <el-tab-pane label="权限矩阵" name="permissions">
        <el-empty description="权限矩阵功能开发中，敬请期待" />
      </el-tab-pane>
    </el-tabs>

    <!-- 自动凭证规则弹窗 -->
    <el-dialog v-model="showRuleDialog" :title="editingRule ? '编辑规则' : '新建规则'" width="600px" :close-on-click-modal="false">
      <el-form ref="ruleFormRef" :model="ruleForm" label-width="110px">
        <el-form-item label="规则名称" required>
          <el-input v-model="ruleForm.rule_name" />
        </el-form-item>
        <el-form-item label="业务类型" required>
          <el-input v-model="ruleForm.business_type" placeholder="如 sales、purchase、payroll" />
        </el-form-item>
        <el-form-item label="来源系统" required>
          <el-input v-model="ruleForm.source_system" placeholder="如 baison、dingtalk" />
        </el-form-item>
        <el-form-item label="生效起始期间" required>
          <el-input v-model="ruleForm.effective_from" placeholder="如 202601" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="ruleForm.priority" :min="1" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="条件">
          <el-input v-model="ruleForm.conditions_str" type="textarea" :rows="3" placeholder='JSON 格式，如 {"amount_gt": 0}' />
        </el-form-item>
        <el-form-item label="分录模板">
          <el-input v-model="ruleForm.entry_template_str" type="textarea" :rows="6" placeholder='JSON 格式，如 [{"account_id": 1, "direction": "debit", "amount_source": "total"}]' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRuleDialog = false">取消</el-button>
        <el-button type="primary" :loading="ruleSaving" @click="handleSaveRule">保存</el-button>
      </template>
    </el-dialog>

    <!-- 运行规则弹窗 -->
    <el-dialog v-model="showRunDialog" title="运行规则" width="420px" :close-on-click-modal="false">
      <el-form :model="runForm" label-width="80px">
        <el-form-item label="规则">
          <span>{{ runTarget?.rule_name }}</span>
        </el-form-item>
        <el-form-item label="期间" required>
          <el-input v-model="runForm.period" placeholder="如 202601" />
        </el-form-item>
        <el-form-item label="模式">
          <el-radio-group v-model="runForm.mode">
            <el-radio label="preview">预览</el-radio>
            <el-radio label="draft">草稿</el-radio>
            <el-radio label="live">正式</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRunDialog = false">取消</el-button>
        <el-button type="primary" :loading="runLoading" @click="handleRun">运行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { financeCenterApi, type FinBook, type FinAutoEntryRule, type FinAutoEntryRun, type FinAccount, type FinOperationLog } from "@/api/financeCenter";

const activeTab = ref("auto_rules");
const selectedBookId = ref<number | null>(null);
const books = ref<FinBook[]>([]);

// 自动凭证规则
const rules = ref<FinAutoEntryRule[]>([]);
const ruleLoading = ref(false);
const runs = ref<FinAutoEntryRun[]>([]);

const showRuleDialog = ref(false);
const editingRule = ref<FinAutoEntryRule | null>(null);
const ruleFormRef = ref();
const ruleSaving = ref(false);
const ruleForm = ref({
  rule_name: "",
  business_type: "",
  source_system: "",
  effective_from: "",
  priority: 10,
  conditions_str: "",
  entry_template_str: "",
});

const showRunDialog = ref(false);
const runTarget = ref<FinAutoEntryRule | null>(null);
const runLoading = ref(false);
const runForm = ref({ period: "", mode: "preview" });

// 报表映射
const accounts = ref<FinAccount[]>([]);
const statementLines = ref<any[]>([]);
const mappingForm = ref({
  account_id: null as number | null,
  statement_line_id: null as number | null,
  amount_sign: 1,
});

// 操作日志
const logs = ref<FinOperationLog[]>([]);
const logLoading = ref(false);
const logActionFilter = ref("");
const logPage = ref(1);
const logPageSize = ref(20);
const logTotal = ref(0);

const loadBooks = async () => {
  try {
    const res = await financeCenterApi.listBooks();
    books.value = res.data.data || [];
    if (books.value.length > 0 && !selectedBookId.value) {
      selectedBookId.value = books.value[0].id;
    }
  } catch { /* ignore */ }
};

// 自动凭证规则
const loadRules = async () => {
  if (!selectedBookId.value) return;
  ruleLoading.value = true;
  try {
    const res = await financeCenterApi.listAutoEntryRules({ book_id: selectedBookId.value });
    rules.value = res.data.data || [];
    const runsRes = await financeCenterApi.listAutoEntryRuns({ book_id: selectedBookId.value, ...{ page_size: 50 } });
    runs.value = (runsRes.data.data as any)?.items || [];
  } catch { /* ignore */ }
  ruleLoading.value = false;
};

const openRuleCreate = () => {
  if (!selectedBookId.value) { ElMessage.warning("请先选择账套"); return; }
  editingRule.value = null;
  ruleForm.value = { rule_name: "", business_type: "", source_system: "", effective_from: "", priority: 10, conditions_str: "", entry_template_str: "" };
  showRuleDialog.value = true;
};

const openRuleEdit = (rule: FinAutoEntryRule) => {
  editingRule.value = rule;
  ruleForm.value = {
    rule_name: rule.rule_name,
    business_type: rule.business_type,
    source_system: rule.source_system,
    effective_from: rule.effective_from,
    priority: rule.priority,
    conditions_str: JSON.stringify(rule.conditions, null, 2),
    entry_template_str: JSON.stringify(rule.entry_template, null, 2),
  };
  showRuleDialog.value = true;
};

const handleSaveRule = async () => {
  if (!selectedBookId.value) return;
  ruleSaving.value = true;
  try {
    let conditions: Record<string, unknown> = {};
    let entry_template: Record<string, unknown> = {};
    try { if (ruleForm.value.conditions_str) conditions = JSON.parse(ruleForm.value.conditions_str); } catch { /* */ }
    try { if (ruleForm.value.entry_template_str) entry_template = JSON.parse(ruleForm.value.entry_template_str); } catch { /* */ }
    await financeCenterApi.upsertAutoEntryRule({
      book_id: selectedBookId.value,
      rule_name: ruleForm.value.rule_name,
      business_type: ruleForm.value.business_type,
      source_system: ruleForm.value.source_system,
      effective_from: ruleForm.value.effective_from,
      priority: ruleForm.value.priority,
      conditions,
      entry_template,
    });
    ElMessage.success(editingRule.value ? "规则已更新" : "规则已创建");
    showRuleDialog.value = false;
    loadRules();
  } catch { ElMessage.error("保存失败"); }
  ruleSaving.value = false;
};

const openRunRule = (rule: FinAutoEntryRule) => {
  runTarget.value = rule;
  runForm.value = { period: "", mode: "preview" };
  showRunDialog.value = true;
};

const handleRun = async () => {
  if (!runTarget.value || !runForm.value.period) {
    ElMessage.warning("请输入期间");
    return;
  }
  runLoading.value = true;
  try {
    await financeCenterApi.runAutoEntry({
      rule_id: runTarget.value.id,
      period: runForm.value.period,
      mode: runForm.value.mode,
    });
    ElMessage.success("规则运行成功");
    showRunDialog.value = false;
    loadRules();
  } catch { ElMessage.error("运行失败"); }
  runLoading.value = false;
};

// 报表映射
const loadMappingData = async () => {
  if (!selectedBookId.value) return;
  try {
    const res = await financeCenterApi.listAccounts({ book_id: selectedBookId.value });
    accounts.value = res.data.data || [];
  } catch { /* ignore */ }
};

const handleMapAccount = async () => {
  if (!selectedBookId.value || !mappingForm.value.account_id || !mappingForm.value.statement_line_id) {
    ElMessage.warning("请选择科目和报表行");
    return;
  }
  try {
    await financeCenterApi.mapAccountToStatement({
      book_id: selectedBookId.value,
      account_id: mappingForm.value.account_id,
      statement_line_id: mappingForm.value.statement_line_id,
      amount_sign: mappingForm.value.amount_sign,
    });
    ElMessage.success("映射已添加");
  } catch { ElMessage.error("添加映射失败"); }
};

// 操作日志
const loadLogs = async () => {
  if (!selectedBookId.value) return;
  logLoading.value = true;
  try {
    const res = await financeCenterApi.listOperationLogs({ book_id: selectedBookId.value, ...{
      action: logActionFilter.value || undefined,
      page: logPage.value,
      page_size: logPageSize.value,
    } });
    const data = res.data.data as any;
    logs.value = data?.items || [];
    logTotal.value = data?.total || 0;
  } catch { /* ignore */ }
  logLoading.value = false;
};

onMounted(() => {
  loadBooks();
});
</script>

<script lang="ts">
export default { name: "FinanceSettings" };
</script>

<style scoped>
.fc-settings { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 20px; color: #1f2937; margin: 0; }
.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
.sub-card { border-radius: 8px; border: 1px solid #e5e7eb; margin-top: 16px; }
.sub-card :deep(.el-card__header) { padding: 12px 16px; border-bottom: 1px solid #f3f4f6; }
.card-title { font-size: 14px; font-weight: 600; color: #1f2937; }
.mapping-form { padding: 8px 0; }
</style>