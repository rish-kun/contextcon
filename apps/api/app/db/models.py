"""ORM models for DealProof's persistent state.

Conventions:
- UUID primary keys and a server-set `created_at` on every table (`IdMixin`).
- Enum-like columns are plain strings with CHECK constraints (values in `app.db.enums`).
- Rows holding confidential, document-derived content carry `delete_after`; the purge
  job (`app.jobs.purge`) deletes or scrubs them once it passes.
- `assessment_versions`, `message_revisions` and `approvals` are immutable: a database
  trigger rejects UPDATE (see the initial migration), and the ORM refuses to flush
  changes to them.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin
from app.db.enums import (
    CallStatus,
    ClaimOrigin,
    ClaimStatus,
    CriterionKind,
    CriterionResult,
    Disposition,
    IdentityStatus,
    RunKind,
    RunState,
    SendStatus,
    StepState,
    check_in,
)

Credits = Numeric(14, 4)
Usd = Numeric(14, 6)


def _fk(target: str, *, ondelete: str = "CASCADE") -> ForeignKey:
    return ForeignKey(target, ondelete=ondelete)


def _ts(*, nullable: bool = True) -> Any:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


def _owner_fks() -> tuple[ForeignKeyConstraint, ...]:
    """(owner_id, workspace_id) → owner(id, workspace_id) for the three owner kinds.

    A NULL owner column skips its check (MATCH SIMPLE), so each row is held only to the
    owner it names, and that owner must be in the row's workspace."""
    return tuple(
        ForeignKeyConstraint(
            [column, "workspace_id"], [f"{table}.id", f"{table}.workspace_id"], ondelete="CASCADE"
        )
        for column, table in (
            ("case_id", "cases"),
            ("discovery_run_id", "discovery_runs"),
            ("investor_run_id", "investor_runs"),
        )
    )


# --- Tenancy -----------------------------------------------------------------


class Workspace(IdMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(200))


class User(IdMixin, Base):
    """A named person. Approvals record who approved, so users are never anonymous."""

    __tablename__ = "users"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (CheckConstraint("length(trim(display_name)) > 0", name="named"),)


class AuthSession(IdMixin, Base):
    """A signed-in browser session (`app.auth`). The cookie holds a random token; only
    its SHA-256 is stored, so a database read does not hand out live sessions."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(_fk("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = _ts(nullable=False)

    __table_args__ = (Index("ix_auth_sessions_expires_at", "expires_at"),)


# --- Discover ----------------------------------------------------------------


class Thesis(IdMixin, Base):
    __tablename__ = "theses"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")

    criteria: Mapped[list["Criterion"]] = relationship(
        back_populates="thesis", order_by="Criterion.position", cascade="all, delete-orphan"
    )


class Criterion(IdMixin, Base):
    __tablename__ = "criteria"

    thesis_id: Mapped[uuid.UUID] = mapped_column(_fk("theses.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    dimension: Mapped[str] = mapped_column(String(64))
    operator: Mapped[str] = mapped_column(String(32))
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    crustdata_filter: Mapped[dict | None] = mapped_column(JSONB)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)

    thesis: Mapped[Thesis] = relationship(back_populates="criteria")

    __table_args__ = (CheckConstraint(check_in("kind", CriterionKind), name="kind"),)


class DiscoveryRun(IdMixin, Base):
    __tablename__ = "discovery_runs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    thesis_id: Mapped[uuid.UUID] = mapped_column(_fk("theses.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    criteria_snapshot: Mapped[list | None] = mapped_column(JSONB)

    # Target of the composite (owner, workspace) foreign keys on runs and the ledger.
    __table_args__ = (UniqueConstraint("id", "workspace_id"),)


class Candidate(IdMixin, Base):
    """One company returned by a discovery run, with its fit and assessable share."""

    __tablename__ = "candidates"

    discovery_run_id: Mapped[uuid.UUID] = mapped_column(_fk("discovery_runs.id"), index=True)
    crustdata_company_id: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(500))
    domain: Mapped[str | None] = mapped_column(String(500))
    rank: Mapped[int | None] = mapped_column(Integer)
    fit: Mapped[int | None] = mapped_column(Integer)
    assessable_pct: Mapped[int] = mapped_column(Integer, default=0)
    card: Mapped[dict] = mapped_column(JSONB, default=dict)
    unknowns: Mapped[list] = mapped_column(JSONB, default=list)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)

    criterion_results: Mapped[list["CandidateCriterionResult"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("fit IS NULL OR (fit BETWEEN 0 AND 100)", name="fit_range"),
        CheckConstraint("assessable_pct BETWEEN 0 AND 100", name="assessable_range"),
        UniqueConstraint("discovery_run_id", "crustdata_company_id"),
    )


class CandidateCriterionResult(IdMixin, Base):
    __tablename__ = "candidate_criterion_results"

    candidate_id: Mapped[uuid.UUID] = mapped_column(_fk("candidates.id"), index=True)
    criterion_id: Mapped[uuid.UUID] = mapped_column(_fk("criteria.id"), index=True)
    result: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)

    candidate: Mapped[Candidate] = relationship(back_populates="criterion_results")

    __table_args__ = (
        CheckConstraint(check_in("result", CriterionResult), name="result"),
        UniqueConstraint("candidate_id", "criterion_id"),
    )


class InvestorRun(IdMixin, Base):
    __tablename__ = "investor_runs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="SET NULL"))
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")

    __table_args__ = (UniqueConstraint("id", "workspace_id"),)


class InvestorEntry(IdMixin, Base):
    __tablename__ = "investor_entries"

    investor_run_id: Mapped[uuid.UUID] = mapped_column(_fk("investor_runs.id"), index=True)
    investor_key: Mapped[str] = mapped_column(String(500))
    investor_name: Mapped[str] = mapped_column(String(500))
    investor_uuid: Mapped[str | None] = mapped_column(String(128))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int | None] = mapped_column(Integer)
    comparable_rounds: Mapped[list] = mapped_column(JSONB, default=list)
    last_sector_investment: Mapped[date | None] = mapped_column(Date)
    why: Mapped[str] = mapped_column(Text, default="")
    possible_duplicate_of: Mapped[str | None] = mapped_column(String(500))
    unknowns: Mapped[list] = mapped_column(JSONB, default=list)

    __table_args__ = (UniqueConstraint("investor_run_id", "investor_key"),)


# --- Cases -------------------------------------------------------------------


class Case(IdMixin, Base):
    """A company under verification. Everything below a case is authorised through it."""

    __tablename__ = "cases"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="SET NULL"))
    thesis_id: Mapped[uuid.UUID | None] = mapped_column(_fk("theses.id", ondelete="SET NULL"))
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("candidates.id", ondelete="SET NULL")
    )
    company_name: Mapped[str] = mapped_column(String(500))
    website: Mapped[str | None] = mapped_column(String(500))
    crustdata_company_id: Mapped[str | None] = mapped_column(String(64))
    identity_status: Mapped[str] = mapped_column(String(16), default=IdentityStatus.UNRESOLVED)
    # Identifiers that corroborate the match: domain, profile URL, HQ, founded year, CIN…
    identity_identifiers: Mapped[dict] = mapped_column(JSONB, default=dict)
    identity_candidates: Mapped[list] = mapped_column(JSONB, default=list)
    company_type: Mapped[str | None] = mapped_column(String(32))
    credit_budget: Mapped[Decimal | None] = mapped_column(Credits)
    status: Mapped[str] = mapped_column(String(32), default="open")

    __table_args__ = (
        CheckConstraint(check_in("identity_status", IdentityStatus), name="identity_status"),
        UniqueConstraint("id", "workspace_id"),
    )


class Document(IdMixin, Base):
    """An uploaded file. The object lives in GCS; this row outlives it as a record."""

    __tablename__ = "documents"

    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="seller_deck")
    filename: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str] = mapped_column(String(200))
    gcs_path: Mapped[str] = mapped_column(String(1000))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    pages: Mapped[int | None] = mapped_column(Integer)
    # What ingestion found: the parsed file type ("pdf", "pptx", ...) and whether the
    # text could be read ("ok" | "no_text_layer" | "unreadable") with the reason.
    file_kind: Mapped[str | None] = mapped_column(String(16))
    text_status: Mapped[str | None] = mapped_column(String(32))
    text_status_reason: Mapped[str | None] = mapped_column(Text)
    # PII kind -> spans replaced. Counts only, never the redacted values.
    redaction_counts: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="SET NULL"))
    delete_after: Mapped[datetime] = _ts(nullable=False)
    deleted_at: Mapped[datetime | None] = _ts()
    deletion_record_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("deletion_records.id", ondelete="SET NULL")
    )

    __table_args__ = (Index("ix_documents_purge", "delete_after", "deleted_at"),)


class ExtractedText(IdMixin, Base):
    """Confidential text pulled out of a document (after PII stripping)."""

    __tablename__ = "extracted_texts"

    document_id: Mapped[uuid.UUID] = mapped_column(_fk("documents.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id"), index=True)
    page: Mapped[int | None] = mapped_column(Integer)
    # Order within the document, and the DOCX paragraph index (None for PDF/PPTX).
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    paragraph: Mapped[int | None] = mapped_column(Integer)
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    text: Mapped[str] = mapped_column(Text)
    redaction_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    delete_after: Mapped[datetime] = _ts(nullable=False)


class DeletionRecord(IdMixin, Base):
    """Dated record of what the purge job deleted. Never holds the deleted content."""

    __tablename__ = "deletion_records"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("workspaces.id", ondelete="SET NULL")
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(_fk("cases.id", ondelete="SET NULL"))
    object_type: Mapped[str] = mapped_column(String(64))
    object_ids: Mapped[list] = mapped_column(JSONB, default=list)
    object_count: Mapped[int] = mapped_column(Integer, default=0)
    gcs_path: Mapped[str | None] = mapped_column(String(1000))
    reason: Mapped[str] = mapped_column(String(200), default="retention period ended")
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)


class Source(IdMixin, Base):
    __tablename__ = "sources"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(_fk("cases.id"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(_fk("runs.id", ondelete="SET NULL"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(_fk("documents.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(64))
    endpoint_or_url: Mapped[str] = mapped_column(Text)
    request: Mapped[dict] = mapped_column(JSONB, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_class: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(500))
    delete_after: Mapped[datetime | None] = _ts()


class Evidence(IdMixin, Base):
    """An exact span or field from a source, attached to one entity, with its as-of date."""

    __tablename__ = "evidence"

    source_id: Mapped[uuid.UUID] = mapped_column(_fk("sources.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(_fk("cases.id"), index=True)
    entity_ref: Mapped[str] = mapped_column(String(500))
    identity_confidence: Mapped[float | None] = mapped_column(Float)
    field_path: Mapped[str | None] = mapped_column(String(500))
    span: Mapped[str | None] = mapped_column(Text)
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    as_of: Mapped[date | None] = mapped_column(Date)
    # Stable key for where this came from (e.g. "crustdata:enrich:123:funding.milestones[0]")
    # so re-running a step upserts instead of duplicating.
    origin_key: Mapped[str] = mapped_column(String(1000))
    delete_after: Mapped[datetime | None] = _ts()
    scrubbed_at: Mapped[datetime | None] = _ts()

    __table_args__ = (UniqueConstraint("source_id", "origin_key"),)


class Claim(IdMixin, Base):
    __tablename__ = "claims"

    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id"), index=True)
    original_text: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16))
    document_id: Mapped[uuid.UUID | None] = mapped_column(_fk("documents.id", ondelete="SET NULL"))
    page: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64))
    components: Mapped[dict] = mapped_column(JSONB, default=dict)
    material: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="SET NULL"))
    delete_after: Mapped[datetime | None] = _ts()
    scrubbed_at: Mapped[datetime | None] = _ts()

    __table_args__ = (CheckConstraint(check_in("origin", ClaimOrigin), name="origin"),)


class ClaimCheck(IdMixin, Base):
    """One outcome for a claim. Append-only history: the latest row is current."""

    __tablename__ = "claim_checks"

    claim_id: Mapped[uuid.UUID] = mapped_column(_fk("claims.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(_fk("runs.id", ondelete="SET NULL"))
    step_id: Mapped[uuid.UUID | None] = mapped_column(_fk("steps.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text, default="")
    what_would_settle: Mapped[str | None] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(64))

    evidence_links: Mapped[list["ClaimCheckEvidence"]] = relationship(cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(check_in("status", ClaimStatus), name="status"),
        CheckConstraint(
            "status <> 'not_checked' OR length(trim(reason)) > 0", name="not_checked_has_reason"
        ),
        Index("ix_claim_checks_claim_created", "claim_id", "created_at"),
    )


class ClaimCheckEvidence(Base):
    __tablename__ = "claim_check_evidence"

    claim_check_id: Mapped[uuid.UUID] = mapped_column(_fk("claim_checks.id"), primary_key=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(_fk("evidence.id"), primary_key=True)
    relation: Mapped[str] = mapped_column(String(32), default="match")


class Event(IdMixin, Base):
    __tablename__ = "events"

    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str | None] = mapped_column(String(32))
    evidence_id: Mapped[uuid.UUID] = mapped_column(_fk("evidence.id"), index=True)


class Comparable(IdMixin, Base):
    __tablename__ = "comparables"

    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id"), index=True)
    crustdata_company_id: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(500))
    basis: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(_fk("evidence.id", ondelete="SET NULL"))


class AssessmentVersion(IdMixin, Base):
    """Immutable evaluation snapshot. Re-evaluation inserts a new version."""

    __tablename__ = "assessment_versions"

    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("assessment_versions.id", ondelete="RESTRICT")
    )
    policy_version: Mapped[str] = mapped_column(String(64))
    inputs_hash: Mapped[str] = mapped_column(String(128))
    judgments: Mapped[dict] = mapped_column(JSONB)
    disposition: Mapped[str] = mapped_column(String(32))
    reasons: Mapped[list] = mapped_column(JSONB, default=list)
    diff_from_previous: Mapped[dict | None] = mapped_column(JSONB)
    trigger: Mapped[str] = mapped_column(String(64), default="evaluate")
    # Documents that caused this version, and every document / evidence row it rests on.
    trigger_document_ids: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    document_ids: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    evidence_ids: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # RESTRICT, not SET NULL: nulling a column is an UPDATE, which the trigger rejects.
    run_id: Mapped[uuid.UUID | None] = mapped_column(_fk("runs.id", ondelete="RESTRICT"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="RESTRICT"))

    __table_args__ = (
        CheckConstraint(check_in("disposition", Disposition), name="disposition"),
        UniqueConstraint("case_id", "version"),
    )


# --- Act ---------------------------------------------------------------------


class RequestList(IdMixin, Base):
    __tablename__ = "request_lists"

    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id"), index=True)
    assessment_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("assessment_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), default="draft")

    items: Mapped[list["RequestItem"]] = relationship(
        order_by="RequestItem.position", cascade="all, delete-orphan"
    )


class RequestItem(IdMixin, Base):
    __tablename__ = "request_items"

    request_list_id: Mapped[uuid.UUID] = mapped_column(_fk("request_lists.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(64))
    document_requested: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")

    claim_links: Mapped[list["RequestItemClaim"]] = relationship(cascade="all, delete-orphan")


class RequestItemClaim(Base):
    """Which claims (open questions) a requested document would settle."""

    __tablename__ = "request_item_claims"

    request_item_id: Mapped[uuid.UUID] = mapped_column(_fk("request_items.id"), primary_key=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(_fk("claims.id"), primary_key=True)


class MessageRevision(IdMixin, Base):
    """Immutable text of a seller message. Editing creates a new revision."""

    __tablename__ = "message_revisions"

    request_list_id: Mapped[uuid.UUID] = mapped_column(
        _fk("request_lists.id", ondelete="RESTRICT"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id", ondelete="RESTRICT"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    # Empty until a person types the address in (a drafted first revision has none).
    recipient: Mapped[str] = mapped_column(String(320))
    created_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="RESTRICT"))

    __table_args__ = (UniqueConstraint("request_list_id", "revision"),)


class Approval(IdMixin, Base):
    """A named user approving one exact message revision."""

    __tablename__ = "approvals"

    message_revision_id: Mapped[uuid.UUID] = mapped_column(
        _fk("message_revisions.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(_fk("users.id", ondelete="RESTRICT"))
    user_display_name: Mapped[str] = mapped_column(String(200))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("message_revision_id", "user_id"),)


class SendAttempt(IdMixin, Base):
    """At most one per send key. The unique key is what stops a second send."""

    __tablename__ = "send_attempts"

    request_list_id: Mapped[uuid.UUID] = mapped_column(
        _fk("request_lists.id", ondelete="RESTRICT"), index=True
    )
    message_revision_id: Mapped[uuid.UUID] = mapped_column(
        _fk("message_revisions.id", ondelete="RESTRICT"), unique=True
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(_fk("approvals.id", ondelete="RESTRICT"))
    send_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(32), default=SendStatus.PENDING)
    provider: Mapped[str] = mapped_column(String(64), default="resend")
    provider_message_id: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)
    # Bumped by every status change; a transition names the generation it read.
    generation: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    attempts: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    test_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # The exact provider request (from, to, subject, text, tags); retries resend it.
    payload: Mapped[dict | None] = mapped_column(JSONB)
    dispatched_at: Mapped[datetime | None] = _ts()
    last_attempt_at: Mapped[datetime | None] = _ts()
    completed_at: Mapped[datetime | None] = _ts()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(check_in("status", SendStatus), name="status"),
        # While a send has left or may have left, no other send for the same request
        # list can start (two concurrent inserts: the loser gets an IntegrityError).
        Index(
            "uq_send_attempts_active_per_list",
            "request_list_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'sent', 'unknown')"),
        ),
    )


# --- Jobs --------------------------------------------------------------------


class Run(IdMixin, Base):
    __tablename__ = "runs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default=RunState.PENDING)
    # Owner columns reference (id, workspace_id) together, so an owner from another
    # workspace cannot be attached (see `_owner_fks`).
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    investor_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    budget_credits: Mapped[Decimal | None] = mapped_column(Credits)
    created_by: Mapped[uuid.UUID | None] = mapped_column(_fk("users.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = _ts()
    # Set when the run picked up again after an interruption (expired lease or resume).
    resumed_at: Mapped[datetime | None] = _ts()

    steps: Mapped[list["Step"]] = relationship(
        back_populates="run", order_by="Step.position", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(check_in("state", RunState), name="state"),
        CheckConstraint(check_in("kind", RunKind), name="kind"),
        CheckConstraint(
            "num_nonnulls(case_id, discovery_run_id, investor_run_id) <= 1", name="one_owner"
        ),
        *_owner_fks(),
    )


class Step(IdMixin, Base):
    __tablename__ = "steps"

    run_id: Mapped[uuid.UUID] = mapped_column(_fk("runs.id"), index=True)
    key: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(300))
    handler: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default=StepState.PENDING)
    depends_on: Mapped[list] = mapped_column(JSONB, default=list)
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    skip_reason: Mapped[str | None] = mapped_column(Text)
    # Live sub-line while running, and a one-line result when done (shown in the UI).
    detail: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    uses_budget: Mapped[bool] = mapped_column(Boolean, default=True)
    tolerate_failed_deps: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime | None] = _ts()
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    # A fresh token per claim. Renewal, completion and every paid dispatch require it
    # and an unexpired lease, so a worker that lost the step can neither finish it
    # nor start new paid calls.
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = _ts()
    # Set when the output carries confidential text: the output itself lives in this
    # expiring payload and `output` keeps only a marker (see `app.jobs.retention`).
    confidential_output_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("confidential_payloads.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = _ts()
    finished_at: Mapped[datetime | None] = _ts()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[Run] = relationship(back_populates="steps")

    __table_args__ = (
        CheckConstraint(check_in("state", StepState), name="state"),
        UniqueConstraint("run_id", "key"),
        Index("ix_steps_claimable", "state", "next_attempt_at"),
        Index("ix_steps_lease", "state", "lease_until"),
    )


# --- Cost ledger and API cache -----------------------------------------------


class CallAttempt(IdMixin, Base):
    """One external call, upserted from the clients' `CallRecord` reports.

    The `started` report is committed before the request goes out, so a crash leaves a
    trace. Only hashes of the request are kept (`params_hash`, `cache_key`), never the
    request itself, so nothing confidential lands here.
    """

    __tablename__ = "call_attempts"

    call_id: Mapped[str] = mapped_column(String(64), unique=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    investor_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(_fk("runs.id", ondelete="SET NULL"))
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("steps.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(String(500))
    params_hash: Mapped[str | None] = mapped_column(String(128))
    cache_key: Mapped[str | None] = mapped_column(String(128), index=True)
    model: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default=CallStatus.STARTED)
    http_status: Mapped[int | None] = mapped_column(Integer)
    http_attempts: Mapped[int] = mapped_column(Integer, default=0)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    # An allowlisted error code (`app.clients.base.safe_error_code`), never provider text.
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = _ts()
    finished_at: Mapped[datetime | None] = _ts()
    # Stable key of the logical call within its step (step, call index, params), shared
    # by its dispatches, so a resumed step finds what a crashed worker left `started`.
    operation_key: Mapped[str | None] = mapped_column(String(64), index=True)
    dispatch_index: Mapped[int] = mapped_column(Integer, default=0)
    # Credits reserved against the owner's budget for this dispatch. Held while the row
    # is `started`, and as a floor on spend when the final cost is unknown.
    reserved_credits: Mapped[Decimal] = mapped_column(Credits, default=Decimal(0))

    __table_args__ = (
        CheckConstraint(check_in("status", CallStatus), name="status"),
        *_owner_fks(),
        # The run status / SSE poll groups a run's calls by step on every tick.
        Index("ix_call_attempts_run_step", "run_id", "step_id"),
    )


class CostEntry(IdMixin, Base):
    """What one call cost, charged to exactly one owner: a case, a discovery run or an
    investor run. A reuse of data another run paid for is recorded with zero cost and a
    `shared_from_run_id` link, so totals never count the same spend twice."""

    __tablename__ = "cost_entries"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    investor_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("runs.id", ondelete="SET NULL"), index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(_fk("steps.id", ondelete="SET NULL"))
    call_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("call_attempts.id", ondelete="SET NULL"), unique=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(String(500))
    credits: Mapped[Decimal] = mapped_column(Credits, default=Decimal(0))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    usd: Mapped[Decimal] = mapped_column(Usd, default=Decimal(0))
    unknown: Mapped[bool] = mapped_column(Boolean, default=False)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    shared_from_run_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("runs.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(case_id, discovery_run_id, investor_run_id) = 1", name="one_owner"
        ),
        CheckConstraint(
            "shared_from_run_id IS NULL OR (credits = 0 AND usd = 0)", name="shared_is_free"
        ),
        *_owner_fks(),
    )


class CreditBudget(IdMixin, Base):
    """Lock target for credit reservations: one row per budget owner (a case, a
    discovery run or an investor run).

    Before each metered dispatch the recorder locks this row (`SELECT … FOR UPDATE`),
    checks the run's budget against settled spend plus open reservations
    (`app.db.ledger.budget_used`), and inserts the `started` attempt holding its
    reservation, all in one transaction. Concurrent steps of one owner therefore
    reserve one after another and cannot overspend. Handlers never write this row,
    so the lock cannot wait on a handler's own open transaction."""

    __tablename__ = "credit_budgets"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    investor_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(case_id, discovery_run_id, investor_run_id) = 1", name="one_owner"
        ),
        *_owner_fks(),
    )


class ConfidentialPayload(IdMixin, Base):
    """Confidential JSON (document text copied into a step output or an assessment
    snapshot), kept apart from the record that refers to it so it can expire.

    The purge job deletes rows once `delete_after` passes and writes a deletion record;
    the referring step or assessment version stays and resolves to "deleted under the
    retention schedule". Assessment versions are immutable, so the link points from
    here to the version (`assessment_version_id`), never the other way."""

    __tablename__ = "confidential_payloads"

    workspace_id: Mapped[uuid.UUID] = mapped_column(_fk("workspaces.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(_fk("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[Any] = mapped_column(JSONB, nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(_fk("runs.id", ondelete="SET NULL"))
    assessment_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("assessment_versions.id"), index=True
    )
    delete_after: Mapped[datetime] = _ts(nullable=False)

    __table_args__ = (Index("ix_confidential_payloads_delete_after", "delete_after"),)


class ApiCache(IdMixin, Base):
    """Request-hash → response. Confidential rows are scoped to one case and expire."""

    __tablename__ = "api_cache"

    cache_key: Mapped[str] = mapped_column(String(300), unique=True)
    provider: Mapped[str | None] = mapped_column(String(64))
    endpoint: Mapped[str | None] = mapped_column(String(500))
    response: Mapped[Any] = mapped_column(JSONB, nullable=True)
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        _fk("workspaces.id", ondelete="SET NULL")
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(_fk("cases.id"), index=True)
    origin_run_id: Mapped[uuid.UUID | None] = mapped_column(_fk("runs.id", ondelete="SET NULL"))
    origin_case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    origin_discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    origin_investor_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    delete_after: Mapped[datetime | None] = _ts()

    __table_args__ = (
        CheckConstraint(
            "NOT confidential OR (case_id IS NOT NULL AND delete_after IS NOT NULL)",
            name="confidential_scoped",
        ),
        Index("ix_api_cache_purge", "confidential", "delete_after"),
    )


# --- Immutability (ORM side; the database trigger is the real guarantee) -----

IMMUTABLE_MODELS: tuple[type[Base], ...] = (AssessmentVersion, MessageRevision, Approval)
IMMUTABLE_TABLES: tuple[str, ...] = tuple(m.__tablename__ for m in IMMUTABLE_MODELS)


class ImmutableRowError(RuntimeError):
    pass


def _reject_update(mapper: Any, connection: Any, target: Any) -> None:
    raise ImmutableRowError(f"{type(target).__name__} rows are immutable; insert a new one")


for _model in IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_update)
