"""DecisionFlip contract (docs/design/iterations/F-decisionflip.md §7.1).

Mirrors `app.domain.types.DecisionFlipAnalysis` (the rules output, stored as the
`decision_flip_analyses.payload`), plus what the API adds on read: item labels and
claim text from the claim and criteria rows (so retention scrubbing shows through),
the analysis id, and the resolution against the previous version.

Every simulated outcome and set carries `hypothetical: true`; the UI never renders one
as a verified result. These models ignore unknown keys when built from a stored
payload, so a newer rules version never breaks a read; a test keeps them in step with
the domain types.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field

from app.api.schemas.common import ApiModel, ClaimCategory, Disposition


class _Out(ApiModel):
    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)


class FlipState(StrEnum):
    has_blockers = "has_blockers"
    no_blockers = "no_blockers"
    disqualified = "disqualified"
    not_evidence_limited = "not_evidence_limited"
    # The current rules do not reproduce this version (assessed under an older policy).
    not_reproducible = "not_reproducible"


class FlipItemKind(StrEnum):
    claim = "claim"
    check_gap = "check_gap"
    criterion = "criterion"
    identity = "identity"
    financial_inputs = "financial_inputs"


class FlipItemClass(StrEnum):
    decision_blocker = "decision_blocker"
    disqualifier_risk = "disqualifier_risk"
    non_blocking = "non_blocking"


class FlipNextAction(StrEnum):
    request_documents = "request_documents"
    resolve_identity = "resolve_identity"
    rerun_checks = "rerun_checks"
    analyst_follow_up = "analyst_follow_up"
    review_disqualifier = "review_disqualifier"
    none = "none"


class FlipSearch(StrEnum):
    exhaustive = "exhaustive"
    greedy = "greedy"


class FlipEffort(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class FlipOutcomeOut(_Out):
    """The disposition the rules give with items forced. Never verified."""

    hypothetical: Literal[True] = True
    disposition: Disposition
    rule: str = Field(description="decide_disposition's rule id.")
    reasons: list[str] = Field(description="Rule reasons; claim ids only, no claim text.")
    changes_disposition: bool


class FlipItemOut(_Out):
    id: str = Field(
        description='"claim:<id>", "check:<category>", "criterion:<id>", "identity" or '
        '"financial_inputs".'
    )
    kind: FlipItemKind
    claim_id: str | None = None
    criterion_id: str | None = None
    check: ClaimCategory | None = None
    label: str = Field(default="", description="Rendered on read from the claim or criterion.")
    claim_text: str | None = Field(
        default=None, description="The claim's wording on read (scrubbed text once removed)."
    )
    current_state: str
    classification: FlipItemClass
    decision_blocker: bool
    disqualifier_risk: bool
    required_in_every_path: bool
    flips_alone: bool
    locks_target: bool
    seller_resolvable: bool
    analyst_retry: bool
    est_effort: FlipEffort = Field(
        default=FlipEffort.medium, description="Effort to obtain its documents; a tie-break only."
    )
    conditional_action: str | None = Field(
        default=None,
        description="Criteria and financial items: what to obtain, with both branches stated.",
    )
    depends_on: list[str] = Field(default_factory=list)
    settle_with: list[str] = Field(default_factory=list, description="Policy document names.")
    if_supported: FlipOutcomeOut | None = None
    if_contradicted: FlipOutcomeOut | None = None


class FlipDocumentOut(_Out):
    document: str
    item_ids: list[str]
    seller_resolvable: bool


class FlipSetOut(_Out):
    hypothetical: Literal[True] = True
    item_ids: list[str]
    documents: list[FlipDocumentOut]
    outcome: FlipOutcomeOut


class FlipNextBestActionOut(_Out):
    action: FlipNextAction
    text: str = Field(description="From fixed templates, never a model.")
    item_ids: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(
        default_factory=list, description="Both-branch sentences for criteria and financials."
    )


class FlipResolutionItemOut(_Out):
    item_id: str
    label: str = ""
    outcome: Literal["resolved", "settled_against", "still_open", "new"]
    was_blocker: bool
    current_state: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class FlipResolutionOut(_Out):
    """This version's open items against the previous version's analysis, by item id."""

    previous_version: int
    previous_blockers: int
    resolved_blockers: int
    items: list[FlipResolutionItemOut]


class DecisionFlipOut(_Out):
    hypothetical: Literal[True] = True
    analysis_id: str = ""
    case_id: str
    assessment_version: int
    policy_version: str
    inputs_hash: str
    flip_version: str
    analysis_key: str
    selection_basis: Literal["fewest_checks"] = Field(
        default="fewest_checks", description="The fewest checks, never the cheapest."
    )
    selection_label: str = Field(
        default="Minimum set of checks required to change the screening outcome",
        description="The UI label for minimum_evidence, verbatim.",
    )
    state: FlipState
    not_reproducible_reason: str | None = None
    current: Disposition
    current_rule: str
    current_reasons: list[str] = Field(default_factory=list)
    target: Disposition | None = None
    ceiling: FlipOutcomeOut | None = Field(
        default=None, description="Every item forced supported (null when not reproducible)."
    )
    items: list[FlipItemOut]
    minimal_sets: list[FlipSetOut] = Field(description="Exhaustive: all; greedy: the one found.")
    minimum_evidence: FlipSetOut | None = None
    worst_if_contradicted: FlipOutcomeOut | None = None
    next_best_action: FlipNextBestActionOut
    search: FlipSearch
    greedy: bool = False
    evaluations: int = Field(description="Number of rule runs.")
    blocker_count: int = 0
    created_at: datetime | None = None
    resolution: FlipResolutionOut | None = None


class DecisionFlipSummaryOut(ApiModel):
    """The Pipeline board's line, read from columns (no JSON)."""

    state: FlipState
    next_disposition: Disposition | None = None
    blockers_to_next: int
    assessment_version: int


class DecisionFlipRecomputeIn(ApiModel):
    version: int | None = Field(default=None, ge=1, description="Default: the latest version.")
