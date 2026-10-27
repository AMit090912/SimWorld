"""Action contract shared by every environment.

Actions are plain JSON objects. They are parsed strictly once, then validated
against world rules by the environment. Nothing here mutates world state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_ID_LENGTH = 64
ACTION_TYPES = {"move", "wait", "pickup", "deliver", "refuel", "set_phase"}
PHASES = {"NS", "EW"}


class ActionFormatError(ValueError):
    """Raised when an action does not match the wire contract at all."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Action:
    type: str
    target: str | None = None
    package_id: str | None = None
    package_ids: tuple[str, ...] = field(default_factory=tuple)
    amount: float | None = None
    intersection: str | None = None
    phase: str | None = None

    @classmethod
    def parse(cls, raw: Any) -> "Action":
        if not isinstance(raw, dict):
            raise ActionFormatError("malformed_action", "Action must be a JSON object.")

        action_type = raw.get("type")
        if not isinstance(action_type, str):
            raise ActionFormatError("malformed_action", "Action field 'type' must be a string.")
        action_type = action_type.strip().lower()
        if action_type not in ACTION_TYPES:
            raise ActionFormatError(
                "unknown_action_type",
                f"Unknown action type '{action_type}'. Expected one of: {sorted(ACTION_TYPES)}.",
            )

        allowed = {
            "move": {"type", "target"},
            "wait": {"type"},
            "pickup": {"type", "package_id", "package_ids"},
            "deliver": {"type", "package_id"},
            "refuel": {"type", "amount"},
            "set_phase": {"type", "intersection", "phase"},
        }[action_type]
        unknown = set(raw) - allowed
        if unknown:
            raise ActionFormatError(
                "malformed_action",
                f"Unexpected field(s) for '{action_type}': {sorted(unknown)}. "
                f"Allowed fields: {sorted(allowed)}.",
            )

        def read_id(value: Any, name: str) -> str:
            if not isinstance(value, str) or not value.strip():
                raise ActionFormatError("malformed_action", f"Field '{name}' must be a non-empty string.")
            value = value.strip()
            if len(value) > MAX_ID_LENGTH:
                raise ActionFormatError("malformed_action", f"Field '{name}' is too long.")
            return value

        if action_type == "move":
            return cls(type=action_type, target=read_id(raw.get("target"), "target"))

        if action_type == "deliver":
            return cls(type=action_type, package_id=read_id(raw.get("package_id"), "package_id"))

        if action_type == "pickup":
            ids: list[str] = []
            if "package_ids" in raw:
                raw_ids = raw["package_ids"]
                if not isinstance(raw_ids, list) or not raw_ids:
                    raise ActionFormatError(
                        "malformed_action", "Field 'package_ids' must be a non-empty array of strings."
                    )
                if len(raw_ids) > 8:
                    raise ActionFormatError("malformed_action", "'package_ids' accepts at most 8 items.")
                ids = [read_id(item, "package_ids[]") for item in raw_ids]
            elif "package_id" in raw:
                ids = [read_id(raw.get("package_id"), "package_id")]
            else:
                raise ActionFormatError(
                    "malformed_action", "pickup requires 'package_id' or 'package_ids'."
                )
            if len(set(ids)) != len(ids):
                raise ActionFormatError("malformed_action", "'package_ids' contains duplicates.")
            # Order is semantically irrelevant; canonicalise so identical loads
            # produce identical state hashes.
            return cls(type=action_type, package_ids=tuple(sorted(ids)))

        if action_type == "refuel":
            amount = raw.get("amount")
            if amount is not None:
                if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                    raise ActionFormatError("malformed_action", "Field 'amount' must be a number.")
                amount = float(amount)
                if amount <= 0 or amount > 10:
                    raise ActionFormatError("malformed_action", "Field 'amount' must be between 0 and 10 litres.")
            return cls(type=action_type, amount=amount)

        if action_type == "set_phase":
            phase = raw.get("phase")
            if not isinstance(phase, str) or phase.strip().upper() not in PHASES:
                raise ActionFormatError("malformed_action", "Field 'phase' must be 'NS' or 'EW'.")
            return cls(
                type=action_type,
                intersection=read_id(raw.get("intersection"), "intersection"),
                phase=phase.strip().upper(),
            )

        return cls(type=action_type)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.target is not None:
            out["target"] = self.target
        if self.package_id is not None:
            out["package_id"] = self.package_id
        if self.package_ids:
            out["package_ids"] = list(self.package_ids)
        if self.amount is not None:
            out["amount"] = self.amount
        if self.intersection is not None:
            out["intersection"] = self.intersection
        if self.phase is not None:
            out["phase"] = self.phase
        return out


@dataclass
class ApplyResult:
    ok: bool
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, message: str, **details: Any) -> "ApplyResult":
        return cls(True, "ok", message, details)

    @classmethod
    def rejected(cls, code: str, message: str, **details: Any) -> "ApplyResult":
        return cls(False, code, message, details)