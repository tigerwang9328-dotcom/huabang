"""Safe, explicit operational metric policies for Finance V2.0.

The V2.0 monitoring endpoint may expose only aggregate counters.  In
particular it must not turn an unimplemented collector into a zero-valued
metric, and it must never put voucher, counterparty, account, or user data in
metric labels.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


MetricAvailability = Literal["available", "unavailable"]


@dataclass(frozen=True)
class FinanceMetricPolicy:
    metric_key: str
    availability: MetricAvailability
    threshold: str
    owner: str
    notification_route: str
    notification_configured: bool
    close_condition: str
    labels: tuple[str, ...] = ()
    unavailable_reason: str | None = None

    def as_payload(self, value: int | float | None = None) -> dict[str, object]:
        """Return a JSON-safe policy and aggregate value without sensitive labels."""

        payload = asdict(self)
        payload["labels"] = list(self.labels)
        payload["value"] = value if self.availability == "available" else None
        return payload


def _available(metric_key: str, threshold: str, close_condition: str) -> FinanceMetricPolicy:
    return FinanceMetricPolicy(
        metric_key=metric_key,
        availability="available",
        threshold=threshold,
        owner="finance_operations",
        notification_route="finance-v2-oncall",
        notification_configured=False,
        close_condition=close_condition,
    )


def _unavailable(metric_key: str, threshold: str, unavailable_reason: str) -> FinanceMetricPolicy:
    return FinanceMetricPolicy(
        metric_key=metric_key,
        availability="unavailable",
        threshold=threshold,
        owner="finance_operations",
        notification_route="finance-v2-oncall",
        notification_configured=False,
        close_condition="采集器接入、演练并经责任人确认后才允许关闭告警。",
        unavailable_reason=unavailable_reason,
    )


FINANCE_METRIC_CATALOG: dict[str, FinanceMetricPolicy] = {
    "posting_attempt_failed": _available(
        "posting_attempt_failed",
        ">=1 次失败 / 5 分钟",
        "最近 15 分钟无新增失败，失败凭证及独立 attempt 已由财务人员核对。",
    ),
    "voucher_unbalanced_blocked": _unavailable(
        "voucher_unbalanced_blocked",
        ">=1 次阻断 / 5 分钟",
        "借贷不平属于 API 域校验拒绝，尚未持久化为无敏感信息的聚合计数。",
    ),
    "history_import_conflicted": _available(
        "history_import_conflicted",
        ">=1 个冲突批次",
        "冲突来源键、哈希和处理决定已完成审计，且后续核验无冲突。",
    ),
    "source_inbox_backlog": _unavailable(
        "source_inbox_backlog",
        ">=100 条或最老记录 >=15 分钟",
        "V2.0 来源收件箱尚未启用；来源系统仅允许只读 preview。",
    ),
    "exception_queue_backlog": _unavailable(
        "exception_queue_backlog",
        ">=20 条或最老记录 >=30 分钟",
        "V2.0 来源异常队列尚未启用；不得将不存在的队列报告为零。",
    ),
    "lock_wait": _unavailable(
        "lock_wait",
        ">=30 秒",
        "生产应用受限数据库角色不读取 PostgreSQL 全局会话统计；需独立受控采集器。",
    ),
    "deadlock": _unavailable(
        "deadlock",
        ">=0 次 / 5 分钟",
        "生产应用受限数据库角色不读取 PostgreSQL 全局死锁统计；需独立受控采集器。",
    ),
    "period_close_failed": _available(
        "period_close_failed",
        ">=1 次失败 / 期间",
        "失败结账批次已复核、期间状态保持可控，且后续结账检查通过。",
    ),
    "export_failure": _unavailable(
        "export_failure",
        ">=1 次失败 / 5 分钟",
        "V2.0 不提供财务导出写入/队列能力，尚无可采集的导出失败事实源。",
    ),
    "api_5xx_rate": _unavailable(
        "api_5xx_rate",
        ">=1% / 5 分钟",
        "Nginx/API 聚合错误率尚未接入 Finance V2 专属、脱敏的指标采集器。",
    ),
    "balance_difference_alert": _unavailable(
        "balance_difference_alert",
        ">0 个未解决差异",
        "最终期初、日对账和来源增量尚未切换，不能伪造余额差异指标。",
    ),
}


def monitoring_payload(values: dict[str, int | float]) -> list[dict[str, object]]:
    """Attach available aggregates to the full, fail-transparent metric catalog."""

    return [policy.as_payload(values.get(metric_key)) for metric_key, policy in FINANCE_METRIC_CATALOG.items()]
