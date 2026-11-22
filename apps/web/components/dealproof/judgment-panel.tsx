import { formatDateTime, plural } from "@/lib/format";
import type {
  Assessment,
  BusinessSignal,
  EvidenceSufficiency,
  FinancialAssessment,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/card";
import { HatchedBlock } from "./blocks";
import { CriteriaStrip } from "./criteria-strip";
import { DispositionStamp, DispositionSummary } from "./disposition-stamp";
import { Fact } from "./source-line";
import { StatusDistribution } from "./status-mark";

/** "9 of 12 required checks settled · 3 not checked". Not checked is never counted as settled. */
export function sufficiencyText(sufficiency: EvidenceSufficiency, short = false): string {
  const base = `${sufficiency.settled} of ${sufficiency.required} ${
    short ? "settled" : "required checks settled"
  }`;
  return sufficiency.counts.not_checked > 0
    ? `${base} · ${sufficiency.counts.not_checked} not checked`
    : base;
}

function Judgment({
  title,
  question,
  children,
  className,
}: {
  title: string;
  question: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex min-w-0 flex-col gap-3", className)}>
      <div className="flex flex-col">
        <h3 className="text-sm font-medium text-ink">{title}</h3>
        <p className="text-xs text-ink-muted">{question}</p>
      </div>
      {children}
    </section>
  );
}

function Sufficiency({ sufficiency }: { sufficiency: EvidenceSufficiency }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-sm font-medium text-ink">{sufficiencyText(sufficiency)}</p>
      <StatusDistribution counts={sufficiency.counts} />
      {sufficiency.gaps.length > 0 ? (
        <p className="text-xs text-ink-secondary">Gaps: {sufficiency.gaps.join(", ")}</p>
      ) : (
        <p className="text-xs text-ink-secondary">No gaps in the required checks</p>
      )}
    </div>
  );
}

function Signals({ signals }: { signals: BusinessSignal[] }) {
  if (signals.length === 0) {
    return <p className="text-dense text-ink-secondary">No operating signals on record</p>;
  }
  return (
    <ul className="flex flex-col gap-3 text-dense">
      {signals.map((signal) => (
        <li key={signal.id}>
          <Fact evidence={signal.evidence} estimate={signal.estimate} layout="stacked">
            {signal.text}
          </Fact>
        </li>
      ))}
    </ul>
  );
}

function Financial({ financial }: { financial: FinancialAssessment }) {
  if (financial.state === "not_assessed") {
    return (
      <HatchedBlock innerClassName="flex flex-col gap-1 text-dense">
        <p className="font-medium">Not assessed · {financial.reason}</p>
        <p>Would need: {financial.would_need.join(", ")}</p>
      </HatchedBlock>
    );
  }
  return (
    <ul className="flex flex-col gap-3 text-dense">
      {financial.figures.map((figure) => (
        <li key={figure.label} className="flex flex-col gap-1">
          <span className="text-xs text-ink-muted">{figure.label}</span>
          <Fact evidence={figure.evidence} layout="stacked">
            <span className="font-mono">{figure.value}</span>
          </Fact>
          {figure.assumption ? (
            <span className="text-xs text-ink-secondary">Assumes: {figure.assumption}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/**
 * Five judgments in one panel, drawn in five different shapes so they cannot be averaged
 * by eye. There is no overall score, no colour for the panel as a whole, and no order
 * that makes one judgment the total of the others.
 *
 * variant="rail" is the compressed form for the sticky rail: five one-line rows.
 */
export function JudgmentPanel({
  assessment,
  variant = "full",
  className,
}: {
  assessment: Assessment;
  variant?: "full" | "rail";
  className?: string;
}) {
  const { fit, sufficiency, business, financial, disposition } = assessment;
  const meta = `version ${assessment.version} · policy ${assessment.policy_version} · ${
    formatDateTime(assessment.created_at) ?? "time not recorded"
  }`;

  if (variant === "rail") {
    return (
      <Panel aria-label="Assessment" className={className}>
        <PanelHeader>
          <h2 className="text-sm font-medium text-ink">Assessment</h2>
          <p className="font-mono text-2xs text-ink-secondary">
            v{assessment.version} · policy {assessment.policy_version}
          </p>
        </PanelHeader>
        <dl className="flex flex-col divide-y divide-line px-5 text-dense">
          <div className="flex flex-col gap-1 py-3">
            <dt className="text-xs text-ink-muted">Opportunity fit</dt>
            <dd>
              <CriteriaStrip fit={fit} size="compact" className="flex-col items-stretch gap-2" />
            </dd>
          </div>
          <div className="flex flex-col gap-1 py-3">
            <dt className="text-xs text-ink-muted">Evidence sufficiency</dt>
            <dd className="font-mono text-xs font-medium text-ink">
              {sufficiencyText(sufficiency, true)}
            </dd>
          </div>
          <div className="flex flex-col gap-1 py-3">
            <dt className="text-xs text-ink-muted">Business assessment</dt>
            <dd className="text-ink">{plural(business.length, "operating signal")}</dd>
          </div>
          <div className="flex flex-col gap-1 py-3">
            <dt className="text-xs text-ink-muted">Financial assessment</dt>
            <dd className="text-ink">
              {financial.state === "not_assessed" ? (
                <span className="hatch rounded-xs border border-dashed border-not-checked-line px-2 py-0.5 text-xs font-medium text-not-checked">
                  Not assessed
                </span>
              ) : (
                plural(financial.figures.length, "figure")
              )}
            </dd>
          </div>
          <div className="flex flex-col items-start gap-2 py-3">
            <dt className="text-xs text-ink-muted">Screening disposition</dt>
            <dd>
              <DispositionStamp disposition={disposition.disposition} />
            </dd>
          </div>
        </dl>
      </Panel>
    );
  }

  return (
    <Panel aria-label="Assessment" className={className}>
      <PanelHeader>
        <h2 className="text-sm font-medium text-ink">Assessment</h2>
        <p className="font-mono text-2xs text-ink-secondary">{meta}</p>
      </PanelHeader>
      <PanelBody className="flex flex-col gap-6">
        <div className="grid gap-x-8 gap-y-6 lg:grid-cols-3">
          <Judgment
            title="Opportunity fit"
            question="How well does this company match our strategy?"
          >
            <CriteriaStrip fit={fit} />
          </Judgment>
          <Judgment
            title="Evidence sufficiency"
            question="Do the available records support what we need to know?"
          >
            <Sufficiency sufficiency={sufficiency} />
          </Judgment>
          <Judgment
            title="Business assessment"
            question="Operating signals. What do observable indicators suggest?"
          >
            <Signals signals={business} />
          </Judgment>
        </div>
        <div className="grid gap-x-8 gap-y-6 border-t border-line pt-6 lg:grid-cols-2">
          <Judgment
            title="Financial assessment"
            question="What do reliable financial inputs show, under stated assumptions?"
          >
            <Financial financial={financial} />
          </Judgment>
          <Judgment title="Screening disposition" question="What should we do next?">
            <DispositionSummary result={disposition} />
          </Judgment>
        </div>
      </PanelBody>
    </Panel>
  );
}
