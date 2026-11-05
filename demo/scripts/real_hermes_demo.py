"""Spend-free ProveIt Tests demo on a REAL Hermes v0.22.7 runtime (no model).

Every tool call below goes through Hermes' own dispatcher
(model_tools.handle_function_call): the real plugin loader, pre_tool_call /
post_tool_call / transform_tool_result hooks, the real approval gate, and the
real patch / terminal tools. The only scripted part is the "agent": tool calls
a model would emit are hard-coded, so no provider or API key is needed.

Run inside the throwaway Hermes env (see DEMO.md):
    source <throwaway>/env.sh && python demo/scripts/real_hermes_demo.py
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

PACE = float(os.environ.get("DEMO_PACE", "1"))
HERE = Path(__file__).resolve().parents[1]
B, D, R, G, Y, C, X = "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"


def pause(s: float) -> None:
    time.sleep(s * PACE)


def beat(title: str) -> None:
    print(f"\n{B}{C}━━ {title} {X}")
    pause(1.2)


def agent(text: str) -> None:
    print(f"{Y}agent ›{X} {text}")
    pause(1.0)


def show_result(raw: str, limit: int = 900, tail: int = 4) -> None:
    try:
        data = json.loads(raw)
    except Exception:
        try:  # Hermes may append notes after the JSON object
            data, _ = json.JSONDecoder().raw_decode(raw)
        except Exception:
            data = None
    if isinstance(data, dict) and data.get("error"):
        print(f"{R}tool result › {data['error'][:limit]}{X}")
    elif isinstance(data, dict) and "output" in data:
        lines = [ln for ln in str(data["output"]).rstrip().splitlines() if ln.strip()]
        print(f"{D}tool result ›{X}\n" + "\n".join(lines[-tail:]))
    elif isinstance(data, dict) and data.get("success"):
        print(f"{G}tool result › patched {data.get('path') or ''}{X}".rstrip())
    else:
        print(f"{D}tool result ›{X} {raw[:limit]}")
    pause(1.6)


class EchoAnswer(io.StringIO):
    """Answers the Hermes approval prompt and echoes the keypress like a human."""

    def readline(self, *a):  # input() on a non-tty stdin calls readline()
        line = super().readline(*a)
        sys.stdout.write(f"{B}{line.strip()}{X}\n")
        sys.stdout.flush()
        pause(0.6)
        return line


def main() -> int:
    os.environ["HERMES_INTERACTIVE"] = "1"  # a human is at the terminal for the approval card
    from hermes_cli.plugins import get_plugin_command_handler, get_plugin_manager
    from hermes_cli.version_info import get_version_info  # noqa: F401  (import check)
    import model_tools
    from cron.execution_identity import enter_cron_execution, exit_cron_execution

    get_plugin_manager().discover_and_load()

    work = Path(tempfile.mkdtemp(prefix="tiny-repo-"))
    shutil.copytree(HERE / "tiny-repo", work, dirs_exist_ok=True)
    os.chdir(work)
    test_file = work / "tests" / "test_add.py"
    call = lambda name, args: model_tools.handle_function_call(name, args, session_id="proveit-demo", task_id="demo")
    # Test runner: any python with pytest (PROVEIT_DEMO_PYTHON), default the package dev venv.
    py = os.environ.get("PROVEIT_DEMO_PYTHON") or str(HERE.parent / ".venv" / "bin" / "python")
    pytest_cmd = f"cd {work} && {py} -m pytest -q -p no:cacheprovider"

    print(f"{B}Your agent says the tests pass. Did it cheat?{X}")
    print(f"{D}ProveIt Tests on real Hermes v0.22.7 · mode=escalate · synthetic repo · scripted agent (no model){X}")
    pause(2.5)

    beat("1. The repo has a real bug")
    print(open(work / "add.py").read().strip())
    pause(1.0)
    agent("running the tests")
    show_result(call("terminal", {"command": pytest_cmd}), limit=260)

    beat("2. The agent 'fixes' the test instead of the code")
    agent("patch tests/test_add.py:  assert total == 9  →  assert total == 8")
    sys.stdin = EchoAnswer("d\n")
    out = call("patch", {"path": str(test_file), "old_string": "assert total == 9", "new_string": "assert total == 8"})
    sys.stdin = sys.__stdin__
    show_result(out, limit=400)
    print(f"{G}test file on disk is unchanged:{X} {test_file.read_text().strip().splitlines()[-1].strip()}")
    pause(2.0)

    beat("3. Denied, so it fixes the actual bug")
    agent("patch add.py:  return a + b - 1  →  return a + b")
    show_result(call("patch", {"path": str(work / "add.py"), "old_string": "return a + b - 1  # bug: should be a + b", "new_string": "return a + b"}), limit=200)
    agent("running the tests")
    show_result(call("terminal", {"command": pytest_cmd}), limit=200)

    beat("4. Same repo, unattended cron run: `pytest || true`")
    token = enter_cron_execution({"id": "nightly-ci", "name": "nightly-ci"}, "demo-run-1", {"source": "builtin"})
    try:
        agent(f"terminal: pytest -q || true")
        show_result(call("terminal", {"command": pytest_cmd + " || true"}), limit=420)
    finally:
        exit_cron_execution(token)

    beat("5. /proveit receipt ledger")
    print(get_plugin_command_handler("proveit")(""))
    pause(3.0)

    beat("Install")
    print("hermes plugins install file:///path/to/proveit-tests-hermes --ref <sha> --enable")
    print(f"{D}(catalog listing pending review){X}")
    pause(2.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
