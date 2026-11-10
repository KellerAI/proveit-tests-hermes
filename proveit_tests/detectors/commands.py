"""Terminal and CI command detectors for test-runner escape hatches."""

from __future__ import annotations

import re

from ..findings import Finding, Severity
from .addopts import addopts_weakenings, split_opts

# pytest / jest / vitest / npm test escape hatches
_OR_TRUE = re.compile(
    r"(?:pytest|py\.test|python\s+-m\s+pytest|npm\s+test|npx\s+jest|yarn\s+test|pnpm\s+test|"
    r"vitest|npx\s+vitest)\b[^&\n|;]*\|\|\s*true\b",
    re.I,
)
_K_NOT = re.compile(
    r"""(?:pytest|py\.test|python\s+-m\s+pytest)\b[^&\n|;]*\s-k\s+(['"])(?:not\s+|!)""",
    re.I,
)
_K_NOT_UNQUOTED = re.compile(
    r"(?:pytest|py\.test|python\s+-m\s+pytest)\b[^&\n|;]*\s-k\s+not\b",
    re.I,
)
_DESELECT = re.compile(
    r"(?:pytest|py\.test|python\s+-m\s+pytest)\b[^&\n|;]*--deselect\b",
    re.I,
)
_PASS_WITH_NO_TESTS = re.compile(
    r"(?:pytest|py\.test|python\s+-m\s+pytest)\b[^&\n|;]*--pass(?:With|with|-with-)NoTests\b|"
    r"(?:jest|vitest)\b[^&\n|;]*--passWithNoTests\b|"
    r"npm\s+test[^&\n|;]*--passWithNoTests\b",
    re.I,
)
_EXIT_ZERO = re.compile(
    r"(?:pytest|py\.test|python\s+-m\s+pytest|npm\s+test|jest|vitest)\b[^&\n|;]*;\s*exit\s+0\b",
    re.I,
)
_IGNORE_FAIL = re.compile(
    r"(?:pytest|npm\s+test|jest|vitest)[^&\n|;]*\|\|\s*(?:echo|true|:)\b",
    re.I,
)

# PYTEST_ADDOPTS="-k 'not slow'" pytest  /  export PYTEST_ADDOPTS=--deselect=...
_PYTEST_ADDOPTS_ENV = re.compile(
    r"""\bPYTEST_ADDOPTS\s*=\s*("[^"]*"|'[^']*'|\S+)""",
)

_CONTINUE_ON_ERROR = re.compile(
    r"^\s*continue-on-error\s*:\s*true\b",
    re.I | re.M,
)
_ALLOW_FAILURE = re.compile(
    r"^\s*allow_failure\s*:\s*true\b",
    re.I | re.M,
)
_SOFT_FAIL = re.compile(
    r"^\s*soft_fail\s*:\s*true\b|"
    r"^\s*halt_on_error\s*:\s*false\b",
    re.I | re.M,
)


_REDACTED = "[REDACTED]"
_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # URL userinfo: scheme://user:pass@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]+(?::[^\s/@]*)?@"), r"\1" + _REDACTED + "@"),
    # Authorization headers / bearer tokens
    (re.compile(r"(?i)\b(authorization\s*:\s*)(?:bearer|basic|token)?\s*\S+"), r"\1" + _REDACTED),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + _REDACTED),
    # Secret-looking env assignments: FOO_TOKEN=..., PASSWORD=..., AWS_SECRET_ACCESS_KEY=...
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|PWD|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|CREDENTIALS?|AUTH)[A-Z0-9_]*=)"
            r"(?:\"[^\"]*\"|'[^']*'|\S+)"
        ),
        r"\1" + _REDACTED,
    ),
    # Secret-looking CLI flags: --token X, --password=X, --api-key X
    (
        re.compile(
            r"(?i)(--?[a-z0-9-]*(?:token|secret|password|passwd|api-?key|access-?key|auth|credential)s?[a-z0-9-]*)"
            r"(=|\s+)(?:\"[^\"]*\"|'[^']*'|[^\s-]\S*)"
        ),
        r"\1\2" + _REDACTED,
    ),
    # Well-known token shapes
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}"
            r"|sk-[A-Za-z0-9_-]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35})\b"
        ),
        _REDACTED,
    ),
    # Long opaque high-entropy-looking runs (>=32 chars, no path separators)
    (re.compile(r"(?<![A-Za-z0-9_\-/.])[A-Za-z0-9_\-+=]{32,}(?![A-Za-z0-9_\-/.])"), _REDACTED),
)
_DETAIL_MAX = 200


def redact_command(command: str, max_len: int = _DETAIL_MAX) -> str:
    """Best-effort redaction of secret-looking substrings, then truncate.

    Terminal findings keep a short command excerpt as evidence in the local
    receipt ledger. This strips obvious credentials (URL userinfo, bearer/
    Authorization values, *_TOKEN/*PASSWORD= env assignments, --token/--password
    flags, well-known token prefixes, long opaque strings). It is heuristic —
    novel secret formats can survive; README discloses that.
    """
    text = (command or "").strip()
    for pattern, repl in _REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def detect_command_weakenings(command: str) -> list[Finding]:
    """Inspect a shell / terminal command string."""
    findings: list[Finding] = []
    cmd = command or ""

    checks = [
        (_OR_TRUE, "pytest-or-true", "Test runner piped to || true (failures ignored)"),
        (_K_NOT, "pytest-k-not", "pytest -k excludes tests via 'not' expression"),
        (_K_NOT_UNQUOTED, "pytest-k-not", "pytest -k excludes tests via 'not' expression"),
        (_DESELECT, "pytest-deselect", "pytest --deselect used to drop tests"),
        (
            _PASS_WITH_NO_TESTS,
            "pass-with-no-tests",
            "Runner allows zero tests to count as success (--passWithNoTests)",
        ),
        (_EXIT_ZERO, "force-exit-zero", "Test command followed by exit 0"),
        (_IGNORE_FAIL, "ignore-test-failure", "Test failure discarded via || echo/true"),
    ]
    seen: set[str] = set()
    for pattern, kind, message in checks:
        if kind in seen:
            continue
        if pattern.search(cmd):
            seen.add(kind)
            findings.append(
                Finding(
                    kind=kind,
                    message=message,
                    severity=Severity.CRITICAL,
                    path="<command>",
                    detail=redact_command(cmd),
                )
            )
    for m in _PYTEST_ADDOPTS_ENV.finditer(cmd):
        raw = m.group(1)
        if raw[:1] in "\"'" and raw[-1:] == raw[:1]:
            raw = raw[1:-1]
        for kind, message, severity, _detail in addopts_weakenings(split_opts(raw)):
            kind = "pytest-addopts-env-" + kind.removeprefix("pytest-config-")
            if kind in seen:
                continue
            seen.add(kind)
            findings.append(
                Finding(
                    kind=kind,
                    message=message.replace("pytest addopts", "PYTEST_ADDOPTS"),
                    severity=severity,
                    path="<command>",
                    detail=redact_command(cmd),
                )
            )
    return findings


def detect_ci_weakenings(content: str, path: str = "") -> list[Finding]:
    """Inspect CI YAML / Jenkinsfile content for continue-on-error style flags."""
    findings: list[Finding] = []
    text = content or ""
    for pattern, kind, message in (
        (_CONTINUE_ON_ERROR, "ci-continue-on-error", "CI continue-on-error: true added"),
        (_ALLOW_FAILURE, "ci-allow-failure", "CI allow_failure: true added"),
        (_SOFT_FAIL, "ci-soft-fail", "CI soft-fail / halt_on_error disabled"),
    ):
        for m in pattern.finditer(text):
            line = text[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    kind=kind,
                    message=message,
                    severity=Severity.CRITICAL,
                    path=path,
                    line=line,
                )
            )
    return findings


def detect_ci_diff(old: str, new: str, path: str = "") -> list[Finding]:
    """Only flag CI weakenings newly introduced in the proposed content."""
    old_kinds = {(f.kind, f.line) for f in detect_ci_weakenings(old, path)}
    # Compare by kind presence rather than exact line to survive YAML churn
    old_by_kind = {f.kind for f in detect_ci_weakenings(old, path)}
    out: list[Finding] = []
    for f in detect_ci_weakenings(new, path):
        if f.kind not in old_by_kind:
            out.append(f)
        elif (f.kind, f.line) not in old_kinds and f.kind in old_by_kind:
            # same kind already present — skip
            pass
    # If kind already in old, don't re-flag
    return [f for f in detect_ci_weakenings(new, path) if f.kind not in old_by_kind]
