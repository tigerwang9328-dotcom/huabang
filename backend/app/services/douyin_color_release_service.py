"""A/B/C/D release stage switch for Douyin color analytics v3.1.

Pure-function service that enforces the staged rollout contract:

  Stage A -> collectors + base storage
  Stage B -> annotation + metric computation
  Stage C -> reports + ranking
  Stage D -> full release (including ``bounce_report_enabled``)

Rules enforced here:

  * Stages only move forward (A -> B -> C -> D), never backward or sideways.
  * ``bounce_report_enabled`` may only be turned on when
    ``MetricSemanticValidation`` reports ``bounce_semantics_status`` in
    ``{'verified_lower_is_better', 'verified_higher_is_better'}``.
  * Failures only flip the relevant flag; they never delete raw evidence or
    new tables (that concern is owned by callers, not by this module).

The functions operate on plain ``Mapping`` config snapshots and return new
``dict`` values, so they are trivially unit-testable without a database. The
same gating logic is mirrored at the database level by the
``ck_release_stage_current`` and ``ck_release_stage_bounce_gating`` CHECK
constraints on ``douyin.release_stage_configurations``.
"""

from __future__ import annotations

from typing import Any, Mapping


STAGE_ORDER: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3}

#: Bounce semantics statuses that satisfy MetricSemanticValidation and thus
#: permit ``bounce_report_enabled`` to be switched on.
_VERIFIED_BOUNCE_STATUSES: frozenset[str] = frozenset(
    ("verified_lower_is_better", "verified_higher_is_better")
)


def can_advance_stage(*, current_stage: Any, target_stage: Any) -> bool:
    """Return ``True`` only when ``target_stage`` strictly follows ``current_stage``.

    Stage progression is defined by :data:`STAGE_ORDER`. Anything that is not a
    forward move (backward, same stage, unknown value, non-string) is rejected.
    """
    if not isinstance(current_stage, str) or not isinstance(target_stage, str):
        return False
    cur = STAGE_ORDER.get(current_stage)
    tgt = STAGE_ORDER.get(target_stage)
    if cur is None or tgt is None:
        return False
    return tgt > cur


def advance_stage(*, config: Mapping[str, Any], target_stage: str) -> dict[str, Any]:
    """Return a copy of ``config`` with ``current_stage`` moved to ``target_stage``.

    Raises :class:`ValueError` with code ``invalid_stage_transition`` when the
    requested move is not a forward advance.
    """
    if not can_advance_stage(
        current_stage=config.get("current_stage"), target_stage=target_stage
    ):
        raise ValueError("invalid_stage_transition")
    updated: dict[str, Any] = dict(config)
    updated["current_stage"] = target_stage
    return updated


def can_enable_bounce_report(*, bounce_semantics_status: Any) -> bool:
    """Return ``True`` only when the bounce semantics status is verified."""
    return (
        isinstance(bounce_semantics_status, str)
        and bounce_semantics_status in _VERIFIED_BOUNCE_STATUSES
    )


def enable_bounce_report(
    *, config: Mapping[str, Any], bounce_semantics_status: str
) -> dict[str, Any]:
    """Return a copy of ``config`` with ``bounce_report_enabled`` set to ``True``.

    Raises :class:`ValueError` with code ``bounce_semantics_not_verified`` when
    the semantics status is not one of the verified values. This mirrors the
    database CHECK constraint ``ck_release_stage_bounce_gating`` so that no
    constraint-violating config can be produced through the service.
    """
    if not can_enable_bounce_report(bounce_semantics_status=bounce_semantics_status):
        raise ValueError("bounce_semantics_not_verified")
    updated: dict[str, Any] = dict(config)
    updated["bounce_report_enabled"] = True
    updated["bounce_semantics_status"] = bounce_semantics_status
    return updated


def disable_bounce_report(*, config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``config`` with ``bounce_report_enabled`` set to ``False``.

    Disabling only flips the flag; ``bounce_semantics_status`` is preserved so
    the audit trail of the last validation remains readable.
    """
    updated: dict[str, Any] = dict(config)
    updated["bounce_report_enabled"] = False
    return updated
