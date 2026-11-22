/**
 * The sections of the home page. Copy lives in ./content (from docs/content/home.md);
 * product marks and panels come from components/dealproof and components/ui.
 *
 * Section shapes alternate on purpose: window, tabs, two-sided list, ledger with a legend
 * and two unequal cells, paired readouts, panel, split, numbered list, table.
 */
import { Menu } from "lucide-react";
import Link from "next/link";
import {
  ClaimLedger,
  ClaimLedgerRow,
  DispositionStamp,
  Fact,
  JudgmentPanel,
  STATUS_INK,
  STATUS_SURFACE,
  SourceChip,
  StatusCounts,
  StatusGlyph,
  StatusMark,
} from "@/components/dealproof";
import { buttonVariants } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { CLAIM_STATUS_LABEL, DISPOSITION_MEANING } from "@/lib/labels";
import type { ClaimStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ASSESSMENT,
  AUDIENCE,
  AUDIENCE_HEAD,
  CASE_HEAD,
  CLAIMS,
  CLAIM_COUNTS,
  CTA,
  DIFFERS,
  DIFFERS_HEAD,
  DISPOSITIONS_HEAD,
  DISPOSITION_ORDER,
  FIT_HEAD,
  FIT_ROWS,
  FOOTER,
  HERO,
  ILLUSTRATION_LABEL,
  INVESTOR_HEAD,
  INVESTOR_ROW,
  JUDGMENT_HEAD,
  LIMITS,
  LIMITS_HEAD,
  NAV,
  NOT_CHECKED_CLAIM,
  PRINCIPLES,
  PRINCIPLES_HEAD,
  PROBLEM_HEAD,
  STATUS_HEAD,
  STATUS_MEANINGS,
  STATUS_NOTES,
  STEPS_HEAD,
} from "./content";
import { FitReadoutInView } from "./fit-readout";
import { HeroLedger } from "./hero-ledger";
import { Container, IllustrationLabel, SectionHead } from "./primitives";
import { ProblemLedger } from "./problem-ledger";
import { Reveal } from "./reveal";
import { Steps } from "./steps";

const SECTION = "py-16 md:py-24 lg:py-32";
const BAND = "border-y border-line bg-surface";
/** Sign-up sends a visitor who already has a session on to the app. */
const SIGNUP_HREF = "/signup";

const primary = buttonVariants({ variant: "primary", size: "lg" });
const secondary = buttonVariants({ variant: "secondary", size: "lg" });

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
          {NAV.links.map((l) => (
            <a key={l.href} href={l.href} className={link}>
              {l.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2 md:gap-5">
          <Link href="/login" className={cn(link, "hidden md:inline")}>
            {NAV.login}
          </Link>
          <Link
            href={SIGNUP_HREF}
            className={buttonVariants({ variant: "primary", size: "md" })}
          >
            {NAV.signup}
          </Link>
          <details className="relative md:hidden">
            <summary className="flex size-11 cursor-pointer list-none items-center justify-center rounded-md text-ink transition-colors hover:bg-surface-raised [&::-webkit-details-marker]:hidden">
              <Icon icon={Menu} />
              <span className="sr-only">Menu</span>
            </summary>
            <nav
              aria-label="Sections"
              className="absolute top-full right-0 mt-2 grid w-56 animate-overlay-in rounded-lg border border-line bg-surface p-2 shadow-md"
            >
              {[...NAV.links, { href: "/login", label: NAV.login }, { href: SIGNUP_HREF, label: NAV.signup }].map((l) => (
                <a
                  key={l.label}
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
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-sm text-ink-muted">{HERO.eyebrow}</p>
          <h1 className="mt-4 font-serif text-4xl tracking-display text-balance text-ink lg:text-5xl">
            {HERO.title}
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-base text-pretty text-ink-secondary md:text-lg">
            {HERO.lead}
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link href={SIGNUP_HREF} className={primary}>
              {HERO.primary}
            </Link>
            <a href="#case" className={secondary}>
              {HERO.secondary}
            </a>
          </div>
        </div>
        <div className="mt-12 lg:mt-16">
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
    <section className={cn(SECTION, BAND)}>
      <Container>
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

/* ───────────────────────── The claim ledger and its six answers ───────────────────────── */

/** "We employ 250 people": the worked example of an honest open answer. */
const OPEN_CLAIM = CLAIMS[1];

/** A status by name alone, for the legend. In a case, Not checked always carries its reason. */
function LegendTag({ status }: { status: ClaimStatus }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-sm border px-2 text-xs font-medium",
        STATUS_INK[status],
        STATUS_SURFACE[status],
      )}
    >
      <StatusGlyph status={status} />
      {CLAIM_STATUS_LABEL[status]}
    </span>
  );
}

export function CaseSection() {
  return (
    <section id="case" className={cn(SECTION, "scroll-mt-14")}>
      <Container>
        <Reveal className="flex flex-col items-start gap-6">
          <SectionHead
            eyebrow={CASE_HEAD.eyebrow}
            title={CASE_HEAD.title}
            lead={CASE_HEAD.lead}
          />
          <IllustrationLabel>{ILLUSTRATION_LABEL}</IllustrationLabel>
        </Reveal>

        <Reveal className="mt-8 lg:mt-12">
          <ClaimLedger label="Claim ledger for an illustrative company">
            {CLAIMS.map((claim, i) => (
              <ClaimLedgerRow
                key={claim.id}
                claim={claim}
                index={i}
                defaultExpanded={claim.status === "cannot_verify"}
              />
            ))}
          </ClaimLedger>
          <div className="mt-4 flex flex-col gap-4 rounded-lg border border-line bg-surface p-4 lg:flex-row lg:items-center lg:justify-between lg:gap-8">
            <div className="flex flex-col items-start gap-2">
              <StatusCounts counts={CLAIM_COUNTS} />
              <p className="max-w-2xl text-sm text-pretty text-ink-secondary">
                {CASE_HEAD.summary}
              </p>
            </div>
            <DispositionStamp
              disposition={CASE_HEAD.disposition}
              className="self-start lg:self-center"
            />
          </div>
        </Reveal>

        <Reveal className="mt-16 lg:mt-24">
          <h3 className="font-serif text-3xl text-balance text-ink">
            {STATUS_HEAD.title}
          </h3>
        </Reveal>
        <dl className="mt-8 grid border-t border-line-strong sm:grid-cols-2 lg:grid-cols-3">
          {STATUS_MEANINGS.map((s, i) => (
            <Reveal
              key={s.status}
              index={i}
              className="border-b border-line py-5 sm:pr-8"
            >
              <dt>
                <LegendTag status={s.status} />
              </dt>
              <dd className="mt-3 text-sm text-pretty text-ink-secondary">
                {s.meaning}
              </dd>
            </Reveal>
          ))}
        </dl>

        <div className="mt-10 grid gap-6 lg:grid-cols-12">
          <Reveal className="rounded-xl border border-line bg-surface p-5 lg:col-span-7 lg:p-8">
            <h3 className="font-serif text-2xl text-ink">
              {STATUS_NOTES.cannotVerify.title}
            </h3>
            <p className="mt-3 max-w-xl text-base text-pretty text-ink-secondary">
              {STATUS_NOTES.cannotVerify.body}
            </p>
            <div className="mt-6 flex flex-col items-start gap-2 rounded-md border border-line p-4 text-dense">
              <p className="text-ink">&ldquo;{OPEN_CLAIM.text}&rdquo;</p>
              <StatusMark status={OPEN_CLAIM.status} />
              <Fact
                evidence={OPEN_CLAIM.record[0].evidence}
                estimate={OPEN_CLAIM.record[0].estimate}
              >
                {OPEN_CLAIM.record[0].text}
              </Fact>
              <p className="text-ink">
                <span className="text-ink-muted">What would settle it: </span>
                {OPEN_CLAIM.what_would_settle}
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
            <p className="mt-3 text-base text-pretty text-ink-secondary">
              {STATUS_NOTES.notChecked.body}
            </p>
            <div className="hatch mt-6 flex flex-col items-start gap-2 rounded-md border border-dashed border-not-checked-line p-4 text-dense">
              <p className="text-ink">
                &ldquo;{NOT_CHECKED_CLAIM.text}&rdquo;
              </p>
              <StatusMark
                status="not_checked"
                reason={NOT_CHECKED_CLAIM.not_checked_reason}
              />
              <p className="text-ink-secondary">
                No search was run for this claim
              </p>
            </div>
          </Reveal>
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── Fit is not evidence ───────────────────────── */

export function FitSection() {
  return (
    <section className={cn(SECTION, BAND)}>
      <Container>
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-5 lg:pr-8">
            <SectionHead
              eyebrow={FIT_HEAD.eyebrow}
              title={FIT_HEAD.title}
              lead={FIT_HEAD.lead}
            />
          </Reveal>
          <div className="flex flex-col gap-8 lg:col-span-7">
            {FIT_ROWS.map((row) => (
              <div
                key={row.id}
                className="flex flex-col gap-3 border-t border-line-strong pt-5"
              >
                <FitReadoutInView fit={row.fit} />
                <p className="text-sm text-ink">{row.caption}</p>
              </div>
            ))}
            <p className="border-t border-line pt-5">
              <IllustrationLabel>{FIT_HEAD.label}</IllustrationLabel>
            </p>
          </div>
        </div>
      </Container>
    </section>
  );
}

/* ───────────────────────── Five judgments, four dispositions ───────────────────────── */

export function JudgmentSection() {
  return (
    <section className={SECTION}>
      <Container>
        <Reveal>
          <SectionHead
            eyebrow={JUDGMENT_HEAD.eyebrow}
            title={JUDGMENT_HEAD.title}
            lead={JUDGMENT_HEAD.lead}
          />
        </Reveal>

        <Reveal className="mt-10 lg:mt-16">
          <JudgmentPanel assessment={ASSESSMENT} className="shadow-md" />
          <div className="mt-4 flex flex-col items-start gap-3 lg:flex-row lg:items-baseline lg:gap-6">
            <IllustrationLabel>{ILLUSTRATION_LABEL}</IllustrationLabel>
            <p className="max-w-3xl text-dense text-pretty text-ink-muted">
              {JUDGMENT_HEAD.note}
            </p>
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
    <section className={cn(SECTION, BAND)}>
      <Container>
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-5 lg:pr-8">
            <SectionHead
              eyebrow={INVESTOR_HEAD.eyebrow}
              title={INVESTOR_HEAD.title}
              lead={INVESTOR_HEAD.lead}
            />
            <p className="mt-4 text-base text-pretty text-ink-secondary">
              {INVESTOR_HEAD.body}
            </p>
            <ul className="mt-6 grid gap-2 border-t border-line pt-6 text-sm text-ink">
              {INVESTOR_HEAD.shows.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </Reveal>

          <Reveal index={1} className="min-w-0 lg:col-span-7">
            <figure>
              <div className="overflow-hidden rounded-xl border border-line bg-paper">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-3 lg:px-5">
                  <p className="text-base font-medium text-ink">
                    {INVESTOR_ROW.name}
                  </p>
                  <p className="font-mono text-xs text-ink-secondary">
                    {INVESTOR_ROW.lead}
                  </p>
                </div>
                <div className="px-4 py-4 lg:px-5">
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
                          <SourceChip evidence={b.evidence} />
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
              <figcaption className="mt-3 flex flex-col items-start gap-3">
                <IllustrationLabel>{INVESTOR_ROW.label}</IllustrationLabel>
                <span className="text-dense text-pretty text-ink-muted">
                  {INVESTOR_HEAD.guardrails}
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
                  <summary className="focus-inset flex min-h-14 cursor-pointer list-none items-baseline gap-4 py-4 [&::-webkit-details-marker]:hidden">
                    <span className="w-6 shrink-0 font-mono text-xs text-ink-muted">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="flex-1 text-lg text-ink transition-colors group-hover:text-accent">
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
                  <p className="animate-fade-in pr-8 pb-5 pl-10 text-base text-pretty text-ink-secondary motion-reduce:animate-none">
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
    <section id="limits" className={cn(SECTION, BAND, "scroll-mt-14")}>
      <Container>
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
            <span>Existing category</span>
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
          <p className="mt-6 max-w-2xl text-base text-pretty text-ink-secondary">
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
    <section className={cn(SECTION, BAND)}>
      <Container>
        <div className="grid gap-10 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-6 lg:pr-12">
            <SectionHead
              eyebrow={AUDIENCE_HEAD.eyebrow}
              title={AUDIENCE_HEAD.title}
              lead={AUDIENCE_HEAD.lead}
            />
            <p className="mt-4 text-base text-pretty text-ink-secondary">
              {AUDIENCE_HEAD.body}
            </p>
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
        <Reveal className="mx-auto max-w-2xl text-center">
          <h2 className="font-serif text-3xl text-balance text-ink lg:text-4xl lg:tracking-display">
            {CTA.title}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base text-pretty text-ink-secondary lg:text-lg">
            {CTA.lead}
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link href={SIGNUP_HREF} className={primary}>
              {CTA.primary}
            </Link>
            <a href="#case" className={secondary}>
              {CTA.secondary}
            </a>
          </div>
        </Reveal>
      </Container>
    </section>
  );
}

export function SiteFooter() {
  const link = "rounded-xs text-ink-secondary transition-colors hover:text-ink";
  return (
    <footer className="border-t border-line-strong py-10">
      <Container className="flex flex-col gap-6 text-sm md:flex-row md:items-baseline md:justify-between">
        <p className="text-ink-secondary">
          <span className="text-base font-medium text-ink">DealProof</span>
          <span aria-hidden> · </span>
          {FOOTER.built}
        </p>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-8 gap-y-3">
          {FOOTER.links.map((l) => (
            <a key={l.label} href={l.href} className={link}>
              {l.label}
            </a>
          ))}
        </nav>
        <p className="text-ink-muted">{FOOTER.scope}</p>
      </Container>
    </footer>
  );
}
