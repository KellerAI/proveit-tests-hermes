"""ProveIt Tests — Hermes Agent native plugin.

Catches an agent weakening tests to get to green. Deterministic AST + regex.
No LLM. Not unbypassable.

register(ctx) is the Hermes entry point. Pure-Python unit tests import
proveit_tests.* directly and do not need Hermes installed.
"""

from __future__ import annotations

from typing import Any

from proveit_tests.hooks.cron import ContextCronProbe
from proveit_tests.hooks.runtime import ProveItRuntime
from proveit_tests.modes import resolve_mode

__version__ = "0.1.0"

# Module-level runtime so slash command + hooks share state within a process.
_RUNTIME: ProveItRuntime | None = None


def _settings(ctx: Any) -> dict[str, Any]:
    # Hermes PluginContext exposes config / settings differently across versions.
    for attr in ("settings", "config", "plugin_config"):
        val = getattr(ctx, attr, None)
        if isinstance(val, dict):
            return val
    get = getattr(ctx, "get_setting", None)
    if callable(get):
        try:
            return dict(get() or {})
        except Exception:
            pass
    return {}


def _ledger_dir(ctx: Any, settings: dict[str, Any]) -> str | None:
    override = (settings.get("receipt_dir") or "").strip()
    if override:
        return override
    for name in ("plugin_data_dir", "data_dir"):
        fn = getattr(ctx, name, None)
        if callable(fn):
            try:
                return str(fn())
            except Exception:
                pass
        elif isinstance(fn, str) and fn:
            return fn
    db = getattr(ctx, "plugin_db", None)
    if callable(db):
        try:
            # Some builds return a path-like helper; ignore if not
            pass
        except Exception:
            pass
    return None


def _get_runtime() -> ProveItRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        # Lazy default for unit-style imports
        _RUNTIME = ProveItRuntime()
    return _RUNTIME


def register(ctx: Any) -> None:
    """Hermes plugin entry point.

    Registers documented hooks + `/proveit` slash command. Callbacks accept
    ``**kwargs`` so additive Hermes payload fields stay backward-compatible.
    Escalate directives include ``rule_key`` for per-rule approval persistence.
    Not unbypassable — see README "Hook feasibility".
    """
    global _RUNTIME
    settings = _settings(ctx)
    mode = resolve_mode(settings.get("mode"))
    _RUNTIME = ProveItRuntime(
        mode=mode,
        ledger_dir=_ledger_dir(ctx, settings),
        cron=ContextCronProbe(ctx),
        test_globs=settings.get("test_path_globs"),
        ci_globs=settings.get("ci_path_globs"),
        one_shot_nudge=bool(settings.get("one_shot_nudge", True)),
        session_id=str(getattr(ctx, "session_id", "") or ""),
    )
    rt = _RUNTIME

    def pre_tool_call(tool_name: str, args: dict | None = None, **kwargs):
        return rt.on_pre_tool_call(tool_name, args=args or {}, **kwargs)

    def post_tool_call(tool_name: str, args: dict | None = None, result: str = "", **kwargs):
        rt.on_post_tool_call(tool_name, args=args or {}, result=result or "", **kwargs)

    def transform_tool_result(tool_name: str = "", args: dict | None = None, result: str = "", **kwargs):
        return rt.on_transform_tool_result(tool_name=tool_name, args=args or {}, result=result or "", **kwargs)

    def pre_verify(changed_paths=None, attempt: int = 0, final_response: str = "", **kwargs):
        return rt.on_pre_verify(
            changed_paths=changed_paths or [],
            attempt=attempt,
            final_response=final_response or "",
            **kwargs,
        )

    def on_session_start(session_id: str = "", **kwargs):
        rt.session_id = session_id or rt.session_id
        rt._nudged = False
        rt._unexplained = []
        rt._pending_warnings = []

    def on_session_end(**kwargs):
        pass

    def proveit_cmd(raw_args: str = "", **kwargs):
        # Hermes passes the raw argument string positionally; **kwargs carries
        # optional session_id / platform / source when the handler opts in.
        return rt.slash_proveit(raw_args or "")

    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("transform_tool_result", transform_tool_result)
    ctx.register_hook("pre_verify", pre_verify)
    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("on_session_end", on_session_end)
    ctx.register_command(
        "proveit",
        proveit_cmd,
        description="Show the ProveIt Tests receipt ledger for this session",
    )
