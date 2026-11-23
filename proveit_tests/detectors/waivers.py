"""Inline waiver comments: `# proveit: intended <reason>`."""

from __future__ import annotations

import re
from dataclasses import replace
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
    result = []
    for finding in findings:
        line = waiver_line(finding, waivers, window)
        result.append(replace(finding, waived=True, waiver_reason=waivers[line]) if line else finding)
    return result


def waiver_line(finding: Finding, waivers: dict[int, str], window: int = 6) -> int | None:
    line = finding.line
    candidates = [1] if line is None else [line, line - 1, *range(line + 1, line + 1 + window)]
    return next((candidate for candidate in candidates if candidate in waivers), None)
