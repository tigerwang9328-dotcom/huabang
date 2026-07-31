export const MUMAREN_FINANCE_CENTER_ROOT = "/app/finance-center/mumaren";

export type MumarenFinanceCapabilityAvailability = "available" | "planned_backend";

export interface MumarenFinanceCapability {
  title: string;
  description: string;
  sourceModule: string;
  availability: MumarenFinanceCapabilityAvailability;
  unavailableReason?: string;
}

export interface MumarenFinanceCenterNavigationItem {
  key: "workspace" | "vouchers" | "ledgers" | "ar-ap" | "business" | "tax" | "operations" | "reports" | "history";
  title: string;
  path: string;
}

export const mumarenFinanceCenterNavigation: MumarenFinanceCenterNavigationItem[] = [
  { key: "workspace", title: "工作台", path: MUMAREN_FINANCE_CENTER_ROOT },
  { key: "vouchers", title: "凭证", path: `${MUMAREN_FINANCE_CENTER_ROOT}/vouchers` },
  { key: "ledgers", title: "账簿", path: `${MUMAREN_FINANCE_CENTER_ROOT}/ledgers` },
  { key: "ar-ap", title: "应收应付", path: `${MUMAREN_FINANCE_CENTER_ROOT}/ar-ap` },
  { key: "business", title: "业务台账", path: `${MUMAREN_FINANCE_CENTER_ROOT}/business` },
  { key: "tax", title: "税务", path: `${MUMAREN_FINANCE_CENTER_ROOT}/tax` },
  { key: "operations", title: "经营报表", path: `${MUMAREN_FINANCE_CENTER_ROOT}/operations` },
  { key: "reports", title: "报表", path: `${MUMAREN_FINANCE_CENTER_ROOT}/reports` },
  { key: "history", title: "历史归档", path: `${MUMAREN_FINANCE_CENTER_ROOT}/history` },
];

export const mumarenFinanceCapabilityGroups = {
  arAp: {
    title: "应收应付",
    summary: "以牧马人应收、应付与账龄分析领域模型为基线；当前不调用旧华邦财务接口。",
    capabilities: [
      { title: "应收单据", description: "客户应收、回款与未收余额。", sourceModule: "finance_module/api/ar_ap.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
      { title: "应付单据", description: "供应商应付、付款与未付余额。", sourceModule: "finance_module/api/ar_ap.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
      { title: "账龄分析", description: "按 30/60/90/120 天区间查看往来余额。", sourceModule: "finance_module/api/ar_ap.py", availability: "planned_backend", unavailableReason: "等待独立 AR/AP 查询接口。" },
    ] satisfies MumarenFinanceCapability[],
  },
  business: {
    title: "业务台账",
    summary: "牧马人业务台账覆盖出纳、资产、发票、工资和费用；华邦适配必须使用新模块独立表。",
    capabilities: [
      { title: "出纳与银行对账", description: "现金账户、银行流水与对账差异。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
      { title: "固定资产", description: "资产卡片、折旧与处置台账。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
      { title: "发票与费用", description: "发票登记、费用明细与凭证关联。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
      { title: "工资台账", description: "工资、社保、公积金、个税与实发核对。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
    ] satisfies MumarenFinanceCapability[],
  },
  tax: {
    title: "税务",
    summary: "牧马人税务领域包含税种、申报期、计税金额、税额与缴纳状态；首版不自动生成凭证。",
    capabilities: [
      { title: "税务记录", description: "税种、所属期间、计税金额与税额登记。", sourceModule: "finance_module/api/tax.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
      { title: "申报与缴纳", description: "申报状态、缴税记录与人工凭证关联。", sourceModule: "finance_module/api/tax.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
    ] satisfies MumarenFinanceCapability[],
  },
  operations: {
    title: "经营报表",
    summary: "牧马人经营分析、日报、广告费、销售月报、店铺组和退货统计保留为独立能力清单。",
    capabilities: [
      { title: "数据罗盘", description: "经营指标与财务分析钻取。", sourceModule: "finance_module/api/compass.py", availability: "planned_backend", unavailableReason: "等待华邦数据来源与独立接口核实。" },
      { title: "日报与广告费", description: "财务日报、日广告费与统一日导入。", sourceModule: "finance_module/api/daily_report.py", availability: "planned_backend", unavailableReason: "百胜、钉钉正式适配不在首版范围。" },
      { title: "销售与店铺报告", description: "销售月报、店铺组报告与退货统计。", sourceModule: "finance_module/api/sales_monthly_report.py", availability: "planned_backend", unavailableReason: "等待独立业务数据接口适配。" },
      { title: "扩展报表", description: "牧马人扩展财务报表与经营汇总。", sourceModule: "finance_module/api/reports_extra.py", availability: "planned_backend", unavailableReason: "后端适配待完成，当前不可录入。" },
    ] satisfies MumarenFinanceCapability[],
  },
} as const;

export const mumarenFinanceCenterMenuItem = {
  path: MUMAREN_FINANCE_CENTER_ROOT,
  label: "财务中心",
  permission: "mumaren_finance_center:access",
};
