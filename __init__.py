"""ProveIt Tests — Hermes Agent native plugin.

Catches an agent weakening tests to get to green. Deterministic AST + regex.
No LLM. Not unbypassable.

register(ctx) is the Hermes entry point. Hermes loads this directory as a
package (``submodule_search_locations=[plugin_dir]``) without putting it on
``sys.path``, so imports here must be relative. Pure-Python unit tests import
proveit_tests.* directly and do not need Hermes installed.
"""

from __future__ import annotations

from typing import Any

if __package__:
    # Hermes plugin loader: loaded as a package, plugin dir NOT on sys.path.
    from .proveit_tests.hooks.cron import ContextCronProbe
    from .proveit_tests.hooks.runtime import ProveItRuntime
    from .proveit_tests.modes import resolve_mode
else:  # pragma: no cover - pytest imports the rootdir __init__.py top-level
    from proveit_tests.hooks.cron import ContextCronProbe
    from proveit_tests.hooks.runtime import ProveItRuntime
    from proveit_tests.modes import resolve_mode

__version__ = "0.1.0"

# Module-level runtime so slash command + hooks share state within a process.
_RUNTIME: ProveItRuntime | None = None


_SETTING_KEYS = ("mode", "test_path_globs", "ci_path_globs", "receipt_dir", "one_shot_nudge")
_PLUGIN_NAME = "proveit-tests"


def _settings(ctx: Any) -> dict[str, Any]:
    """Read plugin settings.

    Real Hermes (>=0.22.7) exposes ``ctx.get_config(key, default)`` reading
    ``plugins.entries.proveit-tests.settings.<key>`` from config.yaml. Dict-style
    attributes are kept as a fallback for stand-in contexts in unit tests.
    """
    get_config = getattr(ctx, "get_config", None)
    if callable(get_config):
        out: dict[str, Any] = {}
        for key in _SETTING_KEYS:
            try:
                val = get_config(key, None)
            except Exception:
                val = None
            if val is not None:
                out[key] = val
        if out:
            return out
    for attr in ("settings", "config", "plugin_config"):
        val = getattr(ctx, attr, None)
        if isinstance(val, dict):
            return val
    return {}


def _ledger_dir(ctx: Any, settings: dict[str, Any]) -> str | None:
    override = str(settings.get("receipt_dir") or "").strip()
    if override:
        return override
    # Sanctioned Hermes durable-state root: <HERMES_HOME>/plugin-data/<name>/
    try:
        from plugins.plugin_storage import plugin_data_dir  # type: ignore[import-not-found]

        return str(plugin_data_dir(_PLUGIN_NAME))
    except Exception:
        pass
    for name in ("plugin_data_dir", "data_dir"):
        fn = getattr(ctx, name, None)
        if callable(fn):
            try:
                return str(fn())
            except Exception:
                pass
        elif isinstance(fn, str) and fn:
            return fn
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
