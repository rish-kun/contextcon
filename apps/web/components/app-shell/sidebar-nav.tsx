"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { APP_HOME, FOOTER_NAV, PRIMARY_NAV, caseHref, isActive, type NavItem } from "./nav";
import { useShell } from "./shell-context";

const RECENT_LIMIT = 5;

/**
 * The navigation list, shared by the desktop sidebar and the mobile sheet.
 * `rail` is the 56px icon-only form used between the md and lg breakpoints: labels stay
 * in the accessibility tree and show as the native hint on hover.
 */
export function SidebarNav({
  rail = false,
  onNavigate,
}: {
  rail?: boolean;
  /** Called after any item is chosen, so the mobile sheet can close. */
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const { openVerify, recentCases } = useShell();

  const row = cn(
    "flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-sm text-ink-secondary transition-colors hover:bg-surface-raised hover:text-ink",
    rail && "md:max-lg:justify-center md:max-lg:px-0",
  );
  const label = cn("truncate", rail && "md:max-lg:sr-only");
  const active = "bg-accent-tint text-accent hover:bg-accent-tint hover:text-accent";

  const renderItem = (item: NavItem) =>
    item.kind === "link" ? (
      <li key={item.label}>
        <Link
          href={item.href}
          title={rail ? item.label : undefined}
          aria-current={isActive(item, pathname) ? "page" : undefined}
          className={cn(row, isActive(item, pathname) && active)}
          onClick={onNavigate}
        >
          <Icon icon={item.icon} className="shrink-0" />
          <span className={label}>{item.label}</span>
        </Link>
      </li>
    ) : (
      <li key={item.label}>
        <button
          type="button"
          title={rail ? item.label : undefined}
          className={row}
          onClick={() => {
            onNavigate?.();
            openVerify();
          }}
        >
          <Icon icon={item.icon} className="shrink-0" />
          <span className={label}>{item.label}</span>
        </button>
      </li>
    );

  const recent = (recentCases ?? []).slice(0, RECENT_LIMIT);

  return (
    <nav aria-label="Main" className="flex min-h-0 flex-1 flex-col">
      <div className={cn("flex h-14 shrink-0 items-center px-4", rail && "md:max-lg:justify-center md:max-lg:px-0")}>
        <Link
          href={APP_HOME}
          className="rounded-xs text-base font-medium text-ink"
          onClick={onNavigate}
          aria-label="DealProof, dashboard"
        >
          <span className={cn(rail && "md:max-lg:hidden")}>DealProof</span>
          {rail ? <span className="hidden md:max-lg:inline">DP</span> : null}
        </Link>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2">
        <ul className="flex flex-col gap-0.5">{PRIMARY_NAV.map(renderItem)}</ul>

        {recent.length > 0 ? (
          <div className={cn(rail && "md:max-lg:hidden")}>
            <p className="mt-6 mb-2 px-2 text-xs text-ink-muted">Recent</p>
            <ul className="flex flex-col gap-0.5">
              {recent.map((item) => {
                const href = caseHref(item.id);
                const current = pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <li key={item.id}>
                    <Link
                      href={href}
                      aria-current={current ? "page" : undefined}
                      className={cn(row, current && active)}
                      onClick={onNavigate}
                    >
                      <span className="truncate">{item.name}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}

        <ul className="mt-auto flex flex-col gap-0.5 border-t border-line pt-2">
          {FOOTER_NAV.map(renderItem)}
        </ul>
      </div>
    </nav>
  );
}
