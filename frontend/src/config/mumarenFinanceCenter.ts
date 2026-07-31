export const MUMAREN_FINANCE_CENTER_ROOT = "/app/finance-center/mumaren";

export interface MumarenFinanceCenterNavigationItem {
  key: "workspace" | "vouchers" | "ledgers" | "reports" | "history";
  title: string;
  path: string;
}

export const mumarenFinanceCenterNavigation: MumarenFinanceCenterNavigationItem[] = [
  { key: "workspace", title: "工作台", path: MUMAREN_FINANCE_CENTER_ROOT },
  { key: "vouchers", title: "凭证", path: `${MUMAREN_FINANCE_CENTER_ROOT}/vouchers` },
  { key: "ledgers", title: "账簿", path: `${MUMAREN_FINANCE_CENTER_ROOT}/ledgers` },
  { key: "reports", title: "报表", path: `${MUMAREN_FINANCE_CENTER_ROOT}/reports` },
  { key: "history", title: "历史归档", path: `${MUMAREN_FINANCE_CENTER_ROOT}/history` },
];

export const mumarenFinanceCenterMenuItem = {
  path: MUMAREN_FINANCE_CENTER_ROOT,
  label: "财务中心",
  permission: "mumaren_finance_center:access",
};
