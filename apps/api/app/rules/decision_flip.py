"""DecisionFlip: which open items stand between a case and the next disposition.

Pure, like the rest of ``app.rules``: no I/O, no LLM, no clock. It re-runs the
real disposition rules (``evaluate.redecide``) with unresolved items forced to
a hypothetical state, so a simulated result and a real one always come from
the same code. Every output is marked ``hypothetical``. POLICY.md §9 explains
the method; docs/design/iterations/F-decisionflip.md is the design.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.enums import (
    FlipSearch,
    FlipState,
    IdentityStatus,
    ItemClass,
    ItemKind,
    NextAction,
)
from app.domain.types import (
    AssessmentInputs,
    AssessmentVersion,
    Claim,
    Criterion,
    DecisionFlipAnalysis,
    ItemOutcome,
    MinimalSet,
    NextBestAction,
    SettleDocument,
    UnresolvedItem,
)

FLIP_VERSION = "decision-flip-1"

# Up to this many candidates every subset is tried (2**6 = 64 runs); above it a
# deletion greedy finds one irreducible set.
EXHAUSTIVE_MAX_ITEMS = 6

__all__ = [
    "EXHAUSTIVE_MAX_ITEMS",
    "FLIP_VERSION",
    "DecisionFlipAnalysis",
    "FlipSearch",
    "FlipState",
    "ItemClass",
    "ItemKind",
    "ItemOutcome",
    "MinimalSet",
    "NextAction",
    "NextBestAction",
    "ReplayMismatch",
    "SettleDocument",
    "UnresolvedItem",
    "analyse",
]


class ReplayMismatch(ValueError):
    """Replaying the stored version through the current rules did not give its
    stored disposition (for example a version made under an older policy)."""


def analyse(
    version: AssessmentInputs | AssessmentVersion | Mapping[str, Any],
    *,
    claims: Mapping[str, Claim] | None = None,
    criteria: Sequence[Criterion] | None = None,
    identity_status: IdentityStatus | None = None,
) -> DecisionFlipAnalysis:
    """Analyse one assessment version.

    ``version`` is either the case inputs (assessed here with ``rules.assess``),
    an ``AssessmentVersion``, or a stored version payload: the
    ``AssessmentVersion`` JSON, or the stored ``judgments`` document that holds
    it under ``"assessment"`` (the retention skeleton works: it keeps every
    status and id).

    For a stored version, pass ``claims`` (materiality and settling documents;
    without them every claim counts as material, as in ``decide_disposition``)
    and ``criteria`` (custom weights; without them kind defaults are used).
    ``identity_status`` is read from the version when omitted. With
    ``AssessmentInputs`` all three come from the inputs.

    Raises ``ReplayMismatch`` when the current rules do not reproduce the
    version's stored disposition.
    """
    raise NotImplementedError
