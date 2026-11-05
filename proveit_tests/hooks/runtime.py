"""ProveItRuntime — core logic callable from Hermes hooks or unit tests.

Hook wiring follows public Hermes plugin docs
(https://hermes-agent.nousresearch.com/docs/developer-guide/plugins and
https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks):

- `pre_tool_call` may return
  `{"action": "block", "message": ...}` or
  `{"action": "approve", "message": ..., "rule_key": ...}`
  (approve escalates to the human-approval gate; `rule_key` keeps per-rule
  allowlists from collapsing — see Hermes PR #59163 / #60504).
- `post_tool_call` is observer-only (return ignored).
- `transform_tool_result` may return a string that replaces the model-bound
  tool result (first string wins).
- `pre_verify` may return `{"action": "continue", "message": ...}` at the
  edited-code verify gate.
- Callbacks accept `**kwargs` for additive payload fields.
- Hook callbacks are fail-open in Hermes (exception → log + continue).

Hook feasibility (honest):
- `pre_tool_call` receives tool args. For Hermes `write_file` / `patch`, the
  proposed content is typically in `args` (`content`, `new_content`, `diff`,
  `patch`, etc.). We read the existing file from disk to diff. That is
  pre-edit enforcement for those tools.
- Shell rewrites (`cat > file`, `sed -i`, python -c writes) only expose the
  command string in pre_tool_call — we flag known escape-hatch commands there,
  and re-scan the file on `post_tool_call` when a test path was touched.
- This is NOT unbypassable: disable the plugin, use novel shell indirections,
  or edit outside watched globs and detectors will miss it. Hermes itself does
  not claim plugin hooks are a sandbox.

When proposed content is missing from args, we fall back to post-edit observe
on the next tool call / transform_tool_result and document that in STATUS.md.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from ..detectors.commands import detect_ci_diff, detect_command_weakenings
from ..detectors.js_ts import detect_js_ts_diff
from ..detectors.paths import is_ci_path, is_test_path
from ..detectors.python_ast import detect_python_diff
from ..findings import Finding
from ..modes import Mode, resolve_mode
from ..receipts.ledger import Ledger
from .cron import CronProbe, NullCronProbe

WRITE_TOOLS = {"write_file", "write", "create_file", "str_replace_editor"}
PATCH_TOOLS = {"patch", "apply_patch", "edit_file", "str_replace"}
TERMINAL_TOOLS = {"terminal", "shell", "shell_exec", "run_terminal_cmd", "bash", "execute"}


def _extract_path(args: dict[str, Any]) -> str:
    for key in ("path", "file_path", "file", "filename", "target"):
        v = args.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _extract_content(args: dict[str, Any]) -> str | None:
    for key in ("content", "new_content", "new_str", "contents", "text", "body"):
        v = args.get(key)
        if isinstance(v, str):
            return v
    # patch-style: old_str/new_str single replacement — caller handles via disk+patch
    return None


def _extract_command(args: dict[str, Any]) -> str:
    for key in ("command", "cmd", "script", "input"):
        v = args.get(key)
        if isinstance(v, str):
            return v
    return ""


def _read_disk(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _ext(path: str) -> str:
    return Path(path).suffix.lower()


class ProveItRuntime:
    def __init__(
        self,
        *,
        mode: Mode | str = Mode.OBSERVE,
        ledger_dir: str | Path | None = None,
        cron: CronProbe | None = None,
        test_globs: list[str] | None = None,
        ci_globs: list[str] | None = None,
        one_shot_nudge: bool = True,
        session_id: str = "",
    ):
        self.mode = resolve_mode(mode.value if isinstance(mode, Mode) else mode)
        self.cron = cron or NullCronProbe()
        self.test_globs = test_globs
        self.ci_globs = ci_globs
        self.one_shot_nudge = one_shot_nudge
        self.session_id = session_id
        if ledger_dir is None:
            ledger_dir = Path(tempfile.gettempdir()) / "proveit-tests-ledger"
        self.ledger = Ledger(ledger_dir)
        self._pending_warnings: list[str] = []
        self._unexplained: list[Finding] = []
        self._nudged = False
        self._last_receipt_digest = ""

    # ------------------------------------------------------------------ analyze
    def analyze_file_change(self, path: str, old: str, new: str) -> list[Finding]:
        findings: list[Finding] = []
        if is_test_path(path, self.test_globs):
            ext = _ext(path)
            if ext == ".py":
                findings.extend(detect_python_diff(old, new, path=path))
            elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
                findings.extend(detect_js_ts_diff(old, new, path=path))
        if is_ci_path(path, self.ci_globs):
            findings.extend(detect_ci_diff(old, new, path=path))
        return findings

    def analyze_command(self, command: str) -> list[Finding]:
        return detect_command_weakenings(command)

    # --------------------------------------------------------------- directives
    def decide(self, findings: list[Finding]) -> dict[str, Any] | None:
        """Return a pre_tool_call directive or None for observe-only."""
        open_findings = [f for f in findings if not f.waived]
        if not open_findings:
            return None

        receipt = self.ledger.record(
            findings,
            session_id=self.session_id,
            mode=self.mode.value,
        )
        self._last_receipt_digest = receipt.digest
        self._unexplained = list(open_findings)
        summary = "; ".join(f.short() for f in open_findings[:5])
        if len(open_findings) > 5:
            summary += f" (+{len(open_findings) - 5} more)"
        msg = (
            f"ProveIt Tests: possible test weakening detected "
            f"(receipt {receipt.digest[:12]}). {summary}"
        )
        self._pending_warnings.append(msg)

        # rule_key keeps Hermes "[a]lways" approvals scoped to this plugin's
        # weakening rule rather than blanket-approving every write_file call.
        rule_key = "proveit-tests:test-weakening"
        unattended = self.cron.is_unattended()
        if self.mode == Mode.OBSERVE:
            return None
        if self.mode == Mode.BLOCK_UNATTENDED and unattended:
            return {
                "action": "block",
                "message": msg + " [blocked: unattended/cron]",
                "rule_key": rule_key,
            }
        if self.mode == Mode.BLOCK_UNATTENDED and not unattended:
            return {"action": "approve", "message": msg, "rule_key": rule_key}
        if self.mode == Mode.ESCALATE:
            if unattended:
                return {
                    "action": "block",
                    "message": msg + " [blocked: unattended/cron]",
                    "rule_key": rule_key,
                }
            return {"action": "approve", "message": msg, "rule_key": rule_key}
        return None

    # ------------------------------------------------------------------- hooks
    def on_pre_tool_call(
        self, tool_name: str, args: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any] | None:
        args = args or {}
        tool = (tool_name or "").strip()
        findings: list[Finding] = []

        if tool in TERMINAL_TOOLS or tool.endswith("terminal"):
            cmd = _extract_command(args)
            if cmd:
                findings.extend(self.analyze_command(cmd))

        if tool in WRITE_TOOLS | PATCH_TOOLS or tool in {"write_file", "patch"}:
            path = _extract_path(args)
            if path and (is_test_path(path, self.test_globs) or is_ci_path(path, self.ci_globs)):
                new = _extract_content(args)
                old = _read_disk(path)
                if "old_string" in args and "new_string" in args and old:
                    # Hermes core `patch` tool (replace mode): old_string/new_string[, replace_all]
                    count = -1 if args.get("replace_all") else 1
                    new = old.replace(str(args.get("old_string", "")), str(args.get("new_string", "")), count)
                elif new is not None and "old_str" in args and "new_str" in args and old:
                    # str_replace-style editors: synthesize new content
                    new = old.replace(str(args.get("old_str", "")), str(args.get("new_str", "")), 1)
                if new is not None:
                    findings.extend(self.analyze_file_change(path, old, new))
                # else: content not in args — post-edit path will catch it

        if not findings:
            return None
        return self.decide(findings)

    def on_post_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        result: str = "",
        **kwargs: Any,
    ) -> None:
        """Re-scan disk after write tools when pre-edit content was unavailable."""
        args = args or {}
        tool = (tool_name or "").strip()
        if tool not in WRITE_TOOLS | PATCH_TOOLS and tool not in {"write_file", "patch"}:
            # Also re-check if terminal may have rewritten a test file
            if tool in TERMINAL_TOOLS or tool.endswith("terminal"):
                cmd = _extract_command(args)
                # cheap path extraction from redirection targets
                for token in cmd.replace(">", " ").replace("|", " ").split():
                    if is_test_path(token, self.test_globs) or is_ci_path(token, self.ci_globs):
                        new = _read_disk(token)
                        if new:
                            # Without old content we only run absolute checks via empty old
                            findings = self.analyze_file_change(token, "", new)
                            open_f = [f for f in findings if not f.waived]
                            if open_f:
                                self.decide(findings)
            return

        path = _extract_path(args)
        if not path:
            return
        if not (is_test_path(path, self.test_globs) or is_ci_path(path, self.ci_globs)):
            return
        # If we already had content in pre, skip duplicate unless disk differs — keep simple:
        # only run when no pending warning for this path
        if any(path in w for w in self._pending_warnings):
            return
        new = _read_disk(path)
        if not new:
            return
        findings = self.analyze_file_change(path, "", new)
        if findings:
            self.decide(findings)

    def on_transform_tool_result(
        self,
        tool_name: str = "",
        args: dict[str, Any] | None = None,
        result: str = "",
        **kwargs: Any,
    ) -> str | None:
        if not self._pending_warnings:
            return None
        warning = self._pending_warnings.pop(0)
        footer = ""
        if self._last_receipt_digest:
            open_n = len([f for f in self._unexplained if not f.waived])
            footer = f"\n\n[ProveIt] Tests: ? passed / {open_n} weakened · receipt {self._last_receipt_digest[:12]}"
        base = result if isinstance(result, str) else str(result)
        return f"{base}\n\n⚠️ {warning}{footer}"

    def on_pre_verify(
        self,
        changed_paths: list[str] | None = None,
        attempt: int = 0,
        final_response: str = "",
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        if not self.one_shot_nudge:
            return None
        if self._nudged or attempt and attempt > 0:
            return None
        open_f = [f for f in self._unexplained if not f.waived]
        if not open_f:
            return None
        self._nudged = True
        top = open_f[0]
        msg = (
            f"ProveIt Tests: unexplained weakening remains ({top.short()}). "
            f"Restore the assertion or add `# proveit: intended <reason>` on that line."
        )
        return {"action": "continue", "message": msg}

    def slash_proveit(self, args_raw: str = "") -> str:
        return self.ledger.summary_text()

    def footer_line(self, tests_passed: int | None = None) -> str:
        open_n = len([f for f in self._unexplained if not f.waived])
        digest = self._last_receipt_digest[:12] if self._last_receipt_digest else "none"
        passed = str(tests_passed) if tests_passed is not None else "?"
        return f"Tests: {passed} passed / {open_n} weakened · receipt {digest}"
