"""Fail-closed write gates for Finance V2.0."""

from __future__ import annotations

from dataclasses import dataclass


class FeatureGateError(PermissionError):
    pass


@dataclass(frozen=True)
class GateScope:
    scope_type: str
    scope_key: str
    gate_name: str
    enabled: bool


_COMMAND_GATES = {
    "draft": "draft_enabled",
    "review": "review_enabled",
    "post": "post_enabled",
    "source_sync": "source_sync_enabled",
}


def assert_command_enabled(
    gates: list[GateScope],
    *,
    command: str,
    environment: str,
    book: str,
    role: str,
    source: str | None = None,
) -> None:
    """Allow reads always; require explicit enabled values at every configured scope."""

    if command == "read":
        return
    if any(gate.gate_name == "emergency_stop" and gate.enabled for gate in gates):
        raise FeatureGateError("emergency stop blocks all finance writes")
    gate_name = _COMMAND_GATES.get(command)
    if not gate_name:
        raise FeatureGateError(f"unknown finance command: {command}")
    targets = [("global", "*"), ("environment", environment), ("book", book), ("role", role)]
    if source:
        targets.append(("source", source))
    for scope_type, scope_key in targets:
        matching = [gate for gate in gates if gate.gate_name == gate_name and gate.scope_type == scope_type and gate.scope_key == scope_key]
        if matching and not matching[-1].enabled:
            raise FeatureGateError(f"finance gate disabled at {scope_type}:{scope_key}")
    if not any(gate.gate_name == gate_name and gate.scope_type == "global" and gate.scope_key == "*" and gate.enabled for gate in gates):
        raise FeatureGateError(f"finance gate is not globally enabled: {gate_name}")
