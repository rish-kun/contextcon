import {
  BadgeCheck,
  Landmark,
  LayoutList,
  Scale,
  Search,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavLink {
  kind: "link";
  label: string;
  href: string;
  icon: LucideIcon;
  /** Path prefixes, besides `href` itself, that keep this item active. */
  also?: string[];
  /** Active only on the exact path. */
  exact?: boolean;
}

export interface NavAction {
  kind: "action";
  label: string;
  icon: LucideIcon;
  action: "verify";
}

export type NavItem = NavLink | NavAction;

export const APP_HOME = "/app";

export const PRIMARY_NAV: NavItem[] = [
  { kind: "link", label: "Dashboard", href: APP_HOME, icon: LayoutList, exact: true, also: ["/app/cases"] },
  { kind: "link", label: "New screening", href: "/app/discover", icon: Search },
  { kind: "action", label: "Verify a company", icon: BadgeCheck, action: "verify" },
  { kind: "link", label: "Investors", href: "/app/investors", icon: Landmark },
];

export const FOOTER_NAV: NavLink[] = [
  { kind: "link", label: "Scoring policy", href: "/app/policy", icon: Scale },
  { kind: "link", label: "Settings", href: "/app/settings", icon: Settings },
];

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
  switch (section) {
    case undefined:
    case "":
      return [{ label: "Dashboard" }];
    case "cases": {
      const name = id ? caseName(decodeURIComponent(id)) : null;
      return name ? [{ label: "Cases", href: APP_HOME }, { label: name }] : [{ label: "Cases", href: APP_HOME }];
    }
    case "discover":
      return [{ label: "New screening" }];
    case "investors":
      return [{ label: "Investors" }];
    case "policy":
      return [{ label: "Scoring policy" }];
    case "settings":
      return [{ label: "Settings" }];
    default:
      return [{ label: "DealProof" }];
  }
}
