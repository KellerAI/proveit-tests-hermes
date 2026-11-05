"""Durable SHA-256 receipt ledger.

Adapted from ProveIt Audit evidence/verdict digest patterns: every finding
batch becomes a frozen receipt with a content digest. Pure stdlib — no
network, no secrets.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..findings import Finding

log = logging.getLogger("proveit_tests.ledger")


def resolve_ledger_dir(root: str | Path | None, override: Any = None) -> str | None:
    """Confine an optional ``receipt_dir`` override to under ``root``.

    - ``root`` None -> None (caller runs an in-memory ledger; never /tmp).
    - empty override -> ``root``.
    - override must be a relative path that resolves inside ``root``; absolute,
      ``~``-prefixed, or escaping (``..`` / symlink) overrides are rejected with
      a warning and ``root`` is used instead.
    """
    ov = str(override or "").strip()
    if root is None or str(root).strip() == "":
        if ov:
            log.warning(
                "proveit-tests: receipt_dir=%r ignored: no Hermes plugin data dir; "
                "ledger is in-memory only",
                ov,
            )
        return None
    base = Path(root).expanduser()
    if not ov:
        return str(base)
    cand = Path(ov)
    if cand.is_absolute() or ov.startswith("~"):
        log.warning(
            "proveit-tests: receipt_dir=%r rejected (must be relative to the plugin "
            "data dir); using %s",
            ov,
            base,
        )
        return str(base)
    base_r = base.resolve()
    target = (base_r / cand).resolve()
    try:
        target.relative_to(base_r)
    except ValueError:
        log.warning(
            "proveit-tests: receipt_dir=%r escapes the plugin data dir; using %s",
            ov,
            base,
        )
        return str(base)
    return str(target)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Receipt:
    id: str
    ts: float
    session_id: str
    mode: str
    findings: tuple[dict[str, Any], ...]
    open_count: int
    waived_count: int
    digest: str
    meta: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "session_id": self.session_id,
            "mode": self.mode,
            "findings": list(self.findings),
            "open_count": self.open_count,
            "waived_count": self.waived_count,
            "digest": self.digest,
            "meta": dict(self.meta),
        }

    def footer(self) -> str:
        return f"Tests: receipt {self.digest[:12]} · {self.open_count} open / {self.waived_count} waived"


def _finding_dicts(findings: Iterable[Finding]) -> list[dict[str, Any]]:
    return [f.to_dict() for f in findings]


def build_receipt(
    findings: Iterable[Finding],
    *,
    session_id: str = "",
    mode: str = "observe",
    meta: dict[str, Any] | None = None,
) -> Receipt:
    fl = list(findings)
    fdicts = _finding_dicts(fl)
    open_count = sum(1 for f in fl if not f.waived)
    waived_count = sum(1 for f in fl if f.waived)
    payload = {
        "session_id": session_id,
        "mode": mode,
        "findings": fdicts,
        "open_count": open_count,
        "waived_count": waived_count,
        "meta": meta or {},
    }
    digest = sha256(json.dumps(payload, sort_keys=True, default=str))
    rid = digest[:16]
    return Receipt(
        id=rid,
        ts=time.time(),
        session_id=session_id,
        mode=mode,
        findings=tuple(fdicts),
        open_count=open_count,
        waived_count=waived_count,
        digest=digest,
        meta=meta or {},
    )


class Ledger:
    """Append-only JSONL ledger on disk, or in-memory when ``directory`` is None.

    On disk the directory is created 0700 and the file 0600 (owner-only).
    """

    def __init__(self, directory: str | Path | None):
        self._memory: list[Receipt] = []
        self.directory: Path | None = None
        self.path: Path | None = None
        if directory is None:
            return
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / "receipts.jsonl"
        self._load()

    @property
    def persistent(self) -> bool:
        return self.path is not None

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                self._memory.append(
                    Receipt(
                        id=d["id"],
                        ts=d["ts"],
                        session_id=d.get("session_id", ""),
                        mode=d.get("mode", ""),
                        findings=tuple(d.get("findings", [])),
                        open_count=d.get("open_count", 0),
                        waived_count=d.get("waived_count", 0),
                        digest=d["digest"],
                        meta=d.get("meta", {}),
                    )
                )
        except (OSError, json.JSONDecodeError):
            pass

    def append(self, receipt: Receipt) -> Receipt:
        self._memory.append(receipt)
        if self.path is None:
            return receipt
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        return receipt

    def record(
        self,
        findings: Iterable[Finding],
        *,
        session_id: str = "",
        mode: str = "observe",
        meta: dict[str, Any] | None = None,
    ) -> Receipt:
        receipt = build_receipt(findings, session_id=session_id, mode=mode, meta=meta)
        return self.append(receipt)

    def all(self) -> list[Receipt]:
        return list(self._memory)

    def latest(self) -> Receipt | None:
        return self._memory[-1] if self._memory else None

    def open_findings(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in self._memory:
            for f in r.findings:
                if not f.get("waived"):
                    out.append(f)
        return out

    def summary_text(self) -> str:
        note = "" if self.persistent else " [in-memory only: no Hermes plugin data dir; not persisted]"
        if not self._memory:
            return "ProveIt ledger empty — no weakenings recorded this session." + note
        lines = [f"ProveIt ledger ({len(self._memory)} receipt(s)):{note}"]
        for r in self._memory[-20:]:
            kinds = sorted({f.get("kind", "?") for f in r.findings if not f.get("waived")})
            lines.append(
                f"  · {r.digest[:12]}  open={r.open_count} waived={r.waived_count} "
                f"kinds={','.join(kinds) or '-'} mode={r.mode}"
            )
        latest = self._memory[-1]
        lines.append(latest.footer())
        return "\n".join(lines)
