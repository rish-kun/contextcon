/**
 * The public read-only showcase's API paths. While a `/showcase/**` page is open, the
 * browser's API client sends these reads to `/public/showcase/*` (which serve only the
 * records flagged `is_showcase`) and refuses every other call. Kept free of imports so
 * `node --test` can run `showcase-paths.test.mjs` directly.
 */

const READS: [RegExp, (m: RegExpExecArray) => string][] = [
  [/^\/cases\/[^/?]+(\?.*)?$/, () => "/public/showcase/case"],
  [/^\/cases\/[^/]+\/assessments(\?.*)?$/, () => "/public/showcase/case/assessments"],
  [/^\/runs\/([^/?]+)(\?.*)?$/, (m) => `/public/showcase/runs/${m[1]}`],
  [/^\/runs\/([^/]+)\/activity(\?.*)?$/, (m) => `/public/showcase/runs/${m[1]}/activity${m[2] ?? ""}`],
  [/^\/theses\/[^/?]+(\?.*)?$/, () => "/public/showcase/discovery"],
  [/^\/investor-searches\/[^/?]+(\?.*)?$/, () => "/public/showcase/investors"],
  [/^\/(policy|public\/showcase.*)$/, (m) => m[0]],
];

/** The public path for a showcase read, or null when the call is not allowed there. */
export function showcaseReadPath(method: string, path: string): string | null {
  if (method !== "GET") return null;
  for (const [pattern, to] of READS) {
    const m = pattern.exec(path);
    if (m) return to(m);
  }
  return null;
}
