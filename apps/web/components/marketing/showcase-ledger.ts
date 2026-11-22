/**
 * The home page's claim ledger, read from the committed showcase export: a real run of
 * the pipelines on a real company (content/showcase, see meta.json for its provenance).
 * The rows go through the same adapter as the case screens, so nothing here is written
 * by hand. Returns null when the export is missing a part the section needs; the page
 * then falls back to its labelled illustration.
 */
import caseJson from "@/content/showcase/case.json";
import metaJson from "@/content/showcase/meta.json";
import type { ClaimOut } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import type { Claim, ClaimStatusCounts } from "@/lib/types";
import { statusCounts, toClaim } from "@/components/case/adapt";

/**
 * The claims shown, by ledger number. Claim 4 is left out on purpose: meta.json records
 * it as a known wrong result (a country stored as an ISO code read as a mismatch), and
 * the home page does not repeat a result the export itself says is wrong.
 */
const SHOWN = [2, 8, 9, 6];

export interface ShowcaseLedger {
  company: string;
  /** "22 Nov 2026": the day the run finished. */
  ranOn: string;
  claims: Claim[];
  counts: ClaimStatusCounts;
  /** Every claim on the case, shown or not. */
  total: number;
}

function isClaimOut(value: unknown): value is ClaimOut {
  if (!value || typeof value !== "object") return false;
  const claim = value as Record<string, unknown>;
  return (
    typeof claim.id === "string" &&
    typeof claim.number === "number" &&
    typeof claim.original_text === "string" &&
    typeof claim.status === "string" &&
    typeof claim.reason === "string" &&
    Array.isArray(claim.evidence) &&
    typeof claim.stated_in === "object" &&
    claim.stated_in !== null
  );
}

export function showcaseLedger(): ShowcaseLedger | null {
  try {
    const meta = metaJson as Record<string, unknown>;
    const all = (caseJson as { claims?: unknown }).claims;
    const ranOn = formatDate(typeof meta.run_finished_at === "string" ? meta.run_finished_at : null);
    if (!Array.isArray(all) || !all.every(isClaimOut)) return null;
    if (typeof meta.company_name !== "string" || meta.claims_origin !== "public_website" || !ranOn) {
      return null;
    }
    const claims = SHOWN.flatMap((number) => all.filter((claim) => claim.number === number)).map(toClaim);
    if (claims.length < 3) return null;
    return { company: meta.company_name, ranOn, claims, counts: statusCounts(claims), total: all.length };
  } catch {
    return null;
  }
}
