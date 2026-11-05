"""Durable SHA-256 receipt ledger.

Adapted from ProveIt Audit evidence/verdict digest patterns: every finding
batch becomes a frozen receipt with a content digest. Pure stdlib — no
network, no secrets.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..findings import Finding


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
    """Append-only JSONL ledger on disk."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "receipts.jsonl"
        self._memory: list[Receipt] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
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
        with self.path.open("a", encoding="utf-8") as fh:
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
        if not self._memory:
            return "ProveIt ledger empty — no weakenings recorded this session."
        lines = [f"ProveIt ledger ({len(self._memory)} receipt(s)):"]
        for r in self._memory[-20:]:
            kinds = sorted({f.get("kind", "?") for f in r.findings if not f.get("waived")})
            lines.append(
                f"  · {r.digest[:12]}  open={r.open_count} waived={r.waived_count} "
                f"kinds={','.join(kinds) or '-'} mode={r.mode}"
            )
        latest = self._memory[-1]
        lines.append(latest.footer())
        return "\n".join(lines)
