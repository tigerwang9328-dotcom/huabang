"""人事类审批解析：请假 / 出差 / 外出 / 考勤相关。"""
from typing import Optional

from app.modules.dingtalk.sync.finance_parser import categorize

HR_CATEGORIES = ("leave", "business_trip", "attendance")


def is_hr_category(category: Optional[str]) -> bool:
    return category in HR_CATEGORIES


def parse_hr_summary(inst: dict) -> Optional[dict]:
    """把人事类审批实例归纳为简要信息（MVP：仅分类与申请人，明细后续扩展）。"""
    cat = inst.get("_category")
    if not is_hr_category(cat):
        return None
    return {
        "category": cat,
        "applicant_user_id": inst.get("originator_userid"),
        "applicant_name": inst.get("_originator_name"),
        "department_name": inst.get("originator_dept_name"),
        "process_name": inst.get("_process_name"),
    }


__all__ = ["categorize", "is_hr_category", "parse_hr_summary", "HR_CATEGORIES"]
