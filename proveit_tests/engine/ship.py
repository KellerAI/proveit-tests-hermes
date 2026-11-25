"""Recognize supported shell invocations and resolve their local Git range."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex

from .gitdiff import InspectionError, Repository

_SHIP = {"git": {"commit", "push"}, "gh": {"pr create", "pr merge"}}
_ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=")


@dataclass
class ShipCommand:
    name: str
    options: list[str]
    directory: Path | None
    uncertain: bool = False


def ship_commands(command: str, cwd: str | Path | None) -> list[ShipCommand]:
    directory = Path(cwd) if cwd else None
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"
    if os.name == "nt":
        lexer.escape = ""
    commands = []
    prior_command = False
    segment = []
    try:
        for token in lexer:
            if token and all(char in ";&|\n" for char in token):
                directory, prior_command = _parse_segment(segment, directory, prior_command, commands)
                segment = []
            else:
                segment.append(token)
    except ValueError:
        if re.search(r"\b(?:git\b.*\b(?:commit|push)|gh\b.*\bpr\s+(?:create|merge))\b", command):
            commands.append(ShipCommand("ship", [], directory, True))
        return commands
    _parse_segment(segment, directory, prior_command, commands)
    return commands


def _parse_segment(tokens, directory, prior_command, commands):
    if not tokens:
        return directory, prior_command
    tokens = iter(tokens)
    token = next(tokens)
    overrides = False
    if token == "env":
        token = next(tokens, "")
    while _ASSIGNMENT.match(token):
        overrides |= token.startswith("GIT_") or token.startswith(("GH_REPO=", "GH_HOST="))
        token = next(tokens, "")
    rest = list(tokens)
    if token == "cd" and len(rest) == 1 and not prior_command:
        return _relative(directory, rest[0]), False

    executable = token.replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
    if executable not in _SHIP:
        # Earlier commands can mutate the range before the shell ships it.
        return directory, True
    local = directory
    while executable == "git" and rest:
        option = rest[0]
        if option in {"--no-pager", "--paginate"}:
            rest.pop(0)
        elif option == "-C" and len(rest) > 1:
            local = _relative(local, rest[1])
            del rest[:2]
        elif option.startswith("-C") and option != "-C":
            local = _relative(local, option[2:])
            rest.pop(0)
        elif option in {"-c", "--git-dir", "--work-tree", "--namespace", "--config-env"} and len(rest) > 1:
            overrides = True
            del rest[:2]
        elif option.startswith("-"):
            overrides = True
            rest.pop(0)
        else:
            break
    if executable == "gh" and rest[:1] == ["pr"]:
        rest.pop(0)
        name = "pr " + (rest.pop(0) if rest else "")
    else:
        name = rest.pop(0) if rest else ""
    if name in _SHIP[executable]:
        commands.append(ShipCommand(name, rest, local, prior_command or overrides))
    return directory, True


def _relative(cwd: Path | None, value: str) -> Path | None:
    if any(char in value for char in ("$", "`", "%")):
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return cwd / path if cwd is not None else None


def commit_tracks_worktree(options: list[str]) -> bool:
    tracked = False
    args = iter(options)
    for option in args:
        if option in {"-a", "--all"}:
            tracked = True
        elif option in {
            "-m", "-F", "-C", "-c", "--message", "--file", "--reuse-message",
            "--reedit-message", "--author", "--date", "--trailer", "--fixup", "--squash",
        }:
            if next(args, None) is None:
                raise InspectionError("A commit option is missing its argument")
        elif option.startswith(("-m", "-F", "-C", "-c")) and not option.startswith("--"):
            continue
        elif option.startswith("-a") and not option.startswith("--") and option[2:3] in {"m", "F"}:
            tracked = True
            if len(option) == 3 and next(args, None) is None:
                raise InspectionError("A commit option is missing its argument")
        elif option in {"--amend", "--no-edit", "--allow-empty", "--allow-empty-message",
                        "--no-verify", "-n", "--quiet", "-q", "-v", "--verbose",
                        "--signoff", "-s", "--no-gpg-sign", "-S", "--dry-run"}:
            continue
        elif option.startswith(("--message=", "--file=", "--author=", "--date=", "--gpg-sign=")):
            continue
        else:
            raise InspectionError("Commit options or paths require a separate staged commit")
    return tracked


def ship_base(repo: Repository, command: ShipCommand) -> str:
    if command.name == "push":
        positional = []
        for option in command.options:
            if option in {"-u", "--set-upstream", "--force", "-f", "--force-with-lease", "--dry-run",
                          "--porcelain", "--verbose", "-v", "--quiet", "-q", "--no-verify"}:
                continue
            if option.startswith("-"):
                raise InspectionError("Push options could select a different range")
            positional.append(option)
        if len(positional) > 2 or (len(positional) == 2 and positional[1] != "HEAD"):
            raise InspectionError("Push refspec could select a different range")
        remote = positional[0] if positional else None
        upstream = repo.run("rev-parse", "--symbolic-full-name", "@{u}", optional=True)
        if upstream:
            ref = upstream.decode("utf-8").strip()
            if remote is None or ref.startswith(f"refs/remotes/{remote}/"):
                return repo.resolve(ref)
        return repo.merge_base(repo.remote_default(remote))

    if os.environ.get("GH_REPO"):
        raise InspectionError("Unset GH_REPO before inspecting the local pull request range")
    args = iter(command.options)
    base = None
    for option in args:
        if option in {"--base", "-B"}:
            base = next(args, "")
        elif option.startswith("--base="):
            base = option.partition("=")[2]
        elif option.startswith("-B") and not option.startswith("--"):
            base = option[2:]
        elif option in {"--head", "-H", "--repo", "-R"} or option.startswith(
            ("--head=", "--repo=", "-H", "-R")
        ):
            raise InspectionError("PR options could select a different head or repository")
        elif option in {"--title", "-t", "--body", "-b", "--body-file", "-F", "--reviewer",
                        "-r", "--assignee", "-a", "--label", "-l", "--project", "-p", "--milestone", "-m"}:
            next(args, None)
    if base == "":
        raise InspectionError("PR base is missing")
    if base:
        for ref in (f"refs/remotes/origin/{base}", base):
            if repo.resolve(ref, optional=True):
                return repo.merge_base(ref)
        raise InspectionError("PR base is unavailable locally")
    return repo.merge_base(repo.remote_default())
