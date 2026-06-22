"""财务类审批解析：报销 / 付款 / 费用。分类 + 金额 + 申请人 + 状态。"""
import re
from datetime import datetime
from typing import Optional


def categorize(process_name: Optional[str], title: Optional[str]) -> str:
    t = f"{process_name or ''} {title or ''}"
    if "报销" in t:
        return "reimbursement"
    if "付款" in t:
        return "payment"
    if "请假" in t:
        return "leave"
    if "出差" in t:
        return "business_trip"
    if "外出" in t:
        return "business_trip"
    if any(k in t for k in ("考勤", "补卡", "打卡", "加班")):
        return "attendance"
    return "other"


def _parse_number(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))
    return float(m.group()) if m else None


def extract_amount(form_values) -> Optional[float]:
    """从审批表单中提取金额。"""
    for c in form_values or []:
        name = c.get("name") or c.get("label") or ""
        if any(k in name for k in ("金额", "费用", "合计", "总额", "amount", "money", "报销", "付款")):
            num = _parse_number(c.get("value"))
            if num is not None:
                return num
    return None


def _parse_dt(v) -> Optional[datetime]:
    if not v:
        return None
    s = str(v).replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt) + 2] if fmt == "%Y-%m-%d %H:%M:%S" else s[:10], fmt)
        except ValueError:
            continue
    return None


def parse_finance_record(inst: dict) -> Optional[dict]:
    """把一条审批实例(已带 _category/_process_name)解析为 finance_expense_records 行。

    仅对 reimbursement / payment 生效，其它返回 None。
    """
    cat = inst.get("_category")
    if cat not in ("reimbursement", "payment"):
        return None
    form = inst.get("form_component_values") or []
    dt = _parse_dt(inst.get("create_time"))
    return {
        "source": "dingtalk",
        "source_instance_id": inst.get("_process_instance_id"),
        "applicant_user_id": inst.get("originator_userid"),
        "applicant_name": inst.get("_originator_name"),
        "department_name": inst.get("originator_dept_name"),
        "expense_type": inst.get("_process_name"),
        "amount": extract_amount(form),
        "expense_date": dt.date() if dt else None,
        "approval_status": inst.get("status"),
        "payment_status": "paid" if inst.get("result") == "agree" and cat == "payment" else "unknown",
        "category": cat,
        "raw_payload": inst,
    }
