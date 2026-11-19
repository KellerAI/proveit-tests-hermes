#!/usr/bin/env python3
"""Fail if internal working notes land in this public repo.

Checks tracked files (git ls-files) for:
- internal note files: STATUS.md, REMAINING-APPROVALS.md, anything under drafts/ or internal/,
  and *.internal.md
- internal markers in text: "keep private", "do not post from bots", "do not submit from bots",
  "/workspace/" paths, "Mac Mini", "shared box"

Run: python3 scripts/check_public_hygiene.py   (exit 1 on any hit)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()
SKIP = {SELF, "tests/test_public_hygiene.py"}

BLOCKED_NAMES = {"STATUS.md", "REMAINING-APPROVALS.md"}
BLOCKED_DIRS = ("drafts/", "internal/")
BLOCKED_SUFFIXES = (".internal.md",)

MARKERS = [
    re.compile(r"keep\s+private", re.I),
    re.compile(r"do\s+not\s+(post|submit)\s+from\s+bots", re.I),
    re.compile(r"(?<![\w.])/workspace/"),
    re.compile(r"mac\s+mini", re.I),
    re.compile(r"shared\s+box", re.I),
]

TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".toml", ".txt", ".sh", ".cfg", ".ini", ".json", ""}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def check(files: list[str]) -> list[str]:
    problems: list[str] = []
    for rel in files:
        if rel in SKIP:
            continue
        name = rel.rsplit("/", 1)[-1]
        if name in BLOCKED_NAMES or rel.startswith(BLOCKED_DIRS) or rel.endswith(BLOCKED_SUFFIXES):
            problems.append(f"{rel}: internal notes file; keep it out of the public repo")
            continue
        path = ROOT / rel
        if path.suffix not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in MARKERS:
                if pat.search(line):
                    problems.append(f"{rel}:{lineno}: internal marker {pat.pattern!r}")
    return problems


def main() -> int:
    problems = check(tracked_files())
    for p in problems:
        print(p)
    if problems:
        print(f"\n{len(problems)} public-hygiene problem(s). Move internal notes out of the repo.")
        return 1
    print("public hygiene: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
