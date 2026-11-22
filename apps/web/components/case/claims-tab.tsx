"use client";

import { FileText, Plus, RotateCw } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  ApiError,
  type CaseDetail,
  type ClaimOut,
  type ClaimStatus,
  type DocumentOut,
  type EvidenceOut,
  addClaim,
  uploadDocument,
} from "@/lib/api/client";
import { formatAsOf, formatDate, formatDateTime, plural } from "@/lib/format";
import { CLAIM_STATUS_LABEL, CLAIM_STATUS_MEANING, RELIABILITY_NOTE } from "@/lib/labels";
import { CLAIM_STATUSES } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ClaimLedger,
  SourceChip,
  StatusGlyph,
  StatusMark,
} from "@/components/dealproof";
import { STATUS_INK } from "@/components/dealproof/status-mark";
import {
  Button,
  EmptyState,
  Icon,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  TextLink,
  Textarea,
} from "@/components/ui";
import {
  CATEGORY_LABEL,
  SOURCE_CLASS_LABEL,
  claimTally,
  isRunActive,
  statusCounts,
  toClaim,
  toEvidence,
} from "./adapt";
import { useCase, useCaseDetail } from "./case-context";
import { LiveClaimRow } from "./claim-live";
import {
  ConfidentialityStrip,
  DocumentDropzone,
  claimLines,
  formatBytes,
} from "./intake";
import { BlockedByIdentity, TabSection, TabStack } from "./parts";

const RESULT_WORDS: Record<NonNullable<ClaimOut["substantive_result"]>, string> = {
  supports: "it supports the claim",
  conflicts: "it conflicts with the claim",
  partial: "it supports part of the claim",
  silent: "it is silent on the claim",
};

/** One evidence span: the exact words or field, its dates, and the class of its source. */
function EvidenceSpan({ evidence }: { evidence: EvidenceOut }) {
  const mapped = toEvidence(evidence);
  const value = mapped.value;
  return (
    <li className="flex flex-col gap-2 border-l-2 border-line-strong pl-3">
      {evidence.deleted ? (
        <p className="text-ink-secondary">The excerpt was deleted under the retention schedule</p>
      ) : evidence.quote ? (
        <blockquote className="text-ink">“{evidence.quote}”</blockquote>
      ) : evidence.field_path ? (
        <p className="self-start rounded-xs bg-surface-sunken px-2 py-1 font-mono text-2xs break-all text-ink">
          {evidence.field_path}
          {value ? ` = ${value}` : null}
        </p>
      ) : (
        <p className="text-ink-secondary">No excerpt was recorded for this source</p>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <SourceChip evidence={mapped} />
        <span className="font-mono text-2xs text-ink-secondary">
          fact {formatAsOf(evidence.as_of)}
          {evidence.page != null ? ` · p. ${evidence.page}` : null} · retrieved{" "}
          {formatDateTime(evidence.source.retrieved_at) ?? "time not recorded"}
        </span>
      </div>
      <p className="text-xs text-ink-secondary">
        <span className="font-medium text-ink">
          {SOURCE_CLASS_LABEL[evidence.source.source_class]}.
        </span>{" "}
        {RELIABILITY_NOTE[mapped.source.reliability]}
      </p>
    </li>
  );
}

/** What a ledger row opens to: the evidence spans, the adequacy note, and the check history. */
function ClaimDetail({ claim }: { claim: ClaimOut }) {
  const { basePath } = useCase();
  const history = claim.history;

  return (
    <div className="flex flex-col gap-4">
      {claim.status === "not_checked" ? (
        <p className="text-ink-secondary">{claim.reason}</p>
      ) : null}

      {claim.evidence.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h4 className="text-xs font-medium text-ink-secondary">
            Evidence · {plural(claim.evidence.length, "span")}
          </h4>
          <ul className="flex flex-col gap-3">
            {claim.evidence.map((evidence) => (
              <EvidenceSpan key={evidence.evidence_id} evidence={evidence} />
            ))}
          </ul>
        </section>
      ) : null}

      {claim.adequate_source_reached != null ? (
        <p className="text-ink-secondary">
          {claim.adequate_source_reached
            ? "An adequate source for this kind of claim was reached"
            : "No adequate source for this kind of claim was reached"}
          {claim.substantive_result ? `; ${RESULT_WORDS[claim.substantive_result]}` : null}
        </p>
      ) : null}

      {claim.settle_with ? (
        <p className="text-ink">
          <span className="text-ink-muted">What would settle it: </span>
          {claim.settle_with}
          {" · "}
          <TextLink href={`${basePath}/request`}>Request list</TextLink>
        </p>
      ) : null}

      {history.length > 1 ? (
        <section className="flex flex-col gap-2">
          <h4 className="text-xs font-medium text-ink-secondary">Check history</h4>
          <ol className="flex flex-col gap-2">
            {history.map((check) => (
              <li key={check.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="w-6 font-mono text-2xs text-ink-secondary">
                  {check.assessment_version != null ? `v${check.assessment_version}` : "–"}
                </span>
                <StatusMark status={check.status} reason={check.not_checked_reason} />
                <span className="min-w-0 text-ink-secondary">{check.reason}</span>
                <span className="font-mono text-2xs text-ink-muted">
                  {formatDateTime(check.created_at)}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {claim.normalised_text !== claim.original_text ? (
        <p className="text-xs text-ink-secondary">
          <span className="text-ink-muted">Checked as: </span>
          {claim.normalised_text}
        </p>
      ) : null}
    </div>
  );
}

function StatusFilter({
  counts,
  active,
  onToggle,
}: {
  counts: Record<ClaimStatus, number>;
  active: Set<ClaimStatus>;
  onToggle: (status: ClaimStatus) => void;
}) {
  return (
    <ul className="flex flex-wrap items-center gap-2" aria-label="Filter by status">
      {CLAIM_STATUSES.map((status) => {
        const pressed = active.has(status);
        return (
          <li key={status} className={status === "not_checked" ? "ml-2" : undefined}>
            <button
              type="button"
              aria-pressed={pressed}
              disabled={counts[status] === 0}
              onClick={() => onToggle(status)}
              className={cn(
                "inline-flex h-11 items-center gap-1 rounded-md border px-2 text-xs transition-[background-color,border-color,color] disabled:opacity-50 md:h-8",
                pressed
                  ? "border-ink bg-surface font-medium text-ink"
                  : "border-line bg-surface text-ink-secondary hover:border-line-strong hover:bg-surface-raised",
                status === "not_checked" && "border-dashed",
              )}
            >
              <span className={STATUS_INK[status]}>
                <StatusGlyph status={status} />
              </span>
              {CLAIM_STATUS_LABEL[status]}
              <span className="font-mono text-2xs text-ink-muted">{counts[status]}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function describeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError && typeof cause.detail === "string") return cause.detail;
  return fallback;
}

/** Type claims, one per line. Each is attributed to the signed-in person by the API. */
function AddClaims() {
  const { caseId, mutate } = useCase();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lines = claimLines(text);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (lines.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      for (const line of lines) {
        const claim = await addClaim(caseId, line);
        mutate((detail) => appendClaim(detail, claim));
      }
      setText("");
    } catch (cause) {
      setError(describeError(cause, "The claim was not saved. Try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label htmlFor="add-claims" className="flex flex-wrap items-baseline gap-x-2 text-dense font-medium text-ink">
        Type claims
        <span id="add-claims-hint" className="text-xs font-normal text-ink-muted">
          one per line, in the seller&rsquo;s words
        </span>
      </label>
      <Textarea
        id="add-claims"
        aria-describedby="add-claims-hint"
        rows={3}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="We serve 40 enterprise customers"
      />
      {error ? (
        <p role="alert" className="text-xs text-contradicted">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="submit"
          variant="primary"
          className="h-11 md:h-9"
          disabled={busy || lines.length === 0}
        >
          <Icon icon={Plus} />
          {busy ? "Adding" : lines.length > 1 ? `Add ${lines.length} claims` : "Add claim"}
        </Button>
      </div>
    </form>
  );
}

/** A typed claim from the API joins the ledger; ids and numbers never collide with rows already there. */
function appendClaim(detail: CaseDetail, claim: ClaimOut): CaseDetail {
  const taken = detail.claims.some((c) => c.id === claim.id || c.number === claim.number);
  const next = taken
    ? {
        ...claim,
        id: `${claim.id}-${detail.claims.length + 1}`,
        number: Math.max(0, ...detail.claims.map((c) => c.number)) + 1,
      }
    : claim;
  return { ...detail, claims: [...detail.claims, next] };
}

function SellerDocuments({ documents }: { documents: DocumentOut[] }) {
  const { caseId, mutate, followRun } = useCase();
  const [uploading, setUploading] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latestDeletion = documents
    .filter((d) => !d.purged)
    .map((d) => d.delete_after)
    .sort()
    .at(-1);

  async function upload(files: File[]) {
    setError(null);
    setUploading(files.map((file) => file.name));
    try {
      for (const file of files) {
        const document = await uploadDocument(caseId, file, "seller_deck");
        mutate((detail) => ({
          ...detail,
          documents: detail.documents.some((d) => d.id === document.id)
            ? detail.documents
            : [...detail.documents, document],
        }));
        if (document.run && isRunActive(document.run)) followRun(document.run);
        setUploading((names) => names.filter((name) => name !== file.name));
      }
    } catch (cause) {
      setError(
        describeError(
          cause,
          "The upload did not finish. Check that the file is not password-protected or damaged.",
        ),
      );
      setUploading([]);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="flex flex-wrap items-baseline gap-x-2 text-dense font-medium text-ink">
        Upload seller documents
        <span className="text-xs font-normal text-ink-muted">claims are read from them</span>
      </h3>
      <DocumentDropzone onFiles={(files) => void upload(files)} disabled={uploading.length > 0} />
      <ConfidentialityStrip deleteAfter={latestDeletion} />
      {uploading.length > 0 ? (
        <p role="status" className="text-xs text-ink-secondary">
          Uploading {uploading.join(", ")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-xs text-contradicted">
          {error}
        </p>
      ) : null}
      {documents.length > 0 ? (
        <ul className="flex flex-col divide-y divide-line border-t border-line">
          {documents.map((document) => (
            <li key={document.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-dense">
              <Icon icon={FileText} className="shrink-0 text-ink-muted" />
              <span className="min-w-0 truncate text-ink">{document.filename}</span>
              <span className="font-mono text-2xs text-ink-secondary">
                {formatBytes(document.size_bytes)}
                {document.pages != null ? ` · ${plural(document.pages, "page")}` : null}
                {document.claims_extracted > 0
                  ? ` · ${plural(document.claims_extracted, "claim")} extracted`
                  : null}
              </span>
              <span className="ml-auto font-mono text-2xs text-ink-secondary">
                {document.purged
                  ? "deleted"
                  : `deleted on ${formatDate(document.delete_after) ?? "unknown date"}`}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

const ALL_CATEGORIES = "all";

/**
 * The full claim ledger: what the seller said, the status on the spine, what the record
 * shows. Rows open to the exact evidence. Not checked rows stay in every filtered view.
 */
export function ClaimsTab({ initialStatus }: { initialStatus?: string }) {
  const detail = useCaseDetail();
  const { basePath, verify, checkClaim, runActive } = useCase();
  const counts = useMemo(() => statusCounts(detail.claims), [detail.claims]);
  const [statuses, setStatuses] = useState<Set<ClaimStatus>>(() => {
    const first = CLAIM_STATUSES.find((status) => status === initialStatus);
    return new Set(first ? [first] : []);
  });
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const router = useRouter();
  const pathname = usePathname();

  const identityOpen = detail.identity.state !== "confirmed";
  const categories = [...new Set(detail.claims.map((claim) => claim.category))];
  const retryCredits = new Map(
    (detail.request_list?.analyst_retries ?? []).map((retry) => [retry.claim_id, retry.estimated_credits]),
  );

  const visible = detail.claims.filter((claim) => {
    if (category !== ALL_CATEGORIES && claim.category !== category) return false;
    if (statuses.size === 0) return true;
    // Not checked rows are never filtered out by a status filter.
    return statuses.has(claim.status) || claim.status === "not_checked";
  });
  const filtered = statuses.size > 0 || category !== ALL_CATEGORIES;

  function clearFilters() {
    setStatuses(new Set());
    setCategory(ALL_CATEGORIES);
    // A filter that came in on the address leaves it too, so a reload shows the full ledger.
    if (initialStatus) router.replace(pathname, { scroll: false });
  }

  function toggle(status: ClaimStatus) {
    setStatuses((current) => {
      const next = new Set(current);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  }

  const actions = (
    <>
      <Button asChild size="sm" className="h-11 md:h-7">
        <a href="#add-to-ledger">
          <Icon icon={Plus} />
          Add
        </a>
      </Button>
      <Button
        variant="primary"
        size="sm"
        className="h-11 md:h-7"
        onClick={() => void verify()}
        disabled={runActive || identityOpen || detail.claims.length === 0}
      >
        <Icon icon={RotateCw} />
        {runActive ? "Running" : "Re-run verification"}
      </Button>
    </>
  );

  return (
    <TabStack>
      {identityOpen ? <BlockedByIdentity what="Claims can be added now. Checks run once the legal entity is confirmed" /> : null}

      <TabSection
        title="Claim ledger"
        meta={detail.claims.length > 0 ? claimTally(counts) : undefined}
        whyLabel="Statuses"
        why={
          <dl className="flex flex-col gap-2">
            {CLAIM_STATUSES.map((status) => (
              <div key={status} className="flex flex-col">
                <dt className="font-medium text-ink">{CLAIM_STATUS_LABEL[status]}</dt>
                <dd>{CLAIM_STATUS_MEANING[status]}</dd>
              </div>
            ))}
          </dl>
        }
        action={actions}
        flush
      >
        {detail.claims.length === 0 ? (
          <EmptyState title="No claims yet">
            Upload a seller document or type a claim below
          </EmptyState>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-4 py-2">
              <StatusFilter counts={counts} active={statuses} onToggle={toggle} />
              <div className="flex items-center gap-2">
                {categories.length > 1 ? (
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger aria-label="Filter by category" className="h-11 w-40 md:h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL_CATEGORIES}>All categories</SelectItem>
                      {categories.map((value) => (
                        <SelectItem key={value} value={value}>
                          {CATEGORY_LABEL[value]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : null}
                {filtered ? (
                  <Button variant="quiet" size="sm" onClick={clearFilters}>
                    Reset
                  </Button>
                ) : null}
              </div>
            </div>
            {visible.length === 0 ? (
              <EmptyState title="No claims match these filters" />
            ) : (
              <ClaimLedger legend={false} flush label={`Claim ledger, ${plural(visible.length, "claim")}`}>
                {visible.map((claim, index) => (
                  <LiveClaimRow
                    key={claim.id}
                    index={index}
                    claim={{ ...toClaim(claim), retry_credits_estimate: retryCredits.get(claim.id) }}
                    changedHref={`${basePath}/assessment`}
                    onRunCheck={
                      identityOpen || runActive ? undefined : () => void checkClaim(claim.id)
                    }
                    detail={<ClaimDetail claim={claim} />}
                  />
                ))}
              </ClaimLedger>
            )}
          </>
        )}
      </TabSection>

      <TabSection title="Add to the ledger" id="add-to-ledger" bodyClassName="grid gap-x-8 gap-y-6 lg:grid-cols-2">
        <AddClaims />
        <SellerDocuments documents={detail.documents} />
      </TabSection>
    </TabStack>
  );
}
