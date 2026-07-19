const SOURCE_LABELS: Record<string, string> = {
  dim_product: "商品档案",
  dim_sku: "SKU档案",
  dim_store: "门店档案",
  dim_employee: "员工档案",
  dim_member: "会员档案",
  dwd_pos_ticket: "销售小票",
  dwd_pos_sale_goods: "销售商品明细",
  dwd_inventory_balance: "库存余额",
  dwd_baison_purchase_inbound: "采购入库",
  dwd_finance_expense: "费用明细",
  dwd_member_deposit: "会员储值明细",
  dwd_member_visit: "会员回访记录",
  dwd_attendance: "考勤明细",
  dws_company_daily: "公司经营汇总",
  dws_store_daily: "门店经营汇总",
  dws_product_daily: "商品销售汇总",
  dws_inventory_daily: "库存日汇总",
  dws_product_inbound_summary: "商品入库汇总",
  dws_product_sales_summary: "商品销售汇总",
  dws_member_daily: "会员经营汇总",
  dws_finance_daily: "财务日汇总",
  dm_business_overview_daily: "经营看板汇总",
  dm_finance_profit_daily: "财务利润汇总",
  dm_exception_audit: "异常稽核结果",
  finance_expense_records: "费用记录",
  app_action_task: "行动任务",
  ai_business_advice_snapshot: "AI经营建议快照",
  ai_diagnosis_rules: "经营诊断规则",
  rule_engine: "经营规则",
};

const ROLE_LABELS: Record<string, string> = {
  operation_manager: "运营负责人",
  area_supervisor: "区域督导",
  store_manager: "店长",
  product_manager: "商品负责人",
  warehouse_manager: "仓库负责人",
  finance_manager: "财务负责人",
  hr_manager: "人事负责人",
  member_manager: "会员运营负责人",
  audit_manager: "稽核负责人",
  general_manager: "总经理",
  boss: "老板",
  owner: "负责人",
};

const READINESS_LABELS: Record<string, string> = {
  ready: "已就绪",
  estimated: "预估",
  stale: "数据陈旧",
  pending_data: "待接入",
  missing: "缺数据",
  complete: "完整",
  incomplete: "不完整",
};

const ENGINE_LABELS: Record<string, string> = {
  deterministic_rules: "确定性规则模板",
  template: "确定性规则模板",
  model: "大模型建议",
};

const SOURCE_SEPARATOR = /\s*(?:\/|\+|,|，|、|;|；|\||\r?\n)+\s*/;

function normalizeKey(value: unknown) {
  return String(value ?? "")
    .trim()
    .replace(/[\s.-]+/g, "_")
    .toLowerCase();
}

function splitSource(source: unknown): string[] {
  if (Array.isArray(source)) return source.flatMap((item) => splitSource(item));
  return String(source ?? "")
    .split(SOURCE_SEPARATOR)
    .map((item) => item.trim())
    .filter(Boolean);
}

function isInternalLike(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return false;
  return (
    /_/.test(text) ||
    /^(dim|dwd|dws|dm|ods|app|rule|risk|fact|metric|snapshot)[._-]/i.test(text) ||
    /^(sales|product|inventory|finance|member|hr|audit|action|operation)[._-]/i.test(text)
  );
}

function dedupe(values: string[]) {
  const seen = new Set<string>();
  return values.filter((value) => {
    if (!value || seen.has(value)) return false;
    seen.add(value);
    return true;
  });
}

function sourcePartLabel(part: string) {
  const key = normalizeKey(part);
  if (SOURCE_LABELS[key]) return SOURCE_LABELS[key];
  if (isInternalLike(part)) return "系统数据";
  return part;
}

export function sourceLabel(source: unknown, fallback = "业务数据") {
  const labels = dedupe(splitSource(source).map(sourcePartLabel));
  if (!labels.length) return fallback;
  return labels.join("、");
}

export function roleLabel(role: unknown, fallback = "待主管确认") {
  const text = String(role ?? "").trim();
  if (!text) return fallback;
  const key = normalizeKey(text);
  if (ROLE_LABELS[key]) return ROLE_LABELS[key];
  if (isInternalLike(text)) return fallback;
  return text;
}

export function readinessLabel(status: unknown) {
  const text = String(status ?? "").trim();
  if (!text) return "";
  return READINESS_LABELS[normalizeKey(text)] || text;
}

export function engineLabel(engine: unknown, fallback = "确定性规则模板") {
  const text = String(engine ?? "").trim();
  if (!text) return fallback;
  return ENGINE_LABELS[normalizeKey(text)] || text;
}

export function factMeta(fact: any) {
  const status = readinessLabel(fact?.note || fact?.status);
  const source = sourceLabel(fact?.source, "");
  return [status, source ? `数据来源：${source}` : ""].filter(Boolean).join(" · ");
}

export function evidenceFallbackLabel(ref: unknown, fallback = "证据已记录") {
  const text = String(ref ?? "").trim();
  if (!text) return fallback;
  const translatedSource = sourceLabel(text, "");
  if (translatedSource && translatedSource !== text && translatedSource !== "系统数据") return translatedSource;
  if (isInternalLike(text)) return fallback;
  return text;
}
