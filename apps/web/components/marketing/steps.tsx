"use client";

import { ArrowRight, Check } from "lucide-react";
import { motion } from "motion/react";
import { Tabs } from "radix-ui";
import { useState } from "react";
import { transition } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import {
  FIT_ROWS,
  ILLUSTRATION_COMPANY,
  JUDGMENTS,
  LEDGER_ROWS,
  STEPS,
  THESIS_EXAMPLE,
  type StepId,
} from "./content";
import { CriteriaStrip } from "./criteria-strip";
import {
  DispositionStamp,
  Estimate,
  IllustrationLabel,
  SourceChip,
  StatusGlyph,
  StatusTag,
  statusInk,
} from "./primitives";

/** Discover → Verify → Evaluate → Act, each tab showing the product doing that job. */
export function Steps() {
  const [active, setActive] = useState<StepId>("discover");

  return (
    <Tabs.Root value={active} onValueChange={(v) => setActive(v as StepId)}>
      <Tabs.List
        aria-label="The four steps"
        className="-mx-4 flex overflow-x-auto border-b border-line-strong px-4 md:mx-0 md:px-0"
      >
        {STEPS.map((step, i) => (
          <div key={step.id} className="flex shrink-0 items-center">
            {i > 0 ? (
              <ArrowRight
                aria-hidden
                className="mx-2 size-4 text-ink-muted md:mx-4"
                strokeWidth={1.5}
              />
            ) : null}
            <Tabs.Trigger
              value={step.id}
              className={cn(
                "relative flex h-11 items-center gap-2 rounded-xs px-1 text-base transition-colors md:text-lg",
                active === step.id
                  ? "text-ink"
                  : "text-ink-muted hover:text-ink-secondary",
              )}
            >
              <span className="font-mono text-xs">{i + 1}</span>
              {step.name}
              {active === step.id ? (
                <motion.span
                  layoutId="step-indicator"
                  transition={transition.base}
                  className="absolute inset-x-0 -bottom-px h-0.5 bg-ink"
                />
              ) : null}
            </Tabs.Trigger>
          </div>
        ))}
      </Tabs.List>

      {STEPS.map((step) => (
        <Tabs.Content key={step.id} value={step.id} className="rounded-lg">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={transition.slow}
            className="grid gap-8 pt-8 lg:grid-cols-12 lg:gap-6 lg:pt-12"
          >
            <div className="lg:col-span-5 lg:pr-8">
              <p className="text-lg text-pretty text-ink">{step.summary}</p>
              <dl className="mt-6 grid gap-4 border-t border-line pt-6 text-sm">
                <div className="grid gap-1">
                  <dt className="text-ink-muted">You give it</dt>
                  <dd className="text-base text-ink-secondary">{step.give}</dd>
                </div>
                <div className="grid gap-1">
                  <dt className="text-ink-muted">You get</dt>
                  <dd className="text-base text-ink-secondary">{step.get}</dd>
                </div>
              </dl>
            </div>
            <figure className="min-w-0 lg:col-span-7">
              <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-md">
                <Preview id={step.id} />
              </div>
              <figcaption className="mt-3">
                <IllustrationLabel>Illustration</IllustrationLabel>
              </figcaption>
            </figure>
          </motion.div>
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}

function Preview({ id }: { id: StepId }) {
  switch (id) {
    case "discover":
      return <DiscoverPreview />;
    case "verify":
      return <VerifyPreview />;
    case "evaluate":
      return <EvaluatePreview />;
    case "act":
      return <ActPreview />;
  }
}

function PaneHead({ title, meta }: { title: string; meta: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-3 lg:px-6">
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="font-mono text-xs text-ink-muted">{meta}</p>
    </div>
  );
}

function DiscoverPreview() {
  const row = FIT_ROWS[0];
  const criteria = [
    { kind: "Must have", text: "Headquartered in India", from: "Company record" },
    { kind: "Must have", text: "Privately held", from: "Evidence" },
    { kind: "Preference", text: "Serves enterprise customers", from: "Evidence" },
    { kind: "Preference", text: "Recent expansion", from: "Signal" },
  ];
  return (
    <>
      <PaneHead title="Thesis" meta="Criteria · editable before searching" />
      <div className="px-4 py-4 lg:px-6">
        <p className="text-sm text-ink-secondary">&ldquo;{THESIS_EXAMPLE}&rdquo;</p>
        <ul className="mt-4 border-t border-line">
          {criteria.map((c) => (
            <li
              key={c.text}
              className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 border-b border-line py-2 text-dense sm:grid-cols-[6rem_minmax(0,1fr)_auto]"
            >
              <span className="flex items-center gap-2 text-xs text-ink-muted">
                <span
                  aria-hidden
                  className={cn(
                    "size-2 border border-ink",
                    c.kind === "Must have" ? "bg-ink" : "bg-surface",
                  )}
                />
                <span className="hidden sm:inline">{c.kind}</span>
              </span>
              <span className="text-ink">{c.text}</span>
              <span className="col-start-2 text-xs text-ink-muted sm:col-start-3">
                {c.from}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className="border-t border-line bg-paper px-4 py-4 lg:px-6">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div>
            <p className="text-sm font-medium text-ink">{row.company}</p>
            <p className="text-dense text-ink-secondary">{row.line}</p>
          </div>
          <CriteriaStrip
            compact
            fit={row.fit}
            assessable={row.assessable}
            cells={row.cells}
            className="w-full sm:w-72"
          />
        </div>
        <p className="mt-3 flex flex-wrap items-baseline gap-x-2 text-dense text-ink-secondary">
          <Estimate value="~180 people" kind="Estimate" />
          <span aria-hidden>·</span>
          Growth funding, 2025
        </p>
        <p className="mt-1 text-dense text-ink-muted">
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
    { name: "Apply status rules", result: "3 supported · 3 open" },
  ];
  const rows = [LEDGER_ROWS[0], LEDGER_ROWS[4]];
  return (
    <>
      <PaneHead title={`Verify · ${ILLUSTRATION_COMPANY}`} meta="Run finished" />
      <ol className="px-4 py-3 lg:px-6">
        {steps.map((s) => (
          <li
            key={s.name}
            className="grid grid-cols-[1rem_minmax(0,1fr)] gap-x-3 py-1.5 text-dense sm:grid-cols-[1rem_11rem_minmax(0,1fr)]"
          >
            <Check
              aria-hidden
              className="mt-0.5 size-4 text-ink-secondary"
              strokeWidth={1.5}
            />
            <span className="text-ink">{s.name}</span>
            <span className="col-start-2 text-ink-muted sm:col-start-3">
              {s.result}
            </span>
          </li>
        ))}
      </ol>
      <ul className="border-t border-line">
        {rows.map((row) => (
          <li
            key={row.n}
            className="grid gap-x-4 gap-y-2 border-b border-line px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(0,5fr)_auto_minmax(0,6fr)] sm:items-start lg:px-6"
          >
            <p className="text-dense text-ink">&ldquo;{row.claim}&rdquo;</p>
            <span className={cn("hidden sm:block", statusInk(row.status))}>
              <StatusGlyph status={row.status} className="mt-0.5" />
            </span>
            <div className="min-w-0">
              <StatusTag status={row.status} className="mb-2 sm:hidden" />
              <p className="text-dense text-ink-secondary">{row.record}</p>
              <p className="mt-2 flex flex-wrap gap-2">
                {row.sources.map((s) => (
                  <SourceChip key={s.label} {...s} />
                ))}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function EvaluatePreview() {
  const values = [
    "Fit 82 · 70% of criteria assessable",
    "3 of 6 claims supported · 3 open",
    "3 dated operating signals",
    "Not assessed · no reliable financial inputs",
  ];
  return (
    <>
      <PaneHead title="Assessment" meta="Version 1 · policy 1.0" />
      <dl className="px-4 lg:px-6">
        {JUDGMENTS.slice(0, 4).map((j, i) => (
          <div
            key={j.name}
            className="grid gap-x-4 gap-y-1 border-b border-line py-3 text-dense sm:grid-cols-[11rem_minmax(0,1fr)]"
          >
            <dt className="text-ink-muted">{j.name}</dt>
            <dd
              className={cn(
                i === 3
                  ? "hatch -my-1 rounded-xs border border-dashed border-not-checked-line px-2 py-1 text-not-checked"
                  : "text-ink",
                i === 0 && "font-mono",
              )}
            >
              {values[i]}
            </dd>
          </div>
        ))}
        <div className="grid gap-x-4 gap-y-2 py-4 text-dense sm:grid-cols-[11rem_minmax(0,1fr)]">
          <dt className="text-ink-muted">{JUDGMENTS[4].name}</dt>
          <dd>
            <DispositionStamp disposition="investigate_further" />
            <p className="mt-2 text-ink-secondary">
              Strong fit; three of six claims open. Rests on claims 2, 5 and 6
            </p>
          </dd>
        </div>
      </dl>
    </>
  );
}

function ActPreview() {
  const docs = LEDGER_ROWS.filter((r) => r.settle);
  return (
    <>
      <PaneHead title="Request to seller" meta="Draft → Approved → Sent once" />
      <div className="px-4 py-4 lg:px-6">
        <p className="text-xs text-ink-muted">Documents requested (3)</p>
        <ul className="mt-2 border-t border-line">
          {docs.map((row) => (
            <li
              key={row.n}
              className="flex flex-wrap items-baseline justify-between gap-x-4 border-b border-line py-2 text-dense"
            >
              <span className="text-ink">{row.settle}</span>
              <span className="font-mono text-xs text-ink-muted">
                settles claim {row.n}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className="border-t border-line bg-paper px-4 py-4 lg:px-6">
        <p className="text-sm font-medium text-ink">Waiting for approval</p>
        <p className="mt-1 text-dense text-ink-secondary">
          Nothing is sent until a named person approves it. It is sent once, and
          cannot be sent again from this case
        </p>
      </div>
    </>
  );
}
