"""Read-only Git comparisons used by the terminal hook and CI."""

from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import os
from pathlib import Path
import subprocess

from ..detectors.commands import redact_command
from ..detectors.waivers import apply_waivers, extract_waivers, waiver_line
from ..findings import Finding, Severity
from .files import FileAnalyzer
from .policy import finding_tier

_ENV_KEYS = {
    "PATH", "HOME", "LANG", "TZ", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT",
    "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE",
}


class InspectionError(Exception):
    """Git or a watched file could not be inspected."""


def _git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if key.upper() in _ENV_KEYS or key.upper().startswith("LC_")}
    # Keep repository selection explicit and disable transports and optional index writes.
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="",
               GIT_TERMINAL_PROMPT="0")
    return env


@dataclass
class Comparison:
    base_sha: str | None
    head_sha: str | None
    findings: list[Finding]


class Repository:
    def __init__(self, directory: str | Path):
        self.root = Path(directory)
        self.root = Path(self.read("rev-parse", "--show-toplevel").rstrip("\r\n"))

    def run(self, *args: str, optional: bool = False) -> bytes | None:
        try:
            result = subprocess.run(
                ["git", "--no-pager", "-c", "core.fsmonitor=false", "-C", str(self.root), *args], env=_git_env(),
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False, timeout=30,
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            raise InspectionError("Git could not run in this directory") from error
        if result.returncode == 0:
            return result.stdout
        if optional:
            return None
        raise InspectionError(f"Git {args[0]} failed")

    def read(self, *args: str) -> str:
        data = self.run(*args)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InspectionError("Git returned content that is not UTF-8") from error

    def resolve(self, ref: str, *, optional: bool = False) -> str | None:
        result = self.run("rev-parse", "--verify", "--end-of-options", ref + "^{commit}", optional=optional)
        return result.decode("ascii").strip() if result else None

    def remote_default(self, remote: str | None = None) -> str:
        remotes = self.read("remote").splitlines()
        if remote is None:
            remote = "origin" if "origin" in remotes else remotes[0] if len(remotes) == 1 else None
        if remote not in remotes:
            raise InspectionError("No local remote default branch is available")
        return self.read("symbolic-ref", f"refs/remotes/{remote}/HEAD").strip()

    def merge_base(self, ref: str, head: str = "HEAD") -> str:
        return self.read("merge-base", self.resolve(ref), self.resolve(head)).strip()

    def compare(
        self, base: str = "HEAD", head: str = "HEAD", *, staged: bool = False,
        tracked: bool = False, analyzer: FileAnalyzer | None = None,
    ) -> Comparison:
        analyzer = analyzer or FileAnalyzer()
        head_sha = self.resolve("HEAD" if staged else head, optional=staged)
        base_sha = head_sha if staged else self.resolve(base)
        args = ["diff", "--name-status", "-z", "-M", "--no-ext-diff", "--no-textconv",
                "--diff-filter=ADMRT"]
        if staged:
            if self.run("ls-files", "--unmerged", "-z"):
                raise InspectionError("The index contains unresolved merges")
            args.append("--cached")
            if base_sha:
                args.append(base_sha)
        else:
            args.extend([base_sha, head_sha])
        args.append("--")
        fields = iter(self.read(*args).split("\0")[:-1])
        changes = []
        for status in fields:
            before = next(fields)
            after = next(fields) if status.startswith("R") else before
            changes.append((status, before, after))
        if staged and tracked:
            changed = {after for _, _, after in changes}
            # Read tracked files directly. A working-tree Git diff can invoke
            # repository-configured clean filters while comparing these files.
            changes.extend(
                ("M", path, path) for path in self.read("ls-files", "-z").split("\0")[:-1]
                if path not in changed
            )
        findings = []
        for status, before, after in changes:
            old_watched = analyzer.is_watched_path(before)
            new_watched = analyzer.is_watched_path(after)
            if not (old_watched or new_watched):
                continue
            if status == "T":
                raise InspectionError("A watched path changed file type")
            old = self.read("show", f"{base_sha}:{before}") if base_sha and status != "A" else ""
            if staged and tracked and status != "D":
                new = self._working_content(after)
                deleted = new is None
            else:
                deleted = status == "D"
                prefix = "" if staged else head_sha
                new = "" if deleted else self.read("show", f"{prefix}:{after}")
            if deleted or (old_watched and not new_watched):
                if old_watched and (status != "A"):
                    findings.append(Finding(
                        kind="deleted-test-file", message="Watched file removed",
                        severity=Severity.CRITICAL, path=before,
                    ))
                continue
            old = old if old_watched else ""
            if old.replace("\r\n", "\n") != new.replace("\r\n", "\n"):
                findings.extend(_diff_findings(analyzer, after, old, new))
        return Comparison(base_sha, head_sha, findings)

    def _working_content(self, path: str) -> str | None:
        file = self.root / path
        try:
            if file.resolve() != (self.root.resolve() / path) or not file.is_file():
                if not file.exists() and not file.is_symlink():
                    return None
                raise InspectionError("A watched path is not a regular file")
            return file.read_text(encoding="utf-8")
        except (OSError, UnicodeError, RuntimeError) as error:
            raise InspectionError("A tracked file could not be read") from error


def _diff_findings(analyzer: FileAnalyzer, path: str, old: str, new: str) -> list[Finding]:
    findings = analyzer.analyze_file_change(path, old, new)
    waivers = extract_waivers(new)
    if waivers:
        old_lines = old.splitlines()
        new_lines = new.splitlines()
        unchanged = {
            j + offset + 1
            for _, j, size in SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_matching_blocks()
            for offset in range(size)
        }
        findings = [
            replace(finding, waived=False, tier=finding_tier(finding.kind, new_waiver=True))
            if finding.waived and waiver_line(finding, waivers) not in unchanged else finding
            for finding in apply_waivers(findings, new)
        ]
    return [
        replace(finding, message=redact_command(finding.message), detail=redact_command(finding.detail),
                waiver_reason=redact_command(finding.waiver_reason))
        for finding in findings
    ]


def inspect_diff(repo: str | Path, base: str, head: str = "HEAD") -> Comparison:
    return Repository(repo).compare(base, head)
