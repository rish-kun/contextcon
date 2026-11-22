import type { Metadata } from "next";
import { getPolicy, type PolicyOut } from "@/lib/api/client";
import {
  CLAIM_STATUS_LABEL,
  CLAIM_STATUS_MEANING,
  DISPOSITION_MEANING,
  RELIABILITY_LABEL,
} from "@/lib/labels";
import { CLAIM_STATUSES } from "@/lib/types";
import { CATEGORY_LABEL, COMPANY_TYPE_LABEL } from "@/components/case/adapt";
import { load } from "@/components/case/load";
import { ErrorState } from "@/components/ui/states";
import { DispositionStamp } from "@/components/dealproof/disposition-stamp";
import { SourceClassGlyph, StatusGlyph } from "@/components/dealproof/glyphs";
import { StatusMark } from "@/components/dealproof/status-mark";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const metadata: Metadata = { title: "Scoring policy" };

const SECTIONS = [
  ["fit", "Fit and assessable share"],
  ["dispositions", "Dispositions"],
  ["statuses", "Claim statuses"],
  ["required-checks", "Required checks"],
  ["adequate-sources", "Adequate sources"],
  ["settle-with", "What settles an open check"],
  ["other-rules", "Comparables and investors"],
  ["budgets", "Credit budgets"],
] as const;

function PolicySection({
  id,
  title,
  lead,
  children,
}: {
  id: (typeof SECTIONS)[number][0];
  title: string;
  lead: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="flex scroll-mt-24 flex-col gap-4 border-t border-line pt-8">
      <div className="flex max-w-2xl flex-col gap-1">
        <h2 className="text-xl font-medium text-ink">{title}</h2>
        <p className="text-sm text-ink-secondary">{lead}</p>
      </div>
      {children}
    </section>
  );
}

/** A rule exactly as the policy states it, in mono so it reads as the rule and not as prose. */
function Rule({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-ink-muted">{label}</span>
      <p className="rounded-md border border-line bg-surface px-3 py-2 font-mono text-xs leading-5 text-ink">
        {children}
      </p>
    </div>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 border-l border-line-strong pl-3">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="font-mono text-xl font-medium text-ink">{value}</dd>
    </div>
  );
}

function PolicyBody({ policy }: { policy: PolicyOut }) {
  const t = policy.thresholds;
  const types = ["startup", "established"] as const;

  return (
    <div className="flex flex-col gap-8">
      <PolicySection
        id="fit"
        title="Fit and assessable share"
        lead="Fit measures how well a company matches your criteria, counting only the criteria that could be assessed. The assessable share says how many could. The two are always shown together. Fit says nothing about returns."
      >
        <dl className="grid grid-cols-2 gap-4 sm:max-w-md">
          <Figure label="Weight of a must-have" value={String(policy.weights.must)} />
          <Figure label="Weight of a preference" value={String(policy.weights.preference)} />
        </dl>
        <div className="grid gap-4 lg:grid-cols-2">
          <Rule label="Fit">{policy.fit_formula}</Rule>
          <Rule label="Assessable share">{policy.assessable_formula}</Rule>
        </div>
      </PolicySection>

      <PolicySection
        id="dispositions"
        title="Dispositions"
        lead="The rules are tried in this order and the first one that matches decides. A disposition comes from these rules and the records on file, never from a model's confidence. Missing public evidence alone never produces Deprioritise."
      >
        <ol className="flex flex-col divide-y divide-line rounded-lg border border-line bg-surface">
          {[...policy.disposition_rules]
            .sort((a, b) => a.order - b.order)
            .map((rule) => (
              <li
                key={rule.order}
                className="grid gap-x-4 gap-y-2 px-4 py-3 sm:grid-cols-[1.5rem_12rem_minmax(0,1fr)] sm:items-start"
              >
                <span className="font-mono text-xs leading-8 text-ink-muted">{rule.order}</span>
                <DispositionStamp disposition={rule.disposition} className="justify-self-start" />
                <div className="flex flex-col gap-1 text-dense">
                  <p className="text-ink">{rule.rule}</p>
                  <p className="text-xs text-ink-secondary">{DISPOSITION_MEANING[rule.disposition]}</p>
                </div>
              </li>
            ))}
        </ol>
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Threshold</TableHead>
              <TableHead numeric>Value</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>Prioritise needs a fit of at least</TableCell>
              <TableCell numeric>{t.prioritise_fit_min}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Prioritise needs required checks settled of at least</TableCell>
              <TableCell numeric>{t.prioritise_sufficiency_min}%</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Deprioritise on poor fit applies below a fit of</TableCell>
              <TableCell numeric>{t.deprioritise_fit_below}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>and only when the assessable share is at least</TableCell>
              <TableCell numeric>{t.deprioritise_assessable_min}%</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Cannot assess applies when the assessable share is below</TableCell>
              <TableCell numeric>{t.cannot_assess_assessable_below}%</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </PolicySection>

      <PolicySection
        id="statuses"
        title="Claim statuses"
        lead="Every claim ends in one of six statuses. Cannot verify is a finished answer and names the document that would settle it. Not checked means the check did not run, and it is never counted as settled."
      >
        <ul className="flex flex-col divide-y divide-line rounded-lg border border-line bg-surface text-dense">
          {CLAIM_STATUSES.map((status) => (
            <li
              key={status}
              className="grid gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[14rem_minmax(0,1fr)] sm:items-center"
            >
              {status === "not_checked" ? (
                // On a claim this tag always carries its reason. Here it names the status only.
                <span className="hatch inline-flex h-6 items-center gap-1 justify-self-start rounded-sm border border-dashed border-not-checked-line px-2 text-xs font-medium text-not-checked">
                  <StatusGlyph status={status} />
                  {CLAIM_STATUS_LABEL[status]}
                </span>
              ) : (
                <StatusMark status={status} className="justify-self-start" />
              )}
              <span className="text-ink">{CLAIM_STATUS_MEANING[status]}</span>
            </li>
          ))}
        </ul>
      </PolicySection>

      <PolicySection
        id="required-checks"
        title="Required checks"
        lead="Which checks must be settled depends on the kind of company. Evidence sufficiency is the share of these checks that are settled."
      >
        <Rule label="How the company type is decided">{policy.company_type_rule}</Rule>
        <div className="grid gap-4 md:grid-cols-2">
          {types.map((type) => (
            <div key={type} className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4">
              <h3 className="flex items-baseline gap-2 text-sm font-medium text-ink">
                {COMPANY_TYPE_LABEL[type]}
                <span className="font-mono text-xs font-normal text-ink-muted">
                  {policy.required_checks[type].length}
                </span>
              </h3>
              <ul className="flex flex-col gap-1 text-dense text-ink">
                {policy.required_checks[type].map((category) => (
                  <li key={category}>{CATEGORY_LABEL[category]}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </PolicySection>

      <PolicySection
        id="adequate-sources"
        title="Adequate sources"
        lead="The right source for the right question. A claim counts as settled only when a source of a class listed for its category speaks to it."
      >
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Claim category</TableHead>
              <TableHead>Part of the claim</TableHead>
              <TableHead>Source classes that can settle it</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {policy.adequate_sources.map((row) => (
              <TableRow key={`${row.category}:${row.component}`}>
                <TableCell className="align-top">{CATEGORY_LABEL[row.category]}</TableCell>
                <TableCell className="align-top text-ink-secondary">
                  {row.component === "*" ? "Any part" : row.component.replaceAll("_", " ")}
                </TableCell>
                <TableCell>
                  <ul className="flex flex-wrap gap-x-4 gap-y-1">
                    {row.source_classes.map((sourceClass) => (
                      <li key={sourceClass} className="inline-flex items-center gap-1 text-ink">
                        <SourceClassGlyph reliability={sourceClass} className="text-ink-muted" />
                        {RELIABILITY_LABEL[sourceClass]}
                      </li>
                    ))}
                  </ul>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </PolicySection>

      <PolicySection
        id="settle-with"
        title="What settles an open check"
        lead="When a claim cannot be verified from public records, the policy names the document to ask the seller for. These feed the request list."
      >
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Claim category</TableHead>
              <TableHead>Document to request</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {policy.settle_with.map((row) => (
              <TableRow key={row.category}>
                <TableCell>{CATEGORY_LABEL[row.category]}</TableCell>
                <TableCell>{row.document}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </PolicySection>

      <PolicySection
        id="other-rules"
        title="Comparables and investors"
        lead="Comparable companies are for context and are not scored. The investor ranking describes past investments and does not predict whether an investor will invest."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <Rule label="A fair comparable">{policy.comparables_rule}</Rule>
          <Rule label="Investor ranking">{policy.investor_ranking_rule}</Rule>
        </div>
      </PolicySection>

      <PolicySection
        id="budgets"
        title="Credit budgets"
        lead="Each run stops at its budget. Checks that were not reached are marked Not checked, with the reason, and can be run later."
      >
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3 sm:max-w-2xl">
          <Figure label="A case" value={`${policy.budgets.case_credits} credits`} />
          <Figure label="A discovery search" value={`${policy.budgets.discover_credits} credits`} />
          <Figure label="An investor search" value={`${policy.budgets.investor_credits} credits`} />
        </dl>
      </PolicySection>
    </div>
  );
}

export default async function PolicyPage() {
  const policy = await load((init) => getPolicy(init));

  return (
    <div className="flex flex-col gap-8">
      <header className="flex max-w-3xl flex-col gap-2">
        <h1 className="text-2xl font-medium text-ink">Scoring policy</h1>
        <p className="text-sm text-ink-secondary">
          {policy.ok ? (
            <>
              <span className="font-mono text-xs text-ink">Policy {policy.data.policy_version}</span>
              {" · "}
            </>
          ) : null}
          The rules DealProof applies to every case. The same records under the same policy
          produce the same assessment every time.
        </p>
      </header>

      {policy.ok ? (
        <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_14rem]">
          <PolicyBody policy={policy.data} />
          <nav aria-label="On this page" className="hidden xl:block">
            <ul className="sticky top-24 flex flex-col gap-1 border-l border-line pl-4 text-dense">
              {SECTIONS.map(([id, label]) => (
                <li key={id}>
                  <a
                    href={`#${id}`}
                    className="flex min-h-8 items-center rounded-xs text-ink-secondary transition-colors hover:text-ink"
                  >
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      ) : (
        <ErrorState what="The scoring policy" status={policy.status} size="page" />
      )}
    </div>
  );
}
