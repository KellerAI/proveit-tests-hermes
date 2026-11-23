"""Check a committed Git range without loading the plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

from .engine.gitdiff import InspectionError, inspect_diff
from .findings import Finding


def _finding(finding: Finding) -> dict:
    file = finding.path
    line = finding.line or 0
    rule = finding.kind
    detail = finding.message
    key = f"{file}:{line}:{rule}:{detail}"
    return {
        "id": hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
        "rule": rule,
        "file": file,
        "line": line,
        "severity": "BLOCK" if finding.tier == "block" else "WARN",
        "detail": detail,
        "tier": finding.tier,
    }


def _escape(value: str, *, property_value: bool = False) -> str:
    out = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return out.replace(":", "%3A").replace(",", "%2C") if property_value else out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--format", choices=("text", "json", "github"), default="text")
    parser.add_argument("--mode", choices=("block", "warn"), default="block")
    args = parser.parse_args(argv)

    try:
        comparison = inspect_diff(args.repo, args.base, args.head)
    except (InspectionError, OSError, ValueError) as error:
        cause = str(error) if isinstance(error, InspectionError) else "Invalid repository or range"
        message = f"ProveIt could not inspect the Git range. {cause}."
        if args.format == "json":
            print(json.dumps({"verdict": "BLOCK", "findings": [], "error": message}))
        elif args.format == "github":
            print(f"::error::{_escape(message)}")
        else:
            print(message, file=sys.stderr)
        return 2

    findings = [_finding(f) for f in comparison.findings if not f.waived]
    blocked = args.mode == "block" and any(f["tier"] == "block" for f in findings)
    verdict = "BLOCK" if blocked else "WARN" if findings else "PASS"
    if args.format == "json":
        print(json.dumps({"verdict": verdict, "findings": findings}))
    elif args.format == "github":
        for finding in findings:
            level = "error" if blocked and finding["tier"] == "block" else "warning"
            properties = [f"file={_escape(finding['file'], property_value=True)}"]
            if finding["line"]:
                properties.append(f"line={finding['line']}")
            properties.append(f"title={_escape(finding['rule'], property_value=True)}")
            print(f"::{level} {','.join(properties)}::{_escape(finding['detail'])}")
    else:
        print(f"ProveIt {verdict}")
        for finding in findings:
            print(f"{finding['severity']} {finding['file']}:{finding['line']} "
                  f"{finding['rule']} — {finding['detail']}")
    return int(blocked)


if __name__ == "__main__":
    sys.exit(main())
