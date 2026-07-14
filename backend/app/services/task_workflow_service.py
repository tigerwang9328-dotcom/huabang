"""Pure task workflow rules shared by API handlers and tests."""
from typing import Iterable, Optional


MANAGER_ROLE_CODES = frozenset({
    "super_admin",
    "boss",
    "ceo",
    "area_supervisor",
    "operation_manager",
})

ASSIGNEE_ROLE_ALIASES = {
    "operation": "operation_manager",
    "老板": "boss",
    "总经理": "ceo",
    "督导": "area_supervisor",
    "门店督导": "area_supervisor",
    "店长": "store_manager",
    "导购": "guide",
    "运营": "operation_manager",
    "运营经理": "operation_manager",
    "商品经理": "product_manager",
    "商品部": "product_manager",
    "仓库主管": "warehouse_manager",
    "财务经理": "finance_manager",
    "财务": "finance_manager",
    "会员运营": "operation_manager",
}


class TaskTransitionError(ValueError):
    pass


def next_task_status(current: str, action: str, *, review_result: Optional[str] = None) -> str:
    if action == "confirm" and current == "draft":
        return "pending"
    if action == "feedback" and current in {"pending", "processing", "overdue"}:
        return "feedback_submitted"
    if action == "review" and current == "feedback_submitted":
        if review_result == "passed":
            return "review_passed"
        if review_result == "failed":
            return "processing"
        raise TaskTransitionError("复查结果只能是 passed 或 failed")
    if action == "close" and current == "review_passed":
        return "closed"
    raise TaskTransitionError(f"任务状态 {current} 不允许执行 {action}")


def can_manage_tasks(role_codes: Iterable[str]) -> bool:
    return bool(MANAGER_ROLE_CODES.intersection(set(role_codes)))


def normalize_assignee_roles(assignee_role: Optional[str]) -> set[str]:
    if not assignee_role:
        return set()
    tokens = {
        part.strip()
        for part in str(assignee_role).replace("/", " ").split()
        if part.strip()
    }
    return {ASSIGNEE_ROLE_ALIASES.get(token, token) for token in tokens}


def can_submit_feedback(
    assignee_id: Optional[int],
    assignee_role: Optional[str],
    current_user_id: int,
    role_codes: Iterable[str],
) -> bool:
    if assignee_id is not None:
        return int(assignee_id) == int(current_user_id)
    if assignee_role:
        return bool(normalize_assignee_roles(assignee_role).intersection(set(role_codes)))
    return False
