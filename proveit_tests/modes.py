"""Operating modes: block / escalate / warn."""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    BLOCK = "block"
    WARN = "warn"
    OBSERVE = "warn"
    ESCALATE = "escalate"
    BLOCK_UNATTENDED = "block_unattended"


def resolve_mode(raw: str | None) -> Mode:
    if not raw:
        return Mode.BLOCK
    key = str(raw).strip().lower().replace("-", "_")
    aliases = {
        "observe": Mode.OBSERVE,
        "warn": Mode.OBSERVE,
        "escalate": Mode.ESCALATE,
        "approve": Mode.ESCALATE,
        "block_unattended": Mode.BLOCK_UNATTENDED,
        "unattended": Mode.BLOCK_UNATTENDED,
        "cron": Mode.BLOCK_UNATTENDED,
        "block": Mode.BLOCK,
    }
    return aliases.get(key, Mode.BLOCK)
