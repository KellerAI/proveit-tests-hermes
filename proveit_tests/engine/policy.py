"""Central policy for all detector findings."""

from typing import Literal

Tier = Literal["block", "review"]

# Python and heuristic JS/TS expectation rewrites need human judgment.
# Every other detector kind reports a blocking integrity signal.
_REVIEW_KINDS = {
    "expected-value-changed",
    "js-expected-literal-rewrite",
    "ship-merge-approval",
}


def canonical_kind(kind: str) -> str:
    return "expected-value-changed" if kind == "expected-literal-rewrite" else kind


def finding_tier(kind: str, *, new_waiver: bool = False) -> Tier:
    return "review" if new_waiver or canonical_kind(kind) in _REVIEW_KINDS else "block"
