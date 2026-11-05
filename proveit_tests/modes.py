"""Operating modes: observe / escalate / block_unattended."""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    OBSERVE = "observe"
    ESCALATE = "escalate"
    BLOCK_UNATTENDED = "block_unattended"


def resolve_mode(raw: str | None) -> Mode:
    if not raw:
        return Mode.OBSERVE
    key = str(raw).strip().lower().replace("-", "_")
    aliases = {
        "observe": Mode.OBSERVE,
        "warn": Mode.OBSERVE,
        "escalate": Mode.ESCALATE,
        "approve": Mode.ESCALATE,
        "block_unattended": Mode.BLOCK_UNATTENDED,
        "unattended": Mode.BLOCK_UNATTENDED,
        "cron": Mode.BLOCK_UNATTENDED,
        "block": Mode.BLOCK_UNATTENDED,
    }
    return aliases.get(key, Mode.OBSERVE)
