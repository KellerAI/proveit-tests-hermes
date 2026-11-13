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

import logging
import os
from pathlib import Path
from typing import Any

from ..detectors.commands import detect_ci_diff, detect_command_weakenings
from ..detectors.js_ts import detect_js_ts_diff
from ..detectors.paths import is_ci_path, is_test_path
from ..detectors.python_ast import detect_python_diff
from ..detectors.pytest_config import (
    detect_command_lines_diff,
    detect_conftest_diff,
    detect_pytest_config_diff,
    is_conftest_path,
    is_pytest_config_path,
)
from ..findings import Finding
from ..modes import Mode, resolve_mode
from ..receipts.ledger import Ledger
from .cron import CronProbe, NullCronProbe

WRITE_TOOLS = {"write_file", "write", "create_file", "str_replace_editor"}
PATCH_TOOLS = {"patch", "apply_patch", "edit_file", "str_replace"}
import re as _re

# pytest's final summary, e.g. "==== 3 passed, 1 failed in 0.12s ====" or "1 failed in 0.03s"
_PYTEST_SUMMARY = _re.compile(
    r"(\d+ (?:passed|failed|error|errors|skipped|xfailed|xpassed)(?:, \d+ (?:passed|failed|error|errors|skipped|xfailed|xpassed|warnings?|deselected))*) in [\d.]+s"
)

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


def _identity(f: Finding) -> tuple[str, str, str, str]:
    """Stable identity for an outstanding finding (line numbers excluded, since
    unrelated edits can shift them)."""
    return (f.kind, f.path or "<command>", f.message, f.detail)


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
            # Fail closed: no sanctioned plugin data dir -> in-memory ledger,
            # never a shared temp dir.
            logging.getLogger("proveit_tests.ledger").warning(
                "proveit-tests: no Hermes plugin data dir; receipt ledger is "
                "in-memory only and will not persist"
            )
        self.ledger = Ledger(ledger_dir)
        self._pending_warnings: list[str] = []
        # Outstanding (unwaived, unresolved) findings, keyed by watched path
        # ("<command>" for terminal findings). Kept across batches and files so
        # the open count is session-wide, not just the latest batch.
        self._outstanding: dict[str, list[Finding]] = {}
        # path -> content before the first edit that left findings outstanding.
        # Later edits to that path are re-diffed against it, so an exact
        # restoration (or a fix) clears the current warning.
        self._baselines: dict[str, str] = {}
        self._nudged = False
        self._last_receipt_digest = ""
        # path -> file content before the in-flight edit (None = unknown)
        self._snapshots: dict[str, str] = {}
        # paths whose edit was fully analyzed pre-edit (content in args)
        self._pre_analyzed: set[str] = set()
        # path -> (outstanding, baseline) as they stood before the in-flight
        # edit's provisional reconcile, so post_tool_call can undo it if the
        # write did not land.
        self._pre_state: dict[str, tuple[list[Finding] | None, str | None]] = {}
        # last test-runner summary seen in a terminal tool result, e.g. "3 passed, 1 failed"
        self.last_test_summary: str = ""

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
            findings.extend(detect_command_lines_diff(old, new, path=path))
        if is_pytest_config_path(path):
            findings.extend(detect_pytest_config_diff(old, new, path=path))
        if is_conftest_path(path):
            findings.extend(detect_conftest_diff(old, new, path=path))
        return findings

    def is_watched_path(self, path: str) -> bool:
        """Test files, CI configs, pytest config files, and conftest.py."""
        return (
            is_test_path(path, self.test_globs)
            or is_ci_path(path, self.ci_globs)
            or is_pytest_config_path(path)
            or is_conftest_path(path)
        )

    def analyze_command(self, command: str) -> list[Finding]:
        return detect_command_weakenings(command)

    # ------------------------------------------------------------ outstanding
    @property
    def _unexplained(self) -> list[Finding]:
        """Flat view of every outstanding finding across files and commands."""
        return [f for fl in self._outstanding.values() for f in fl]

    @_unexplained.setter
    def _unexplained(self, value: list[Finding]) -> None:
        # Session reset (``rt._unexplained = []``) clears all outstanding state.
        self._outstanding = {}
        self._baselines = {}
        for f in value or []:
            self._add_outstanding(f.path or "<command>", [f])

    def _add_outstanding(self, key: str, findings: list[Finding]) -> None:
        cur = self._outstanding.setdefault(key, [])
        seen = {_identity(f) for f in cur}
        for f in findings:
            if not f.waived and _identity(f) not in seen:
                cur.append(f)
                seen.add(_identity(f))
        if not cur:
            self._outstanding.pop(key, None)

    def reconcile_path(self, path: str, old: str, new: str, edit_findings: list[Finding]) -> None:
        """Update outstanding findings for ``path`` after an edit (old -> new).

        Runs on every edit to a watched path, including clean and strengthening
        edits. Historical receipts are never touched; only the current
        unresolved view changes.
        """
        baseline = self._baselines.get(path)
        if baseline is None:
            current = [f for f in edit_findings if not f.waived]
            if current:
                self._baselines[path] = old
        else:
            current = [
                f for f in self.analyze_file_change(path, baseline, new) if not f.waived
            ]
        if current:
            self._outstanding[path] = []
            self._add_outstanding(path, current)
        else:
            self._outstanding.pop(path, None)
            self._baselines.pop(path, None)

    # --------------------------------------------------------------- directives
    def decide(self, findings: list[Finding]) -> dict[str, Any] | None:
        """Return a pre_tool_call directive or None for observe-only."""
        if not findings:
            return None
        # Every non-empty batch is logged, including fully waived ones
        # ("logged, not silent"). Warn/escalate is suppressed separately below.
        receipt = self.ledger.record(
            findings,
            session_id=self.session_id,
            mode=self.mode.value,
        )
        self._last_receipt_digest = receipt.digest
        open_findings = [f for f in findings if not f.waived]
        if not open_findings:
            return None
        if any(not f.path for f in open_findings):
            self._add_outstanding("<command>", [f for f in open_findings if not f.path])
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
                # Snapshot watched files the command names, so post_tool_call can
                # diff against real prior content instead of guessing.
                for token in self._watched_tokens(cmd):
                    self._snapshots.setdefault(token, _read_disk(token))

        if tool in WRITE_TOOLS | PATCH_TOOLS or tool in {"write_file", "patch"}:
            path = _extract_path(args)
            if path and self.is_watched_path(path):
                new = _extract_content(args)
                old = _read_disk(path)
                self._snapshots[path] = old
                if "old_string" in args and "new_string" in args and old:
                    # Hermes core `patch` tool (replace mode): old_string/new_string[, replace_all]
                    count = -1 if args.get("replace_all") else 1
                    new = old.replace(str(args.get("old_string", "")), str(args.get("new_string", "")), count)
                elif new is not None and "old_str" in args and "new_str" in args and old:
                    # str_replace-style editors: synthesize new content
                    new = old.replace(str(args.get("old_str", "")), str(args.get("new_str", "")), 1)
                if new is not None:
                    self._pre_analyzed.add(path)
                    edit_findings = self.analyze_file_change(path, old, new)
                    # Provisional: post_tool_call re-reconciles from disk.
                    prev = self._outstanding.get(path)
                    self._pre_state[path] = (
                        list(prev) if prev is not None else None,
                        self._baselines.get(path),
                    )
                    self.reconcile_path(path, old, new, edit_findings)
                    findings.extend(edit_findings)
                # else: content not in args — post_tool_call diffs disk vs snapshot

        if not findings:
            return None
        return self.decide(findings)

    def _watched_tokens(self, cmd: str) -> list[str]:
        out = []
        for token in cmd.replace(">", " ").replace("|", " ").replace(";", " ").split():
            token = token.strip("'\"")
            if token and self.is_watched_path(token):
                out.append(token)
        return out

    def on_post_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        result: str = "",
        **kwargs: Any,
    ) -> None:
        """Diff disk against the pre-edit snapshot when pre-edit content was unavailable.

        Only edits with a known prior version are analyzed, so findings are
        attributable to this edit. No snapshot (prior content unknown) → no claim.
        """
        args = args or {}
        tool = (tool_name or "").strip()
        if tool in TERMINAL_TOOLS or tool.endswith("terminal"):
            self._note_test_summary(result)
            cmd = _extract_command(args)
            for token in self._watched_tokens(cmd):
                old = self._snapshots.pop(token, None)
                if old is None:
                    continue
                new = _read_disk(token)
                if new != old:
                    findings = self.analyze_file_change(token, old, new)
                    self.reconcile_path(token, old, new, findings)
                    if findings:
                        self.decide(findings)
            return
        if tool not in WRITE_TOOLS | PATCH_TOOLS:
            return

        path = _extract_path(args)
        if not path:
            return
        old = self._snapshots.pop(path, None)
        if path in self._pre_analyzed:
            self._pre_analyzed.discard(path)
            state = self._pre_state.pop(path, None)
            if old is None or state is None:
                return
            # The pre-edit reconcile used the proposed content. Undo it and
            # reconcile against what actually landed on disk, so a failed or
            # blocked restore cannot clear a weakening that is still there.
            prev_open, prev_base = state
            if prev_open is None:
                self._outstanding.pop(path, None)
            else:
                self._outstanding[path] = prev_open
            if prev_base is None:
                self._baselines.pop(path, None)
            else:
                self._baselines[path] = prev_base
            disk = _read_disk(path)
            if disk != old:
                self.reconcile_path(path, old, disk, self.analyze_file_change(path, old, disk))
            return
        if old is None:
            return
        new = _read_disk(path)
        if new == old:
            return
        findings = self.analyze_file_change(path, old, new)
        self.reconcile_path(path, old, new, findings)
        if findings:
            self.decide(findings)

    def _note_test_summary(self, result: Any) -> None:
        text = result if isinstance(result, str) else str(result or "")
        m = _PYTEST_SUMMARY.findall(text)
        if m:
            self.last_test_summary = m[-1].strip()

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
            footer = "\n\n[ProveIt] " + self.footer_line()
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

    def footer_line(self) -> str:
        """`K open weakening(s) · receipt <hash>`, plus the last test-runner summary
        actually seen in a terminal result (never an invented pass count)."""
        open_n = len([f for f in self._unexplained if not f.waived])
        digest = self._last_receipt_digest[:12] if self._last_receipt_digest else "none"
        line = f"{open_n} open weakening(s) · receipt {digest}"
        if self.last_test_summary:
            line += f" · last test run seen: {self.last_test_summary}"
        return line
