/**
 * The static sections of the home page. Interactive pieces (hero ledger, step tabs,
 * criteria strip, problem spine) live in their own client files.
 *
 * Section shapes alternate on purpose: window, tabs, two-sided list, legend with two
 * unequal cells, paired rows, panel, split, numbered list, table. No repeated card grid.
 */
import { Menu } from "lucide-react";
import Link from "next/link";
import { DISPOSITION_MEANING } from "@/lib/labels";
import { cn } from "@/lib/utils";
import {
  AUDIENCE,
  AUDIENCE_HEAD,
  CTA,
  DIFFERS,
  DIFFERS_HEAD,
  DISPOSITIONS_HEAD,
  DISPOSITION_ORDER,
  FIRST_CUSTOMER,
  FIT_HEAD,
  FIT_ROWS,
  FOOTER,
  HERO,
  ILLUSTRATION_LABEL,
  INVESTOR_HEAD,
  INVESTOR_ROW,
  JUDGMENTS,
  JUDGMENT_HEAD,
  LEDGER_ROWS,
  LIMITS,
  LIMITS_HEAD,
  NAV_LINKS,
  PRINCIPLES,
  PRINCIPLES_HEAD,
  PROBLEM_HEAD,
  STATUS_HEAD,
  STATUS_MEANINGS,
  STATUS_NOTES,
  STEPS_HEAD,
} from "./content";
import { CriteriaLegend, CriteriaStrip } from "./criteria-strip";
import { HeroLedger } from "./hero-ledger";
import {
  Container,
  DispositionStamp,
  Estimate,
  IllustrationLabel,
  SectionHead,
  SourceChip,
  StatusGlyph,
  StatusTag,
  buttonPrimary,
  buttonSecondary,
  statusInk,
} from "./primitives";
import { ProblemLedger } from "./problem-ledger";
import { Reveal } from "./reveal";
import { Steps } from "./steps";

const SECTION = "py-16 md:py-24 lg:py-32";
const APP_HREF = "/app";

/* ───────────────────────── Header ───────────────────────── */

export function SiteHeader() {
  const link =
    "rounded-xs text-sm text-ink-secondary transition-colors hover:text-ink";
  return (
    <header className="sticky top-0 z-(--z-sticky) border-b border-line bg-paper-warm">
      <Container className="flex h-14 items-center justify-between gap-6">
        <Link href="/" className="rounded-xs text-base font-medium text-ink">
          DealProof
        </Link>
        <nav aria-label="Sections" className="hidden items-center gap-8 md:flex">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} className={link}>
              {l.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link
            href={APP_HREF}
            className="press inline-flex h-9 items-center rounded-md bg-ink px-4 text-sm font-medium text-ink-inverse shadow-xs transition-[background-color,transform] hover:bg-ink-secondary"
          >
            Open app
          </Link>
          <details className="group relative md:hidden">
            <summary className="flex size-11 cursor-pointer list-none items-center justify-center rounded-md text-ink transition-colors hover:bg-surface-raised [&::-webkit-details-marker]:hidden">
              <Menu aria-hidden className="size-4" strokeWidth={1.5} />
              <span className="sr-only">Menu</span>
            </summary>
            <nav
              aria-label="Sections"
              className="absolute top-full right-0 mt-2 grid w-56 animate-overlay-in rounded-lg border border-line bg-surface p-2 shadow-md"
            >
              {NAV_LINKS.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  className="flex h-11 items-center rounded-md px-3 text-sm text-ink transition-colors hover:bg-surface-raised"
                >
                  {l.label}
                </a>
              ))}
            </nav>
          </details>
        </div>
      </Container>
    </header>
  );
}

/* ───────────────────────── Hero ───────────────────────── */

export function Hero() {
  return (
    <section className="pt-16 md:pt-20 lg:pt-24">
      <Container>
        {/* COPY: from docs/content/home.md */}
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-sm text-ink-muted">{HERO.eyebrow}</p>
          <h1 className="mt-4 font-serif text-4xl tracking-display text-balance text-ink lg:text-5xl">
            {HERO.title}
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-base text-pretty text-ink-secondary md:text-lg">
            {HERO.lead}
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link href={APP_HREF} className={buttonPrimary}>
              {HERO.primary}
            </Link>
            <a href="#how" className={buttonSecondary}>
              {HERO.secondary}
            </a>
          </div>
        </div>
        <div id="ledger" className="mt-12 scroll-mt-20 lg:mt-16">
          <HeroLedger />
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── Four steps ───────────────────────── */

export function StepsSection() {
  return (
    <section id="how" className={cn(SECTION, "scroll-mt-14")}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <Reveal>
          <SectionHead {...STEPS_HEAD} />
        </Reveal>
        <Reveal className="mt-8 lg:mt-12">
          <Steps />
        </Reveal>
      </Container>
    </section>
  );
}

/* ───────────────────────── The problem ───────────────────────── */

export function ProblemSection() {
  return (
    <section className={cn(SECTION, "border-y border-line bg-surface")}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <Reveal>
          <SectionHead {...PROBLEM_HEAD} />
        </Reveal>
        <div className="mt-10 lg:mt-16">
          <ProblemLedger />
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── Six answers ───────────────────────── */

export function StatusSection() {
  const open = LEDGER_ROWS[1];
  return (
    <section className={SECTION}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <Reveal>
          <SectionHead {...STATUS_HEAD} />
        </Reveal>

        <dl className="mt-10 grid border-t border-line-strong sm:grid-cols-2 lg:mt-16 lg:grid-cols-3">
          {STATUS_MEANINGS.map((s, i) => (
            <Reveal
              key={s.status}
              index={i}
              className="border-b border-line py-5 sm:pr-8"
            >
              <dt>
                <StatusTag status={s.status} />
              </dt>
              <dd className="mt-3 text-sm text-pretty text-ink-secondary">
                {s.meaning}
              </dd>
            </Reveal>
          ))}
        </dl>

        <div className="mt-10 grid gap-6 lg:mt-16 lg:grid-cols-12">
          <Reveal className="rounded-xl border border-line bg-surface p-5 lg:col-span-7 lg:p-8">
            <h3 className="font-serif text-2xl text-ink">
              {STATUS_NOTES.cannotVerify.title}
            </h3>
            <p className="mt-3 max-w-lg text-base text-ink-secondary">
              {STATUS_NOTES.cannotVerify.body}
            </p>
            <div className="mt-6 rounded-md border border-line p-4">
              <p className="text-dense text-ink">&ldquo;{open.claim}&rdquo;</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <StatusTag status={open.status} />
                {open.estimate ? <Estimate {...open.estimate} /> : null}
                {open.sources.map((s) => (
                  <SourceChip key={s.label} {...s} />
                ))}
              </div>
              <p className="mt-3 text-dense text-ink-secondary">
                What would settle it:{" "}
                <span className="font-medium text-ink">{open.settle}</span>
              </p>
            </div>
          </Reveal>

          <Reveal
            index={1}
            className="rounded-xl border border-line bg-surface p-5 lg:col-span-5 lg:p-8"
          >
            <h3 className="font-serif text-2xl text-ink">
              {STATUS_NOTES.notChecked.title}
            </h3>
            <p className="mt-3 text-base text-ink-secondary">
              {STATUS_NOTES.notChecked.body}
            </p>
            <div className="hatch mt-6 rounded-md border border-dashed border-not-checked-line p-4">
              <p className="text-dense text-ink">
                &ldquo;{STATUS_NOTES.notChecked.claim}&rdquo;
              </p>
              <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-not-checked">
                <StatusGlyph status="not_checked" />
                {STATUS_NOTES.notChecked.reason}
              </p>
              <p className="mt-1 text-dense text-ink-secondary">
                {STATUS_NOTES.notChecked.detail}
              </p>
            </div>
          </Reveal>
        </div>
        <p className="mt-4">
          <IllustrationLabel>{ILLUSTRATION_LABEL}</IllustrationLabel>
        </p>
      </Container>
    </section>
  );
}

/* ───────────────────────── Fit is not evidence ───────────────────────── */

export function FitSection() {
  return (
    <section className={cn(SECTION, "border-y border-line bg-surface")}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-5 lg:pr-8">
            <SectionHead {...FIT_HEAD} />
          </Reveal>
          <div className="lg:col-span-7">
            <div className="grid gap-8">
              {FIT_ROWS.map((row, i) => (
                <Reveal
                  key={row.company}
                  index={i}
                  className="border-t border-line-strong pt-5"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                    <p className="text-base font-medium text-ink">
                      {row.company}
                    </p>
                    <p className="text-sm text-ink-muted">{row.line}</p>
                  </div>
                  <CriteriaStrip
                    className="mt-4"
                    fit={row.fit}
                    assessable={row.assessable}
                    cells={row.cells}
                  />
                  <p className="mt-3 text-dense text-ink-secondary">
                    {row.detail}
                  </p>
                </Reveal>
              ))}
            </div>
            <div className="mt-8 flex flex-col gap-4 border-t border-line pt-5">
              <CriteriaLegend />
              <p className="text-dense text-ink-muted">{FIT_HEAD.footnote}</p>
              <p>
                <IllustrationLabel>{ILLUSTRATION_LABEL}</IllustrationLabel>
              </p>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── Five judgments, four dispositions ───────────────────────── */

function JudgmentCell({
  index,
  className,
  children,
}: {
  index: number;
  className?: string;
  children: React.ReactNode;
}) {
  const j = JUDGMENTS[index];
  return (
    <div className={cn("p-5 lg:p-6", className)}>
      <h3 className="text-sm font-medium text-ink">{j.name}</h3>
      <p className="mt-1 text-dense text-ink-muted">{j.question}</p>
      <div className="mt-4">{children}</div>
    </div>
  );
}

export function JudgmentSection() {
  const fit = FIT_ROWS[0];
  const distribution = LEDGER_ROWS.map((r) => r.status).sort(
    (a, b) =>
      STATUS_MEANINGS.findIndex((s) => s.status === a) -
      STATUS_MEANINGS.findIndex((s) => s.status === b),
  );
  return (
    <section className={SECTION}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <Reveal>
          <SectionHead {...JUDGMENT_HEAD} />
        </Reveal>

        <Reveal className="mt-10 lg:mt-16">
          <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-md">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-5 py-3 lg:px-6">
              <p className="text-sm text-ink">
                <span className="font-medium">Assessment</span>
                <span className="font-mono text-xs text-ink-muted">
                  {" "}
                  · version 1 · policy 1.0
                </span>
              </p>
              <IllustrationLabel>{ILLUSTRATION_LABEL}</IllustrationLabel>
            </div>

            <div className="grid divide-y divide-line lg:grid-cols-3 lg:divide-x lg:divide-y-0">
              <JudgmentCell index={0}>
                <CriteriaStrip
                  compact
                  fit={fit.fit}
                  assessable={fit.assessable}
                  cells={fit.cells}
                />
                <p className="mt-3 text-dense text-ink-secondary">
                  Unknown: ownership, customer type, revenue band
                </p>
              </JudgmentCell>

              <JudgmentCell index={1}>
                <p className="font-mono text-dense font-medium text-ink">
                  3 of 6 claims supported · 3 open
                </p>
                <p
                  className="mt-2 flex gap-1"
                  role="img"
                  aria-label="3 Supported, 1 Partially corroborated, 2 Cannot verify"
                >
                  {distribution.map((status, i) => (
                    <span key={i} className={statusInk(status)}>
                      <StatusGlyph status={status} />
                    </span>
                  ))}
                </p>
                <p className="mt-3 text-dense text-ink-secondary">
                  Gaps: payroll summary, lender statements, proof the facility
                  is operating
                </p>
              </JudgmentCell>

              <JudgmentCell index={2}>
                <p className="text-xs text-ink-muted">Operating signals</p>
                <ul className="mt-2 grid gap-2 text-dense text-ink">
                  <li>
                    <Estimate value="~180 people" kind="Estimate" />
                  </li>
                  <li>Growth funding recorded, Jun 2025</li>
                  <li className="flex flex-wrap items-baseline gap-x-1.5">
                    Planned facility announced, Sep 2026
                    <span className="font-mono text-2xs text-ink-muted">
                      Signal
                    </span>
                  </li>
                </ul>
              </JudgmentCell>
            </div>

            <div className="grid divide-y divide-line border-t border-line lg:grid-cols-2 lg:divide-x lg:divide-y-0">
              <JudgmentCell index={3}>
                <div className="hatch rounded-md border border-dashed border-not-checked-line p-4">
                  <p className="text-sm font-medium text-not-checked">
                    Not assessed
                  </p>
                  <p className="mt-1 text-dense text-ink-secondary">
                    No reliable financial inputs
                  </p>
                  <p className="mt-1 text-dense text-ink-secondary">
                    Would need: audited statements
                  </p>
                </div>
              </JudgmentCell>

              <JudgmentCell index={4}>
                <DispositionStamp disposition="investigate_further" />
                <p className="mt-3 text-dense text-ink-secondary">
                  Strong fit; three of six claims open
                </p>
                <p className="mt-1 font-mono text-xs text-ink-muted">
                  Rests on claims 2, 5 and 6
                </p>
              </JudgmentCell>
            </div>
          </div>
        </Reveal>

        <div className="mt-16 grid gap-8 lg:mt-24 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-4">
            <h3 className="font-serif text-3xl text-ink">
              {DISPOSITIONS_HEAD.title}
            </h3>
            <p className="mt-3 max-w-xs text-base text-ink-secondary">
              {DISPOSITIONS_HEAD.note}
            </p>
          </Reveal>
          <dl className="border-t border-line-strong lg:col-span-8">
            {DISPOSITION_ORDER.map((d, i) => (
              <Reveal
                key={d}
                index={i}
                className="grid gap-x-6 gap-y-3 border-b border-line py-4 sm:grid-cols-[13rem_minmax(0,1fr)] sm:items-center"
              >
                <dt>
                  <DispositionStamp disposition={d} />
                </dt>
                <dd className="text-base text-ink-secondary">
                  {DISPOSITION_MEANING[d]}
                </dd>
              </Reveal>
            ))}
          </dl>
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── Investor discovery ───────────────────────── */

export function InvestorSection() {
  return (
    <section className={cn(SECTION, "border-y border-line bg-surface")}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-5 lg:pr-8">
            <SectionHead
              eyebrow={INVESTOR_HEAD.eyebrow}
              title={INVESTOR_HEAD.title}
              lead={INVESTOR_HEAD.lead}
            />
            <ul className="mt-6 grid gap-2 border-t border-line pt-6 text-sm text-ink-secondary">
              {INVESTOR_HEAD.points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </Reveal>

          <Reveal index={1} className="min-w-0 lg:col-span-7">
            <figure>
              <div className="overflow-hidden rounded-xl border border-line bg-paper">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-3 lg:px-6">
                  <p className="text-base font-medium text-ink">
                    {INVESTOR_ROW.name}
                  </p>
                  <p className="font-mono text-xs text-ink-secondary">
                    {INVESTOR_ROW.lead}
                  </p>
                </div>
                <div className="px-4 py-4 lg:px-6">
                  <p className="text-xs text-ink-muted">
                    Comparable companies backed
                  </p>
                  <ul className="mt-2">
                    {INVESTOR_ROW.backed.map((b) => (
                      <li
                        key={b.company}
                        className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 border-t border-line py-2 text-dense sm:grid-cols-[minmax(0,1fr)_5rem_auto]"
                      >
                        <span className="text-ink">{b.company}</span>
                        <span className="text-ink-secondary">{b.round}</span>
                        <span className="col-span-2 sm:col-span-1">
                          <SourceChip
                            kind="funding"
                            label="Funding record"
                            asOf={b.date}
                          />
                        </span>
                      </li>
                    ))}
                    <li className="border-t border-line py-2 text-dense text-ink-muted">
                      {INVESTOR_ROW.more}
                    </li>
                  </ul>
                  <dl className="mt-2 grid gap-1 border-t border-line pt-4 text-dense">
                    <div className="flex flex-wrap gap-x-2">
                      <dt className="text-ink-muted">Why they fit</dt>
                      <dd className="text-ink">{INVESTOR_ROW.why}</dd>
                    </div>
                    <div className="flex flex-wrap gap-x-2">
                      <dt className="text-ink-muted">Unknown</dt>
                      <dd className="text-ink-secondary">
                        {INVESTOR_ROW.unknown}
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
              <figcaption className="mt-3 flex flex-col gap-3">
                <span>
                  <IllustrationLabel>{INVESTOR_ROW.label}</IllustrationLabel>
                </span>
                <span className="text-dense text-ink-muted">
                  {INVESTOR_HEAD.caveat}
                </span>
              </figcaption>
            </figure>
          </Reveal>
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── Principles ───────────────────────── */

export function PrinciplesSection() {
  return (
    <section id="principles" className={cn(SECTION, "scroll-mt-14")}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-5 lg:pr-8">
            <div className="lg:sticky lg:top-28">
              <SectionHead {...PRINCIPLES_HEAD} />
            </div>
          </Reveal>
          <ol className="border-t border-line-strong lg:col-span-7">
            {PRINCIPLES.map((p, i) => (
              <li key={p.title} className="border-b border-line">
                <details className="group" open={i === 0}>
                  <summary className="focus-inset flex min-h-14 cursor-pointer list-none items-baseline gap-4 py-4 transition-colors hover:text-accent [&::-webkit-details-marker]:hidden">
                    <span className="w-6 shrink-0 font-mono text-xs text-ink-muted">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="flex-1 text-lg text-ink group-hover:text-accent">
                      {p.title}
                    </span>
                    <span
                      aria-hidden
                      className="font-mono text-base text-ink-muted group-open:hidden"
                    >
                      +
                    </span>
                    <span
                      aria-hidden
                      className="hidden font-mono text-base text-ink-muted group-open:inline"
                    >
                      −
                    </span>
                  </summary>
                  <p className="animate-fade-in pr-8 pb-5 pl-10 text-base text-pretty text-ink-secondary">
                    {p.body}
                  </p>
                </details>
              </li>
            ))}
          </ol>
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── What it is not ───────────────────────── */

export function LimitsSection() {
  return (
    <section
      id="limits"
      className={cn(SECTION, "scroll-mt-14 border-y border-line bg-surface")}
    >
      <Container>
        {/* COPY: from docs/content/home.md */}
        <Reveal>
          <SectionHead {...LIMITS_HEAD} />
        </Reveal>
        <ul className="mt-10 grid gap-x-16 border-t border-line-strong md:grid-cols-2 lg:mt-16">
          {LIMITS.map((l, i) => (
            <Reveal
              as="li"
              key={l.title}
              index={i}
              className="border-b border-line py-5"
            >
              <p className="text-base font-medium text-ink">{l.title}</p>
              <p className="mt-1 text-base text-pretty text-ink-secondary">
                {l.body}
              </p>
            </Reveal>
          ))}
        </ul>
      </Container>
    </section>
  );
}

/* ───────────────────────── How it differs ───────────────────────── */

export function DiffersSection() {
  return (
    <section className={SECTION}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <Reveal>
          <SectionHead
            eyebrow={DIFFERS_HEAD.eyebrow}
            title={DIFFERS_HEAD.title}
            lead={DIFFERS_HEAD.lead}
          />
        </Reveal>
        <Reveal className="mt-10 lg:mt-16">
          <div
            aria-hidden
            className="hidden grid-cols-[3fr_4fr_5fr] gap-x-8 border-b border-line-strong pb-2 text-xs text-ink-muted md:grid"
          >
            <span>Existing option</span>
            <span>What it does well</span>
            <span>What DealProof adds</span>
          </div>
          <ul className="border-t border-line-strong md:border-t-0">
            {DIFFERS.map((d) => (
              <li
                key={d.option}
                className="grid gap-x-8 gap-y-2 border-b border-line py-5 md:grid-cols-[3fr_4fr_5fr]"
              >
                <p className="text-base font-medium text-ink">{d.option}</p>
                <p className="text-base text-ink-secondary">
                  <span className="text-ink-muted md:hidden">Does well: </span>
                  {d.good}
                </p>
                <p className="text-base text-ink">
                  <span className="text-ink-muted md:hidden">
                    DealProof adds:{" "}
                  </span>
                  {d.adds}
                </p>
              </li>
            ))}
          </ul>
          <p className="mt-6 max-w-2xl text-base text-ink-secondary">
            {DIFFERS_HEAD.close}
          </p>
        </Reveal>
      </Container>
    </section>
  );
}

/* ───────────────────────── Who it is for ───────────────────────── */

export function AudienceSection() {
  return (
    <section className={cn(SECTION, "border-y border-line bg-surface")}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-6 lg:pr-12">
            <SectionHead {...AUDIENCE_HEAD} />
            <div className="mt-8 border-l-2 border-accent pl-4">
              <p className="text-sm font-medium text-ink">
                {FIRST_CUSTOMER.label}
              </p>
              <p className="mt-1 text-base text-pretty text-ink-secondary">
                {FIRST_CUSTOMER.body}
              </p>
            </div>
          </Reveal>
          <Reveal index={1} className="lg:col-span-6">
            <p className="pb-2 text-xs text-ink-muted">Also a fit</p>
            <dl className="border-t border-line-strong">
              {AUDIENCE.map((a) => (
                <div
                  key={a.who}
                  className="grid gap-x-6 gap-y-1 border-b border-line py-4 sm:grid-cols-[12rem_minmax(0,1fr)]"
                >
                  <dt className="text-base font-medium text-ink">{a.who}</dt>
                  <dd className="text-base text-ink-secondary">{a.need}</dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── Close ───────────────────────── */

export function CtaSection() {
  return (
    <section className={SECTION}>
      <Container>
        {/* COPY: from docs/content/home.md */}
        <Reveal className="mx-auto max-w-2xl text-center">
          <h2 className="font-serif text-3xl text-balance text-ink lg:text-4xl lg:tracking-display">
            {CTA.title}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base text-pretty text-ink-secondary lg:text-lg">
            {CTA.lead}
          </p>
          <div className="mt-8 flex flex-col sm:flex-row sm:justify-center">
            <Link href={APP_HREF} className={buttonPrimary}>
              {CTA.primary}
            </Link>
          </div>
        </Reveal>
      </Container>
    </section>
  );
}

export function SiteFooter() {
  const link =
    "rounded-xs text-ink-secondary transition-colors hover:text-ink";
  return (
    <footer className="border-t border-line-strong py-10">
      <Container className="flex flex-col gap-8 text-sm md:flex-row md:items-start md:justify-between">
        {/* COPY: from docs/content/home.md */}
        <div>
          <p className="text-base font-medium text-ink">DealProof</p>
          <p className="mt-1 max-w-xs text-ink-secondary">{FOOTER.line}</p>
        </div>
        <nav
          aria-label="Footer"
          className="flex flex-wrap gap-x-8 gap-y-3"
        >
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} className={link}>
              {l.label}
            </a>
          ))}
          <Link href={APP_HREF} className={link}>
            Open app
          </Link>
        </nav>
        <div className="text-ink-muted md:text-right">
          <p>{FOOTER.built}</p>
          <p className="mt-1">{FOOTER.disclaimer}</p>
        </div>
      </Container>
    </footer>
  );
}
