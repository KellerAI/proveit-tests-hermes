"""Clean interface for detecting unattended / cron execution.

Hermes exposes `ctx.current_cron_execution()` which returns a frozen
CronExecution or None. We wrap that behind CronProbe so unit tests can
stub it without importing Hermes.
"""

from __future__ import annotations

from typing import Any, Protocol


class CronProbe(Protocol):
    def is_unattended(self) -> bool:
        """True when the current execution should fail closed (cron / unattended)."""
        ...


class NullCronProbe:
    """Default: never unattended (safe for unit tests and observe mode)."""

    def is_unattended(self) -> bool:
        return False


class ContextCronProbe:
    """Uses Hermes PluginContext.current_cron_execution() when available."""

    def __init__(self, ctx: Any):
        self._ctx = ctx

    def is_unattended(self) -> bool:
        fn = getattr(self._ctx, "current_cron_execution", None)
        if not callable(fn):
            return False
        try:
            return fn() is not None
        except Exception:
            return False


class FlagCronProbe:
    """Test double: fixed boolean."""

    def __init__(self, flag: bool = False):
        self.flag = flag

    def is_unattended(self) -> bool:
        return bool(self.flag)
