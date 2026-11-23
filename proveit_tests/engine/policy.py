"""Central policy for all detector findings."""

from typing import Literal

Tier = Literal["block", "review"]

# Python and heuristic JS/TS expectation rewrites need human judgment.
# Every other detector kind reports a blocking integrity signal.
_REVIEW_KINDS = {
    "expected-value-changed",
    "expected-literal-rewrite",  # Historical receipt identifier.
    "js-expected-literal-rewrite",
    "ship-merge-approval",
}


def finding_tier(kind: str) -> Tier:
    return "review" if kind in _REVIEW_KINDS else "block"
