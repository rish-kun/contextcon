"use client";

import { ArrowRight, Check } from "lucide-react";
import {
  CriteriaStrip,
  Fact,
  JudgmentPanel,
  SourceLine,
  StatusMark,
} from "@/components/dealproof";
import { Icon } from "@/components/ui/icon";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  ASSESSMENT,
  CLAIMS,
  FIT_THIN,
  ILLUSTRATION_COMPANY,
  STEPS,
  THESIS_EXAMPLE,
  type StepId,
} from "./content";
import { IllustrationLabel } from "./primitives";

/** Discover → Verify → Evaluate → Act, each tab showing the product doing that job. */
export function Steps() {
  return (
    <Tabs defaultValue="discover" className="gap-0">
      <TabsList
        aria-label="The four steps"
        className="-mx-4 gap-0 px-4 md:mx-0 md:px-0"
      >
        {STEPS.map((step, i) => (
          <div key={step.id} className="flex shrink-0 items-center">
            {i > 0 ? (
              <Icon icon={ArrowRight} className="mx-3 text-ink-muted md:mx-5" />
            ) : null}
            <TabsTrigger value={step.id} className="h-11 text-base md:text-lg">
              <span className="font-mono text-xs font-normal">{i + 1}</span>
              {step.name}
            </TabsTrigger>
          </div>
        ))}
      </TabsList>

      {STEPS.map((step) => (
        <TabsContent
          key={step.id}
          value={step.id}
          className="grid gap-8 pt-8 lg:grid-cols-12 lg:gap-6 lg:pt-12"
        >
          <div className="lg:col-span-5 lg:pr-8">
            <h3 className="font-serif text-2xl text-balance text-ink">
              {step.title}
            </h3>
            <p className="mt-3 text-base text-pretty text-ink-secondary">
              {step.lead}
            </p>
            <dl className="mt-6 grid gap-4 border-t border-line pt-6">
              {step.rows.map((row) => (
                <div key={row.label} className="grid gap-1">
                  <dt className="text-sm font-medium text-ink">{row.label}</dt>
                  <dd className="text-sm text-pretty text-ink-secondary">
                    {row.text}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
          <figure className="min-w-0 lg:col-span-7">
            <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-md">
              <Preview id={step.id} />
            </div>
            <figcaption className="mt-3 flex flex-col items-start gap-3">
              <IllustrationLabel>Illustration</IllustrationLabel>
              {step.note ? (
                <p className="text-dense text-pretty text-ink-muted">
                  {step.note}
                </p>
              ) : null}
            </figcaption>
          </figure>
        </TabsContent>
      ))}
    </Tabs>
  );
}

function Preview({ id }: { id: StepId }) {
  switch (id) {
    case "discover":
      return <DiscoverPreview />;
    case "verify":
      return <VerifyPreview />;
    case "evaluate":
      return (
        <JudgmentPanel
          assessment={ASSESSMENT}
          variant="rail"
          className="rounded-none border-0"
        />
      );
    case "act":
      return <ActPreview />;
  }
}

function PaneHead({ title, meta }: { title: string; meta: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-3 lg:px-5">
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="font-mono text-2xs text-ink-secondary">{meta}</p>
    </div>
  );
}

function DiscoverPreview() {
  const criteria = [
    { must: true, text: "Headquartered in India", from: "Company record" },
    { must: true, text: "Privately held", from: "Evidence" },
    { must: false, text: "Serves enterprise customers", from: "Evidence" },
    { must: false, text: "Recent expansion", from: "Signal" },
  ];
  const headcount = CLAIMS[1].record[0];
  return (
    <>
      <PaneHead title="Thesis" meta="Criteria · edit before searching" />
      <div className="px-4 py-4 lg:px-5">
        <p className="text-sm text-ink-secondary">
          &ldquo;{THESIS_EXAMPLE}&rdquo;
        </p>
        <ul className="mt-4 border-t border-line">
          {criteria.map((c) => (
            <li
              key={c.text}
              className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line py-2 text-dense"
            >
              <span className="flex items-center gap-2 text-xs text-ink-muted sm:w-24">
                <span
                  aria-hidden
                  className={cn(
                    "size-2 border border-ink",
                    c.must ? "bg-ink" : "bg-surface",
                  )}
                />
                <span className="sr-only sm:not-sr-only">
                  {c.must ? "Must have" : "Preference"}
                </span>
              </span>
              <span className="text-ink">{c.text}</span>
              <span className="text-xs text-ink-muted">{c.from}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-col gap-3 border-t border-line bg-paper px-4 py-4 text-dense lg:px-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4">
          <p className="text-sm font-medium text-ink">{ILLUSTRATION_COMPANY}</p>
          <p className="text-ink-secondary">Contract warehousing, Pune</p>
        </div>
        <CriteriaStrip
          fit={FIT_THIN}
          size="compact"
          className="flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:gap-3"
        />
        <Fact evidence={headcount.evidence} estimate={headcount.estimate}>
          {headcount.text}
        </Fact>
        <p className="text-ink-muted">
          Unknown: ownership, customer type, revenue band
        </p>
      </div>
    </>
  );
}

function VerifyPreview() {
  const steps = [
    { name: "Confirm identity", result: "Matched on domain and registration number" },
    { name: "Build public profile", result: "Company record read" },
    { name: "Read seller deck", result: "6 claims extracted" },
    { name: "Gather evidence", result: "6 of 6 claims searched" },
  ];
  const rows = [CLAIMS[0], CLAIMS[3]];
  return (
    <>
      <PaneHead title={`Verify · ${ILLUSTRATION_COMPANY}`} meta="Run finished" />
      <ol className="px-4 py-3 lg:px-5">
        {steps.map((s) => (
          <li
            key={s.name}
            className="grid grid-cols-[1rem_minmax(0,1fr)] gap-x-3 py-1.5 text-dense sm:grid-cols-[1rem_11rem_minmax(0,1fr)]"
          >
            <Icon icon={Check} className="mt-0.5 text-ink-secondary" />
            <span className="text-ink">{s.name}</span>
            <span className="col-start-2 text-ink-muted sm:col-start-3">
              {s.result}
            </span>
          </li>
        ))}
      </ol>
      <ul className="border-t border-line">
        {rows.map((claim) => (
          <li
            key={claim.id}
            className="flex flex-col items-start gap-2 border-b border-line px-4 py-3 text-dense last:border-b-0 lg:px-5"
          >
            <p className="text-ink">&ldquo;{claim.text}&rdquo;</p>
            <StatusMark status={claim.status} />
            <p className="text-ink-secondary">{claim.record[0].text}</p>
            <SourceLine evidence={claim.record[0].evidence} />
          </li>
        ))}
      </ul>
    </>
  );
}

function ActPreview() {
  const open = CLAIMS.filter((c) => c.what_would_settle);
  return (
    <>
      <PaneHead title="Request to seller" meta="Draft → Approved → Sent once" />
      <div className="px-4 py-4 lg:px-5">
        <p className="text-xs text-ink-muted">Documents requested (3)</p>
        <ul className="mt-2 border-t border-line">
          {open.map((claim) => (
            <li
              key={claim.id}
              className="flex flex-wrap items-baseline justify-between gap-x-4 border-b border-line py-2 text-dense"
            >
              <span className="text-ink">{claim.what_would_settle}</span>
              <span className="font-mono text-xs text-ink-muted">
                settles claim {claim.number}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className="border-t border-line bg-paper px-4 py-4 lg:px-5">
        <p className="text-sm font-medium text-ink">Waiting for approval</p>
        <p className="mt-1 text-dense text-ink-secondary">
          Nothing is sent until a named person approves it. It is sent once, and
          cannot be sent again from this case.
        </p>
      </div>
    </>
  );
}
