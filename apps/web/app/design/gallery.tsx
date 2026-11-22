"use client";

import { Plus, Printer } from "lucide-react";
import { useState } from "react";
import {
  ApprovalBlock,
  ApprovalReceipt,
  ApprovalSteps,
  ClaimLedger,
  ClaimLedgerRow,
  CostReadout,
  CriteriaStrip,
  DispositionStamp,
  DispositionSummary,
  EstimateLabel,
  Fact,
  HatchedBlock,
  IdentityBadge,
  JudgmentPanel,
  NumberTween,
  ReadingOldVersionBanner,
  RuleBreakBlock,
  RunProgress,
  SourceChip,
  SourceLine,
  StatusCounts,
  StatusDistribution,
  StatusLegend,
  StatusMark,
  TestModeBanner,
  UnsourcedBlock,
  VersionDiff,
  VersionRail,
  WaitingOnIdentity,
} from "@/components/dealproof";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Field,
  Icon,
  Input,
  Kbd,
  Panel,
  PanelBody,
  PanelHeader,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  SkeletonText,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
} from "@/components/ui";
import { CLAIM_STATUS_MEANING, DISPOSITION_MEANING } from "@/lib/labels";
import { type SoundCue, useSound } from "@/lib/sound";
import {
  CLAIM_STATUSES,
  DISPOSITIONS,
  NOT_CHECKED_REASONS,
  type ClaimStatus,
  type RequestStatus,
  type SellerRequest,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import * as sample from "./sample-data";

const SECTIONS = [
  ["foundations", "Foundations"],
  ["primitives", "Primitives"],
  ["source-line", "Source line"],
  ["claim-status", "Claim status"],
  ["disposition", "Disposition stamp"],
  ["estimate", "Estimate label"],
  ["identity", "Identity"],
  ["criteria", "Criteria strip"],
  ["judgments", "Judgment panel"],
  ["ledger", "Claim ledger"],
  ["run", "Run progress"],
  ["cost", "Cost readout"],
  ["diff", "Version diff"],
  ["approval", "Approval"],
  ["sound", "Sound"],
] as const;

function Section({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="flex scroll-mt-6 flex-col gap-6">
      <div className="flex flex-col gap-1 border-b border-line-strong pb-3">
        <h2 id={`${id}-title`} className="text-2xl font-medium text-ink">
          {title}
        </h2>
        <p className="max-w-(--layout-prose-max) text-sm text-ink-secondary">{lead}</p>
      </div>
      {children}
    </section>
  );
}

/** One state of one component, with its name above it. */
function Specimen({
  label,
  note,
  children,
  className,
}: {
  label: string;
  note?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-xs text-ink-muted">
        <span className="font-medium text-ink-secondary">{label}</span>
        {note ? <span> · {note}</span> : null}
      </p>
      <div className={cn("min-w-0", className)}>{children}</div>
    </div>
  );
}

const row = "flex flex-wrap items-center gap-3";

function Swatch({ name, className, hex }: { name: string; className: string; hex: string }) {
  return (
    <li className="flex items-center gap-3">
      <span className={cn("size-8 shrink-0 rounded-md border border-line-strong", className)} aria-hidden />
      <span className="flex flex-col">
        <span className="text-dense text-ink">{name}</span>
        <span className="font-mono text-2xs text-ink-muted">{hex}</span>
      </span>
    </li>
  );
}

function Foundations() {
  return (
    <Section
      id="foundations"
      title="Foundations"
      lead="Paper and ink, one registrar-blue accent, three type families. Tokens live in app/globals.css and mirror docs/design/tokens.css."
    >
      <Specimen label="Neutrals and accent">
        <ul className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
          <Swatch name="paper" className="bg-paper" hex="#F7F7F5" />
          <Swatch name="paper-warm" className="bg-paper-warm" hex="#F5F2EA" />
          <Swatch name="surface" className="bg-surface" hex="#FFFFFF" />
          <Swatch name="surface-raised" className="bg-surface-raised" hex="#F0F0ED" />
          <Swatch name="surface-sunken" className="bg-surface-sunken" hex="#EBEBE7" />
          <Swatch name="ink" className="bg-ink" hex="#16181D" />
          <Swatch name="ink-secondary" className="bg-ink-secondary" hex="#454A54" />
          <Swatch name="ink-muted" className="bg-ink-muted" hex="#626771" />
          <Swatch name="accent" className="bg-accent" hex="#24408E" />
          <Swatch name="accent-tint" className="bg-accent-tint" hex="#E9EDF8" />
        </ul>
      </Specimen>

      <Specimen label="Type scale" note="hierarchy from size and ink, not weight">
        <div className="flex flex-col gap-3">
          <p className="font-serif text-5xl tracking-display text-ink">Know what is proven</p>
          <p className="font-serif text-4xl tracking-display text-ink">Newsreader 44, section head</p>
          <p className="font-serif text-3xl text-ink">Newsreader 32, memo title</p>
          <p className="text-2xl font-medium text-ink">Plex Sans 24, page title</p>
          <p className="text-xl font-medium text-ink">Plex Sans 20, card title</p>
          <p className="text-lg text-ink-secondary">Plex Sans 18, lead paragraph</p>
          <p className="text-base text-ink">Plex Sans 16, reading body for memo prose</p>
          <p className="text-sm text-ink">Plex Sans 14, interface body, navigation, buttons</p>
          <p className="text-dense text-ink">Plex Sans 13, ledger and table cells</p>
          <p className="text-xs text-ink-secondary">Plex Sans 12, table headers and captions</p>
          <p className="font-mono text-2xs text-ink-secondary">
            Plex Mono 11, the floor: as of 14 Oct 2026 · 86 cr · $0.42
          </p>
        </div>
      </Specimen>

      <div className="grid gap-6 lg:grid-cols-2">
        <Specimen label="Radii" note="4 chip · 6 status · 8 control · 12 card · 16 panel">
          <div className={row}>
            {(["rounded-xs", "rounded-sm", "rounded-md", "rounded-lg", "rounded-xl"] as const).map(
              (radius) => (
                <span
                  key={radius}
                  className={cn(
                    "flex size-16 items-center justify-center border border-line-strong bg-surface font-mono text-2xs text-ink-secondary",
                    radius,
                  )}
                >
                  {radius.replace("rounded-", "")}
                </span>
              ),
            )}
          </div>
        </Specimen>
        <Specimen label="Elevation" note="hairline · shadow-xs · shadow-md · shadow-lg">
          <div className={cn(row, "gap-6 p-2")}>
            {(["", "shadow-xs", "shadow-md", "shadow-lg"] as const).map((shadow, level) => (
              <span
                key={level}
                className={cn(
                  "flex size-16 items-center justify-center rounded-lg border border-line bg-surface font-mono text-2xs text-ink-secondary",
                  shadow,
                )}
              >
                {level}
              </span>
            ))}
          </div>
        </Specimen>
      </div>

      <Specimen label="Hatch" note="anything that did not happen is hatched and dashed, never flat">
        <div className="grid gap-3 sm:grid-cols-3">
          <span className="hatch h-12 rounded-md border border-dashed border-not-checked-line" aria-hidden />
          <span className="hatch-dense h-12 rounded-md border border-dashed border-not-checked-line" aria-hidden />
          <HatchedBlock innerClassName="text-dense">HatchedBlock keeps its text on a plain interior</HatchedBlock>
        </div>
      </Specimen>
    </Section>
  );
}

function Primitives() {
  const [selectedRow, setSelectedRow] = useState("r2");

  return (
    <Section
      id="primitives"
      title="Primitives"
      lead="Radix-based controls in components/ui. The primary button is ink, not accent. Every control has a hover state and a 2px accent focus ring; tab through this section to see it."
    >
      <Specimen label="Button" note="primary · secondary · quiet · destructive · link">
        <div className="flex flex-col gap-3">
          <div className={row}>
            <Button variant="primary">Start a screening</Button>
            <Button>Open case</Button>
            <Button variant="quiet">Cancel</Button>
            <Button variant="destructive">Delete document</Button>
            <Button variant="link" size="inline">
              Scoring policy
            </Button>
          </div>
          <div className={row}>
            <Button variant="primary" size="sm">
              Small 32
            </Button>
            <Button variant="primary">Default 36</Button>
            <Button variant="primary" size="lg">
              Large 44
            </Button>
            <Button>
              <Icon icon={Plus} />
              New case
            </Button>
            <Button size="icon" aria-label="Print memo">
              <Icon icon={Printer} />
            </Button>
            <Button variant="primary" disabled>
              Disabled
            </Button>
            <Button disabled>Disabled</Button>
          </div>
        </div>
      </Specimen>

      <div className="grid gap-6 lg:grid-cols-2">
        <Specimen label="Input, Textarea, Field">
          <div className="flex flex-col gap-4">
            <Field label="Company name" hint="The legal name, if you know it">
              {(control) => <Input {...control} placeholder="Meridian Warehousing" />}
            </Field>
            <Field label="Website" error="Enter a domain, for example example.com">
              {(control) => <Input {...control} defaultValue="not a domain" />}
            </Field>
            <Field label="Thesis">
              {(control) => (
                <Textarea
                  {...control}
                  defaultValue="Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion"
                />
              )}
            </Field>
            <Field label="Disabled">{(control) => <Input {...control} disabled defaultValue="Read only" />}</Field>
          </div>
        </Specimen>

        <div className="flex flex-col gap-6">
          <Specimen label="Select">
            <Select defaultValue="series-a">
              <SelectTrigger aria-label="Funding stage" className="max-w-xs">
                <SelectValue placeholder="Funding stage" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="seed">Seed</SelectItem>
                <SelectItem value="series-a">Series A</SelectItem>
                <SelectItem value="series-b">Series B</SelectItem>
                <SelectItem value="growth">Growth equity</SelectItem>
              </SelectContent>
            </Select>
          </Specimen>

          <Specimen label="Tooltip, Popover, Dialog">
            <div className={row}>
              <Tooltip content="A tooltip repeats what the page already says">
                <Button>Hover or focus</Button>
              </Tooltip>
              <Popover>
                <PopoverTrigger asChild>
                  <Button>Open popover</Button>
                </PopoverTrigger>
                <PopoverContent>
                  <p className="text-dense text-ink">
                    Popovers hold detail on demand, such as the evidence behind a source chip.
                  </p>
                </PopoverContent>
              </Popover>
              <Dialog>
                <DialogTrigger asChild>
                  <Button>Open dialog</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Send this request once</DialogTitle>
                    <DialogDescription>
                      A dialog interrupts, so the product uses it in one place: confirming a send.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <DialogClose asChild>
                      <Button>Go back</Button>
                    </DialogClose>
                    <DialogClose asChild>
                      <Button variant="primary">Send once</Button>
                    </DialogClose>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
          </Specimen>

          <Specimen label="Badge, Kbd">
            <div className={row}>
              <Badge>Dated events</Badge>
              <Badge variant="outline">Recorded</Badge>
              <Badge variant="accent">Selected</Badge>
              <Badge variant="mono">v2 · policy 1.0</Badge>
              <Badge variant="test-mode">Test mode</Badge>
              <span className="inline-flex items-center gap-1">
                <Kbd>⌘</Kbd>
                <Kbd>K</Kbd>
              </span>
            </div>
          </Specimen>

          <Specimen label="Skeleton" note="fades twice, then holds still">
            <div className="flex flex-col gap-3">
              <SkeletonText lines={3} label="Loading sample text" />
              <div className={row}>
                <Skeleton className="size-8 rounded-md" />
                <Skeleton className="h-6 w-32" />
                <span className="text-xs text-ink-muted">Still working</span>
              </div>
            </div>
          </Specimen>
        </div>
      </div>

      <Specimen label="Tabs" note="arrow keys move between tabs; the underline slides">
        <Tabs defaultValue="claims">
          <TabsList aria-label="Sample case sections">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="claims" count={12}>
              Claims
            </TabsTrigger>
            <TabsTrigger value="events" count={5}>
              Events
            </TabsTrigger>
            <TabsTrigger value="sources" count={31}>
              Sources
            </TabsTrigger>
            <TabsTrigger value="cost" disabled>
              Cost
            </TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="text-dense text-ink-secondary">
            Overview content
          </TabsContent>
          <TabsContent value="claims" className="text-dense text-ink-secondary">
            Claims content
          </TabsContent>
          <TabsContent value="events" className="text-dense text-ink-secondary">
            Events content
          </TabsContent>
          <TabsContent value="sources" className="text-dense text-ink-secondary">
            Sources content
          </TabsContent>
        </Tabs>
      </Specimen>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Specimen label="Card, Panel">
          <div className="flex flex-col gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Card title</CardTitle>
                <CardDescription>Radius 12, a hairline, no shadow</CardDescription>
              </CardHeader>
              <CardContent className="text-dense text-ink-secondary">Card content</CardContent>
              <CardFooter>
                <Button size="sm">Action</Button>
              </CardFooter>
            </Card>
            <Panel>
              <PanelHeader>
                <h3 className="text-sm font-medium text-ink">Panel</h3>
                <p className="font-mono text-2xs text-ink-secondary">radius 16</p>
              </PanelHeader>
              <PanelBody className="text-dense text-ink-secondary">Panel body</PanelBody>
            </Panel>
          </div>
        </Specimen>

        <Specimen label="Table" note="click a row to select it; selected is tint, a left bar and aria-selected">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Company (sample)</TableHead>
                <TableHead>Region</TableHead>
                <TableHead numeric>Founded</TableHead>
                <TableHead numeric>Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[
                ["r1", "Meridian Warehousing", "Pune", "2014", "86 cr · $0.42"],
                ["r2", "Cold Chain Logix", "Nashik", "2016", "12 cr · $0.04"],
                ["r3", "Northline Freight", "Indore", "2011", "38 cr · $0.11"],
              ].map(([id, name, region, founded, cost]) => (
                <TableRow
                  key={id}
                  data-state={selectedRow === id ? "selected" : undefined}
                  aria-selected={selectedRow === id}
                  onClick={() => setSelectedRow(id)}
                >
                  <TableCell>{name}</TableCell>
                  <TableCell>{region}</TableCell>
                  <TableCell numeric>{founded}</TableCell>
                  <TableCell numeric>{cost}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Specimen>
      </div>
    </Section>
  );
}

function SourceLineSection() {
  return (
    <Section
      id="source-line"
      title="Source line"
      lead="The signature of the product: every fact ends in a chip naming where it came from and a mono as-of date. Click a chip, or focus it and press Enter, to open the evidence."
    >
      <Specimen label="SourceChip" note="one glyph per reliability class">
        <div className={row}>
          {sample.allClasses.map((evidence) => (
            <SourceChip key={evidence.source.label} evidence={evidence} />
          ))}
        </div>
      </Specimen>

      <div className="grid gap-6 lg:grid-cols-2">
        <Specimen label="Unknown date" note="says so; never left blank">
          <SourceChip evidence={sample.ev.undated} />
        </Specimen>
        <Specimen label="SourceLine with several sources" note="two visible, then +N">
          <SourceLine
            evidence={[sample.ev.fundingAnnouncement, sample.ev.news, sample.ev.newsLater, sample.ev.deck(8)]}
          />
        </Specimen>
        <Specimen label="Fact" note="statement, then its source line">
          <div className="flex flex-col items-start gap-3 text-dense">
            <Fact evidence={[sample.ev.registry]}>Incorporated 2014, Pune</Fact>
            <Fact
              evidence={[sample.ev.profiles]}
              estimate={{ kind: "estimate", basis: "from professional profiles, not a payroll count" }}
            >
              180 people
            </Fact>
            <Fact evidence={[sample.ev.fundingAnnouncement, sample.ev.news]} layout="stacked">
              Raised Series A
            </Fact>
          </div>
        </Specimen>
        <Specimen
          label="No source, no render"
          note="development shows this block; production omits the fact and logs it"
        >
          <UnsourcedBlock what="Revenue grew 40% last year" />
        </Specimen>
      </div>
    </Section>
  );
}

function ClaimStatusSection() {
  const [index, setIndex] = useState(0);
  const settling: ClaimStatus = CLAIM_STATUSES[index % CLAIM_STATUSES.length];

  return (
    <Section
      id="claim-status"
      title="Claim status"
      lead="Six statuses, six silhouettes. Shape and words carry the meaning; colour only reinforces it. Not checked is the only one that is dashed and hatched, and it always states its reason."
    >
      <Specimen label="Tag" note="the default form">
        <ul className="grid gap-x-6 gap-y-3 md:grid-cols-2">
          {CLAIM_STATUSES.map((status) => (
            <li key={status} className="flex flex-wrap items-center gap-3">
              <StatusMark status={status} reason="budget_reached" />
              <span className="text-xs text-ink-secondary">{CLAIM_STATUS_MEANING[status]}</span>
            </li>
          ))}
        </ul>
      </Specimen>

      <div className="grid gap-6 lg:grid-cols-2">
        <Specimen label="Not checked, with each reason">
          <div className={row}>
            {NOT_CHECKED_REASONS.map((reason) => (
              <StatusMark key={reason} status="not_checked" reason={reason} />
            ))}
            <StatusMark status="not_checked" />
          </div>
        </Specimen>
        <Specimen label="Mark" note="glyph only; always beside a legend">
          <div className="flex flex-col gap-3">
            <div className={row}>
              {CLAIM_STATUSES.map((status) => (
                <StatusMark key={status} status={status} form="mark" reason="budget_reached" />
              ))}
            </div>
            <StatusLegend />
          </div>
        </Specimen>
        <Specimen label="Count" note="fixed order; a non-zero Not checked count is always shown">
          <div className="flex flex-col items-start gap-2">
            <StatusCounts counts={sample.counts} />
            <StatusCounts counts={sample.countsComplete} />
          </div>
        </Specimen>
        <Specimen label="Settling" note="the mark fades in and scales from 0.9 when a rule fires">
          <div className={row}>
            <StatusMark status={settling} reason="step_failed" />
            <Button size="sm" onClick={() => setIndex((value) => value + 1)}>
              Next status
            </Button>
          </div>
        </Specimen>
      </div>

      <Specimen
        label="StatusDistribution"
        note="the Not checked segment is hatched and sits after a gap, so the bar reads as unfinished"
      >
        <div className="flex max-w-2xl flex-col gap-4">
          <div className="flex flex-col gap-1">
            <p className="font-mono text-xs text-ink">9 of 12 required checks settled · 3 not checked</p>
            <StatusDistribution counts={sample.counts} />
          </div>
          <div className="flex flex-col gap-1">
            <p className="font-mono text-xs text-ink">12 of 12 required checks settled</p>
            <StatusDistribution counts={sample.countsComplete} />
          </div>
        </div>
      </Specimen>
    </Section>
  );
}

function DispositionSection() {
  return (
    <Section
      id="disposition"
      title="Disposition stamp"
      lead="Four outcomes. A stamp is taller than a status tag, has a 1.5px border in its own ink and a 600 label, so it is never mistaken for a claim status. Deprioritise is graphite, not red."
    >
      <Specimen label="DispositionStamp" note="32px default">
        <ul className="grid gap-x-6 gap-y-3 md:grid-cols-2">
          {DISPOSITIONS.map((disposition) => (
            <li key={disposition} className="flex flex-wrap items-center gap-3">
              <DispositionStamp disposition={disposition} />
              <span className="text-xs text-ink-secondary">{DISPOSITION_MEANING[disposition]}</span>
            </li>
          ))}
        </ul>
      </Specimen>
      <div className="grid gap-6 lg:grid-cols-2">
        <Specimen label="Header size" note="40px, for the case header">
          <div className={row}>
            {DISPOSITIONS.map((disposition) => (
              <DispositionStamp key={disposition} disposition={disposition} size="header" />
            ))}
          </div>
        </Specimen>
        <Specimen label="DispositionSummary" note="a stamp never appears without its reasons and policy version">
          <DispositionSummary result={sample.assessment.disposition} />
        </Specimen>
      </div>
    </Section>
  );
}

function EstimateSection() {
  return (
    <Section
      id="estimate"
      title="Estimate label"
      lead="A value that is not a recorded fact is marked three ways at once: a tilde, a dotted underline and the word. Estimate is a number inferred from indirect data; Signal is an observation that suggests something without proving it."
    >
      <div className="grid gap-6 text-dense lg:grid-cols-3">
        <Specimen label="Estimate" note="basis on hover and focus">
          <EstimateLabel kind="estimate" basis="from professional profiles, not a payroll count">
            180 people
          </EstimateLabel>
        </Specimen>
        <Specimen label="Signal">
          <EstimateLabel kind="signal" basis="open job listings, which can be stale">
            2 open roles
          </EstimateLabel>
        </Specimen>
        <Specimen label="Basis shown inline" note="for expanded rows and print">
          <EstimateLabel kind="estimate" basis="from professional profiles, not a payroll count" showBasis>
            180 people
          </EstimateLabel>
        </Specimen>
      </div>
    </Section>
  );
}

function IdentitySection() {
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <Section
      id="identity"
      title="Identity"
      lead="Identity comes first. Confirmed shows the keys that matched, each with its source; the keys are the proof. Unresolved lists the candidates side by side and attaches nothing until a person chooses."
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <Specimen label="Confirmed, band">
          <IdentityBadge identity={sample.identityConfirmed} />
        </Specimen>
        <div className="flex flex-col gap-6">
          <Specimen label="Inline" note="case header and dashboard rows">
            <div className="flex flex-col items-start gap-2">
              <IdentityBadge identity={sample.identityConfirmed} variant="inline" />
              <IdentityBadge identity={sample.identityUnresolved} variant="inline" />
            </div>
          </Specimen>
          <Specimen label="WaitingOnIdentity" note="replaces identity-dependent tab content">
            <WaitingOnIdentity />
          </Specimen>
        </div>
      </div>
      <Specimen label="Unresolved, band">
        <div className="flex flex-col gap-2">
          <IdentityBadge identity={sample.identityUnresolved} onChoose={(candidate) => setChosen(candidate.name)} />
          <p className="text-xs text-ink-muted" role="status">
            {chosen ? `Gallery only: you chose ${chosen}` : "Gallery only: nothing chosen yet"}
          </p>
        </div>
      </Specimen>
    </Section>
  );
}

function CriteriaSection() {
  const [fitValue, setFitValue] = useState(82);
  return (
    <Section
      id="criteria"
      title="Criteria strip"
      lead="Fit and the assessable share are one component and are never shown apart. The track is all criteria, weighted; what could not be assessed is hatched at the right end. Focus a cell to read its criterion."
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <Specimen label="Fit 82 with 70% assessable">
          <CriteriaStrip fit={sample.fit} caption />
        </Specimen>
        <Specimen label="Fit 82 with 100% assessable" note="the same score on full evidence looks different">
          <CriteriaStrip fit={sample.fitFull} />
        </Specimen>
        <Specimen label="Fit unavailable" note="nothing could be assessed, so there is no number">
          <CriteriaStrip fit={sample.fitUnavailable} />
        </Specimen>
        <Specimen label="Compact" note="6px strip for shortlist and dashboard rows">
          <div className="flex flex-col gap-3">
            <CriteriaStrip fit={sample.fit} size="compact" />
            <CriteriaStrip fit={sample.fitFull} size="compact" />
            <CriteriaStrip fit={sample.fitUnavailable} size="compact" />
          </div>
        </Specimen>
      </div>
      <Specimen label="NumberTween" note="a figure that changes tweens to its new value over 360ms">
        <div className={row}>
          <span className="font-mono text-3xl font-semibold text-ink">
            <NumberTween value={fitValue} />
          </span>
          <Button size="sm" onClick={() => setFitValue((value) => (value === 82 ? 64 : 82))}>
            Change the value
          </Button>
        </div>
      </Specimen>
    </Section>
  );
}

function JudgmentSection() {
  return (
    <Section
      id="judgments"
      title="Judgment panel"
      lead="Five judgments, five shapes, no total. They sit together so they are read together, and they are drawn differently so they cannot be averaged by eye."
    >
      <Specimen label="Full" note="financial assessment not assessed: it keeps its place so its absence is seen">
        <JudgmentPanel assessment={sample.assessment} />
      </Specimen>
      <Specimen label="Full, with financial inputs and every check settled">
        <JudgmentPanel assessment={sample.assessmentWithFinancials} />
      </Specimen>
      <Specimen label="Rail" note="five one-line rows for the sticky rail, 320 wide">
        <JudgmentPanel assessment={sample.assessment} variant="rail" className="max-w-(--layout-rail)" />
      </Specimen>
    </Section>
  );
}

function LedgerSection() {
  const [ran, setRan] = useState<string | null>(null);
  return (
    <Section
      id="ledger"
      title="Claim ledger"
      lead="What the seller said, set against what the record shows, with the status on the spine between them. Click a row or press Enter to expand it; arrow keys move between rows. Under 1024px each row stacks."
    >
      <Specimen label="ClaimLedger with ClaimLedgerRow" note="all six statuses, a selected row and a row still being checked">
        <div className="flex flex-col gap-2">
          <ClaimLedger label="Sample claim ledger">
            {sample.claims.map((claim, index) => (
              <ClaimLedgerRow
                key={claim.id}
                claim={claim}
                index={index}
                selected={claim.id === "c2"}
                defaultExpanded={claim.id === "c5"}
                changedHref="#diff"
                onRunCheck={(target) => setRan(`claim ${target.number}`)}
              />
            ))}
            <ClaimLedgerRow claim={sample.pendingClaim} index={7} pending />
          </ClaimLedger>
          <p className="text-xs text-ink-muted" role="status">
            {ran ? `Gallery only: Run check pressed for ${ran}. Nothing was spent` : "Gallery only: Run check spends nothing here"}
          </p>
        </div>
      </Specimen>
      <Specimen label="Rule breaks" note="data that breaks a product rule renders as an error, not as a tidy row">
        <ClaimLedger label="Sample ledger with broken data">
          <ClaimLedgerRow
            claim={{ ...sample.claims[1], id: "bad-1", number: 9, what_would_settle: null }}
          />
          <ClaimLedgerRow claim={{ ...sample.claims[0], id: "bad-2", number: 10, record: [] }} />
        </ClaimLedger>
      </Specimen>
    </Section>
  );
}

function RunSection() {
  const [step, setStep] = useState(3);
  const total = sample.runRunning.steps.length;
  const live = {
    ...sample.runRunning,
    elapsed_seconds: 134 + (step - 3) * 9,
    credits_used: 38 + (step - 3) * 7,
    steps: sample.runRunning.steps.map((item, index) =>
      index < step
        ? {
            ...item,
            status: "done" as const,
            result: item.result ?? "finished",
            credits_used: item.credits_used ?? (item.model_usd == null ? 7 : null),
          }
        : index === step
          ? { ...item, status: "running" as const, detail: item.detail ?? "working through the claims" }
          : { ...item, status: "pending" as const },
    ),
  };

  return (
    <Section
      id="run"
      title="Run progress"
      lead="The steps, in order, as they happen. No progress bar and no percentage. The orb is the one moving indicator in the product; with reduced motion it becomes the word Working."
    >
      <Specimen label="Running" note="advance it to see the credit count tween; a screen reader hears one line per step">
        <div className="flex flex-col gap-2">
          <RunProgress run={live} />
          <div className={row}>
            <Button size="sm" disabled={step >= total - 1} onClick={() => setStep((value) => value + 1)}>
              Advance one step
            </Button>
            <Button size="sm" variant="quiet" onClick={() => setStep(3)}>
              Reset
            </Button>
          </div>
        </div>
      </Specimen>
      <Specimen label="Resumed after an interruption" note="kept steps cost nothing the second time">
        <RunProgress run={sample.runResumed} />
      </Specimen>
      <Specimen label="A step failed, and one was skipped for budget" note="skipped is hatched; it becomes Not checked on the claims">
        <RunProgress run={sample.runFailed} onRetryStep={() => {}} />
      </Specimen>
      <Specimen label="Finished" note="collapses to one line and stays as a link to the run log">
        <RunProgress run={sample.runFinished} logHref="#run" />
      </Specimen>
    </Section>
  );
}

function CostSection() {
  return (
    <Section
      id="cost"
      title="Cost readout"
      lead="Crustdata credits and model dollars are two currencies and are never added together. Reaching the budget is a stated limit, so nothing turns red."
    >
      <Specimen label="Full">
        <CostReadout cost={sample.cost} />
      </Specimen>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        <Specimen label="Budget reached" note="links to the claims that were not checked">
          <CostReadout cost={{ ...sample.costReached, lines: sample.cost.lines.slice(0, 2) }} notCheckedHref="#ledger" />
        </Specimen>
        <Specimen label="Compact" note="case header and dashboard rows">
          <CostReadout cost={sample.cost} variant="compact" />
        </Specimen>
      </div>
    </Section>
  );
}

function DiffSection() {
  const [replay, setReplay] = useState(0);
  return (
    <Section
      id="diff"
      title="Version diff"
      lead="New evidence changes the assessment in the open. Every change is old → new with both drawn in full, a stated cause and a source. A downgrade is presented exactly like an upgrade."
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="flex flex-col gap-6">
          <Specimen label="VersionRail">
            <VersionRail versions={sample.versions} current={2} onOpen={() => {}} />
          </Specimen>
          <Specimen label="Reading an earlier version">
            <ReadingOldVersionBanner reading={1} current={2} />
          </Specimen>
        </div>
        <Specimen label="VersionDiff" note="replay the one-time highlight; with reduced motion a Changed tag stays instead">
          <div className="flex flex-col items-start gap-2">
            <VersionDiff key={replay} diff={sample.diff} highlight={replay > 0} onShowUnchanged={() => {}} className="w-full" />
            <Button size="sm" onClick={() => setReplay((value) => value + 1)}>
              Replay the highlight
            </Button>
          </div>
        </Specimen>
      </div>
      <Specimen label="A downgrade, and a change with no stated cause" note="the second is a bug in the data and renders as one">
        <VersionDiff diff={sample.diffDowngrade} />
      </Specimen>
    </Section>
  );
}

function ApprovalDemo({ testMode, signedIn }: { testMode: boolean; signedIn: boolean }) {
  const { playCue } = useSound();
  const [request, setRequest] = useState<SellerRequest>(sample.requests.draft);

  return (
    <div className="flex flex-col items-start gap-2">
      <ApprovalBlock
        key={request.status}
        request={request}
        testMode={testMode}
        signedInUser={signedIn ? sample.sampleUser : null}
        messageHref="#approval"
        className="w-full"
        onApprove={(draft) => {
          setRequest({
            ...request,
            ...draft,
            status: testMode ? "suppressed_test_mode" : "sent",
            approver: sample.sampleUser,
            approved_at: "2026-11-22T11:18:00Z",
          });
          // A suppressed send uses the neutral cue, never the success cue.
          playCue(testMode ? "run_finished" : "request_sent");
        }}
      />
      {request.status !== "draft" ? (
        <Button size="sm" variant="quiet" onClick={() => setRequest(sample.requests.draft)}>
          Reset this example
        </Button>
      ) : null}
    </div>
  );
}

function ApprovalSection() {
  const receipts: [string, SellerRequest][] = [
    ["Sent once", sample.requests.sent],
    ["Suppressed in test mode", sample.requests.suppressed],
    ["Failed", sample.requests.failed],
    ["Approved, waiting on the provider", sample.requests.approved],
  ];
  const steps: [RequestStatus, boolean][] = [
    ["draft", false],
    ["approved", false],
    ["sent", false],
    ["draft", true],
    ["suppressed_test_mode", true],
    ["failed", false],
  ];

  return (
    <Section
      id="approval"
      title="Approval"
      lead="Nothing leaves without a named approver, and it leaves once. After approval the button is removed, not disabled, and a permanent receipt takes its place. Test mode is shown honestly: hatched, dashed, never a check mark, never the word Sent on its own."
    >
      <Specimen
        label="Draft, sending on"
        note="type a recipient, approve, confirm in the dialog. Gallery only: no email is sent from this page"
      >
        <ApprovalDemo testMode={false} signedIn />
      </Specimen>
      <Specimen label="Draft, test mode">
        <ApprovalDemo testMode signedIn />
      </Specimen>
      <Specimen label="Draft, nobody signed in" note="the button stays disabled and says why">
        <ApprovalDemo testMode={false} signedIn={false} />
      </Specimen>

      <Specimen label="ApprovalReceipt" note="the four outcomes">
        <div className="grid gap-4 lg:grid-cols-2">
          {receipts.map(([label, request]) => (
            <div key={label} className="flex flex-col gap-1">
              <p className="text-xs text-ink-muted">{label}</p>
              <ApprovalReceipt request={request} messageHref="#approval" onStartNewApproval={() => {}} />
            </div>
          ))}
        </div>
      </Specimen>

      <div className="grid gap-6 lg:grid-cols-2">
        <Specimen label="ApprovalSteps" note="the last step is named for what really happened">
          <div className="flex flex-col gap-2">
            {steps.map(([status, testMode]) => (
              <ApprovalSteps key={`${status}-${testMode}`} status={status} testMode={testMode} />
            ))}
          </div>
        </Specimen>
        <Specimen label="TestModeBanner">
          <TestModeBanner />
        </Specimen>
      </div>
    </Section>
  );
}

function SoundSection() {
  const { enabled, setEnabled, playCue } = useSound();
  const cues: [SoundCue, string][] = [
    ["run_finished", "Run finished"],
    ["request_sent", "Request approved and sent"],
    ["error", "Error that needs attention"],
  ];

  return (
    <Section
      id="sound"
      title="Sound"
      lead="Off by default. When a person turns it on there are three cues and no others. A cue always accompanies a visible, announced change; it is never the only signal. A suppressed send uses the run-finished cue, not the success cue."
    >
      <Specimen label="Setting" note="stored per browser; call useSound().playCue from pages">
        <div className="flex flex-col items-start gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              className="size-4 accent-ink"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            Sounds for finished runs and sends
          </label>
          <div className={row}>
            {cues.map(([cue, label]) => (
              <Button key={cue} size="sm" disabled={!enabled} onClick={() => playCue(cue)}>
                {label}
              </Button>
            ))}
          </div>
          <p className="text-xs text-ink-muted" role="status">
            {enabled ? "Sounds are on" : "Sounds are off. The buttons do nothing until you turn them on"}
          </p>
        </div>
      </Specimen>
    </Section>
  );
}

export function Gallery() {
  return (
    <div className="mx-auto flex w-full max-w-(--layout-content-max) flex-col lg:flex-row">
      <nav
        aria-label="Gallery sections"
        className="border-b border-line px-4 py-4 md:px-6 lg:sticky lg:top-0 lg:h-dvh lg:w-(--layout-sidebar) lg:shrink-0 lg:overflow-y-auto lg:border-r lg:border-b-0 lg:px-4 lg:py-6"
      >
        <p className="px-2 text-base font-medium text-ink">DealProof</p>
        <p className="px-2 pt-6 pb-2 text-xs text-ink-muted">Component gallery</p>
        <ul className="flex flex-wrap gap-x-1 gap-y-0.5 lg:flex-col">
          {SECTIONS.map(([id, label]) => (
            <li key={id}>
              <a
                href={`#${id}`}
                className="flex h-8 items-center rounded-md px-2 text-sm text-ink-secondary transition-colors hover:bg-surface-raised hover:text-ink"
              >
                {label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <main className="flex min-w-0 flex-1 flex-col gap-12 px-4 py-8 md:px-6 lg:px-8 lg:py-12">
        <header className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <h1 className="font-serif text-3xl text-ink">Component gallery</h1>
            <p className="max-w-(--layout-prose-max) text-base text-ink-secondary">
              Every DealProof component in every state. Pages are built from these parts and
              nothing else for the same job.
            </p>
          </div>
          <HatchedBlock role="note" innerClassName="text-dense">
            <span className="font-medium">Sample data. </span>
            Meridian Warehousing is an illustration, not a real company. Every source, date,
            figure and person on this page is invented to show density and wording.
          </HatchedBlock>
        </header>

        <Foundations />
        <Primitives />
        <SourceLineSection />
        <ClaimStatusSection />
        <DispositionSection />
        <EstimateSection />
        <IdentitySection />
        <CriteriaSection />
        <JudgmentSection />
        <LedgerSection />
        <RunSection />
        <CostSection />
        <DiffSection />
        <ApprovalSection />
        <SoundSection />

        <footer className="border-t border-line pt-4 text-xs text-ink-muted">
          <RuleBreakBlock title="How to read the red blocks" className="mb-4 max-w-(--layout-prose-max)">
            A red block like this one means the data broke a product rule: a fact with no source,
            a change with no cause, a Cannot verify with nothing that would settle it.
          </RuleBreakBlock>
          Gallery for reviewers and page builders. Not linked from the product.
        </footer>
      </main>
    </div>
  );
}
