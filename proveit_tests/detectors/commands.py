"""Terminal and CI command detectors for test-runner escape hatches."""

from __future__ import annotations

import re

from ..findings import Finding, Severity

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
                    detail=cmd.strip()[:300],
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
