"""Finding records emitted by detectors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


from .engine.policy import Tier, finding_tier


class Severity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class Finding:
    kind: str
    message: str
    severity: Severity
    path: str = ""
    line: int | None = None
    detail: str = ""
    waived: bool = False
    waiver_reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    tier: Tier | None = None

    def __post_init__(self) -> None:
        if self.tier is None:
            object.__setattr__(self, "tier", finding_tier(self.kind))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d

    def short(self) -> str:
        loc = self.path or "<command>"
        if self.line is not None:
            loc = f"{loc}:{self.line}"
        tag = "[waived] " if self.waived else ""
        return f"{tag}{self.kind} @ {loc}: {self.message}"
