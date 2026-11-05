"""Inline waiver comments: `# proveit: intended <reason>`."""

from __future__ import annotations

import re
from typing import Iterable

from ..findings import Finding

WAIVER_RE = re.compile(
    r"(?:#|//|/\*)\s*proveit:\s*intended\s+(.+?)(?:\*/)?\s*$",
    re.IGNORECASE,
)


def extract_waivers(source: str) -> dict[int, str]:
    """Map 1-based line number → waiver reason."""
    out: dict[int, str] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        m = WAIVER_RE.search(line)
        if m:
            out[i] = m.group(1).strip()
    return out


def apply_waivers(findings: Iterable[Finding], source: str, window: int = 6) -> list[Finding]:
    """Mark findings waived when a waiver comment is nearby.

    Looks at the finding line, the previous line, and up to ``window`` lines
    after (so a decorator finding can be waived by a comment in the function
    body). Also accepts a file-level waiver on line 1 when the finding has no
    line number.
    """
    waivers = extract_waivers(source)
    if not waivers:
        return list(findings)
    result: list[Finding] = []
    for f in findings:
        reason = ""
        if f.line is not None:
            candidates = [f.line, f.line - 1] + list(range(f.line + 1, f.line + 1 + window))
            for ln in candidates:
                if ln in waivers:
                    reason = waivers[ln]
                    break
        elif 1 in waivers:
            reason = waivers[1]
        if reason:
            result.append(
                Finding(
                    kind=f.kind,
                    message=f.message,
                    severity=f.severity,
                    path=f.path,
                    line=f.line,
                    detail=f.detail,
                    waived=True,
                    waiver_reason=reason,
                    evidence=dict(f.evidence),
                )
            )
        else:
            result.append(f)
    return result
