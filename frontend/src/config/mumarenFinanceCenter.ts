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
  key:
    | "workspace"
    | "vouchers"
    | "ledgers"
    | "ar-ap"
    | "business"
    | "tax"
    | "operations"
    | "reports"
    | "history"
    | "accounts"
    | "closing"
    | "cashier"
    | "assets"
    | "invoices"
    | "payroll"
    | "payments";
  title: string;
  path: string;
}

export const mumarenFinanceCenterNavigation: MumarenFinanceCenterNavigationItem[] = [
  { key: "workspace", title: "工作台", path: MUMAREN_FINANCE_CENTER_ROOT },
  { key: "vouchers", title: "凭证", path: `${MUMAREN_FINANCE_CENTER_ROOT}/vouchers` },
  { key: "ledgers", title: "账簿", path: `${MUMAREN_FINANCE_CENTER_ROOT}/ledgers` },
  { key: "accounts", title: "科目", path: `${MUMAREN_FINANCE_CENTER_ROOT}/accounts` },
  { key: "ar-ap", title: "应收应付", path: `${MUMAREN_FINANCE_CENTER_ROOT}/ar-ap` },
  { key: "business", title: "业务台账", path: `${MUMAREN_FINANCE_CENTER_ROOT}/business` },
  { key: "tax", title: "税务", path: `${MUMAREN_FINANCE_CENTER_ROOT}/tax` },
  { key: "cashier", title: "出纳", path: `${MUMAREN_FINANCE_CENTER_ROOT}/cashier` },
  { key: "assets", title: "资产", path: `${MUMAREN_FINANCE_CENTER_ROOT}/assets` },
  { key: "invoices", title: "发票", path: `${MUMAREN_FINANCE_CENTER_ROOT}/invoices` },
  { key: "payroll", title: "薪资", path: `${MUMAREN_FINANCE_CENTER_ROOT}/payroll` },
  { key: "payments", title: "付款", path: `${MUMAREN_FINANCE_CENTER_ROOT}/payments` },
  { key: "operations", title: "经营报表", path: `${MUMAREN_FINANCE_CENTER_ROOT}/operations` },
  { key: "reports", title: "报表", path: `${MUMAREN_FINANCE_CENTER_ROOT}/reports` },
  { key: "closing", title: "期末结账", path: `${MUMAREN_FINANCE_CENTER_ROOT}/closing` },
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
  cashier: {
    title: "出纳",
    summary: "牧马人出纳领域覆盖资金账户、银行流水与日记账；华邦适配必须使用新模块独立表，不读取旧财务表。",
    capabilities: [
      { title: "资金账户", description: "银行/支付宝/微信/现金账户与期初余额。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "出纳独立后端适配待完成，当前不可新增账户。" },
      { title: "日记账与流水", description: "收支明细、对方、类别与备注登记。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "出纳独立后端适配待完成，当前不可录入流水。" },
      { title: "银行对账", description: "银行流水与账面余额的对账差异核销。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "对账独立接口待接入，当前不可对账。" },
      { title: "收支汇总", description: "今日/本月流入流出与净流入汇总。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "汇总独立接口待接入，当前不可查询。" },
    ] satisfies MumarenFinanceCapability[],
  },
  assets: {
    title: "固定资产",
    summary: "牧马人固定资产领域覆盖资产卡片、折旧与处置；华邦适配必须使用新模块独立表。",
    capabilities: [
      { title: "资产卡片", description: "资产编码、名称、分类、原值与购入日期。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "资产独立后端适配待完成，当前不可新增资产。" },
      { title: "折旧与净值", description: "累计折旧、净值与折旧年限维护。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "折旧独立接口待接入，当前不可计提折旧。" },
      { title: "资产处置", description: "资产报废、出售与处置台账。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "处置独立接口待接入，当前不可处置。" },
    ] satisfies MumarenFinanceCapability[],
  },
  invoices: {
    title: "发票",
    summary: "牧马人发票领域覆盖进项/销项发票登记与认证；华邦适配必须使用新模块独立表。",
    capabilities: [
      { title: "发票登记", description: "发票号码、方向、对方单位、金额与税额。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "发票独立后端适配待完成，当前不可录入发票。" },
      { title: "进项认证", description: "进项发票认证状态与税额抵扣。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "认证独立接口待接入，当前不可认证。" },
      { title: "发票台账", description: "按期间、方向汇总进销项发票与税额。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "台账独立接口待接入，当前不可查询。" },
    ] satisfies MumarenFinanceCapability[],
  },
  payroll: {
    title: "薪资",
    summary: "牧马人薪资领域覆盖工资、社保、公积金、个税与实发核对；华邦适配必须使用新模块独立表。",
    capabilities: [
      { title: "工资台账", description: "员工、部门、基本工资、奖金与应发合计。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "薪资独立后端适配待完成，当前不可录入工资。" },
      { title: "社保公积金与个税", description: "社保、公积金、个税扣缴与实发核对。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "扣缴独立接口待接入，当前不可录入扣款。" },
      { title: "薪资发放", description: "按期间发放状态与实发汇总。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "发放独立接口待接入，当前不可发放。" },
    ] satisfies MumarenFinanceCapability[],
  },
  payments: {
    title: "付款",
    summary: "牧马人付款领域覆盖付款申请、审批与执行；华邦适配必须使用新模块独立表，不读取旧财务表。",
    capabilities: [
      { title: "付款申请", description: "付款单录入、往来单位与付款金额。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "付款独立后端适配待完成，当前不可录入付款单。" },
      { title: "付款审批", description: "付款单审批流程与状态流转。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "审批独立接口待接入，当前不可审批。" },
      { title: "付款执行", description: "付款执行确认与银行流水关联。", sourceModule: "finance_module/api/business.py", availability: "planned_backend", unavailableReason: "执行独立接口待接入，当前不可执行。" },
    ] satisfies MumarenFinanceCapability[],
  },
  closing: {
    title: "期末结账",
    summary: "期末结账独立后端适配尚未完成；在期间结账接口、预检规则与独立权限校验就绪前，本页不提供任何结账/反结账操作。",
    capabilities: [
      { title: "期间结账预检", description: "结账前对凭证完整性、借贷平衡、未审核单据进行预检。", sourceModule: "finance_module/api/closing.py", availability: "planned_backend", unavailableReason: "等待独立结账预检接口接入，当前不可操作。" },
      { title: "期末结账", description: "按会计期间执行期末结账，结账后该期间凭证不可再修改。", sourceModule: "finance_module/api/closing.py", availability: "planned_backend", unavailableReason: "等待独立结账接口接入，当前不可结账。" },
      { title: "结账状态查询", description: "查询各账簿各期间的结账状态与结账人。", sourceModule: "finance_module/api/closing.py", availability: "planned_backend", unavailableReason: "等待独立结账状态查询接口接入，当前不可查询。" },
    ] satisfies MumarenFinanceCapability[],
  },
} as const;

export const mumarenFinanceCenterMenuItem = {
  path: MUMAREN_FINANCE_CENTER_ROOT,
  label: "财务中心",
  permission: "mumaren_finance_center:access",
};
