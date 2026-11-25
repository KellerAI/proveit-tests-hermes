"""Check a committed Git range without loading the plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

from . import __version__
from .engine.gitdiff import InspectionError, inspect_diff
from .findings import Finding

_SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_REPO_URL = "https://github.com/KellerAI/proveit-tests-hermes"


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


def _sarif_level(finding: dict, *, blocked: bool) -> str:
    return "error" if blocked and finding["tier"] == "block" else "warning"


def _sarif_document(
    findings: list[dict],
    *,
    blocked: bool,
    verdict: str,
    error_message: str | None = None,
) -> dict:
    rules_by_id: dict[str, dict] = {}
    results: list[dict] = []
    for finding in findings:
        rule_id = finding["rule"]
        level = _sarif_level(finding, blocked=blocked)
        if rule_id not in rules_by_id:
            rules_by_id[rule_id] = {
                "id": rule_id,
                "shortDescription": {"text": finding["detail"]},
                "defaultConfiguration": {"level": "error" if finding["tier"] == "block" else "warning"},
                "properties": {"tier": finding["tier"]},
            }
        result: dict = {
            "ruleId": rule_id,
            "level": level,
            "message": {"text": finding["detail"]},
            "partialFingerprints": {"proveitFindingId/v1": finding["id"]},
            "properties": {
                "id": finding["id"],
                "tier": finding["tier"],
                "severity": finding["severity"],
            },
        }
        if finding["file"]:
            physical: dict = {"artifactLocation": {"uri": finding["file"]}}
            if finding["line"]:
                physical["region"] = {"startLine": finding["line"]}
            result["locations"] = [{"physicalLocation": physical}]
        results.append(result)

    run: dict = {
        "tool": {
            "driver": {
                "name": "ProveIt Tests",
                "semanticVersion": __version__,
                "informationUri": _REPO_URL,
                "rules": list(rules_by_id.values()),
            }
        },
        "results": results,
        "properties": {"verdict": verdict},
    }
    if error_message is not None:
        run["invocations"] = [
            {
                "executionSuccessful": False,
                "toolExecutionNotifications": [
                    {
                        "level": "error",
                        "message": {"text": error_message},
                    }
                ],
            }
        ]
    else:
        run["invocations"] = [{"executionSuccessful": True}]

    return {
        "$schema": _SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [run],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--format", choices=("text", "json", "github", "sarif"), default="text")
    parser.add_argument("--mode", choices=("block", "warn"), default="block")
    args = parser.parse_args(argv)

    try:
        comparison = inspect_diff(args.repo, args.base, args.head)
    except (InspectionError, OSError, ValueError) as error:
        cause = str(error) if isinstance(error, InspectionError) else "Invalid repository or range"
        message = f"ProveIt could not inspect the Git range. {cause}."
        if args.format == "json":
            print(json.dumps({"verdict": "BLOCK", "findings": [], "error": message}))
        elif args.format == "sarif":
            print(json.dumps(_sarif_document([], blocked=True, verdict="BLOCK", error_message=message)))
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
    elif args.format == "sarif":
        print(json.dumps(_sarif_document(findings, blocked=blocked, verdict=verdict)))
    elif args.format == "github":
        for finding in findings:
            level = _sarif_level(finding, blocked=blocked)
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
