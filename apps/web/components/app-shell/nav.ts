import {
  Activity,
  Building2,
  Columns3,
  GitCompareArrows,
  Inbox,
  Landmark,
  LayoutDashboard,
  ListFilter,
  Scale,
  Settings,
  type LucideIcon,
} from "lucide-react";

/** A place in the app. The nav holds places only; actions live in the "New" menu. */
export interface NavLink {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Path prefixes, besides `href` itself, that keep this item active. */
  also?: string[];
  /** Active only on the exact path. */
  exact?: boolean;
  /** Which live count sits at the right edge of the row. */
  count?: "approvals";
}

export interface NavGroup {
  label: string;
  items: NavLink[];
}

export const APP_HOME = "/app";

/**
 * One name per destination. The same word is the nav label, the breadcrumb, the page
 * title and the document title.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { label: "Overview", href: APP_HOME, icon: LayoutDashboard, exact: true },
      { label: "Pipeline", href: "/app/pipeline", icon: Columns3 },
      { label: "Approvals", href: "/app/approvals", icon: Inbox, count: "approvals" },
    ],
  },
  {
    label: "Research",
    items: [
      { label: "Companies", href: "/app/companies", icon: Building2, also: ["/app/cases"] },
      { label: "Screenings", href: "/app/discover", icon: ListFilter },
      { label: "Compare", href: "/app/compare", icon: GitCompareArrows },
      { label: "Signals", href: "/app/signals", icon: Activity },
      { label: "Investors", href: "/app/investors", icon: Landmark },
    ],
  },
];

export const FOOTER_NAV: NavLink[] = [
  { label: "Scoring policy", href: "/app/policy", icon: Scale },
  { label: "Settings", href: "/app/settings", icon: Settings },
];

const ALL = [...NAV_GROUPS.flatMap((group) => group.items), ...FOOTER_NAV];

export function isActive(item: NavLink, pathname: string): boolean {
  if (pathname === item.href) return true;
  if (!item.exact && pathname.startsWith(`${item.href}/`)) return true;
  return (item.also ?? []).some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export const caseHref = (id: string) => `/app/cases/${encodeURIComponent(id)}`;

/** Breadcrumb for the top bar, from the path alone. */
export function breadcrumb(
  pathname: string,
  caseName: (id: string) => string | null,
): { label: string; href?: string }[] {
  const [, , section, id] = pathname.split("/");
  if (section === "cases") {
    const companies = { label: "Companies", href: "/app/companies" };
    const name = id && id !== "new" ? caseName(decodeURIComponent(id)) : null;
    return name ? [companies, { label: name }] : id === "new" ? [companies, { label: "Verify a company" }] : [companies];
  }
  const place = ALL.find((item) => item.href === (section ? `/app/${section}` : APP_HOME));
  if (!place) return [{ label: "DealProof", href: APP_HOME }, { label: "Page not found" }];
  if (!id) return [{ label: place.label }];
  if (section === "discover") {
    return [{ label: place.label, href: place.href }, { label: id === "new" ? "New screening" : "Screening" }];
  }
  if (section === "investors") {
    return [{ label: place.label, href: place.href }, { label: id === "new" ? "Find investors" : "Investor search" }];
  }
  return [{ label: place.label, href: place.href }];
}
