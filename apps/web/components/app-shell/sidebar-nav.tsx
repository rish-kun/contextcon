"use client";

import { BadgeCheck, ChevronDown, Landmark, ListFilter, Plus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { DropdownMenu } from "radix-ui";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { APP_HOME, FOOTER_NAV, NAV_GROUPS, caseHref, isActive, type NavLink } from "./nav";
import { useShell } from "./shell-context";

const RECENT_LIMIT = 5;

const menuItem =
  "flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-sm text-ink-secondary outline-none data-highlighted:bg-surface-raised data-highlighted:text-ink";

/**
 * The navigation list, shared by the desktop sidebar and the mobile sheet. It lists
 * places, grouped, and has one action: the "New" menu. `rail` is the 56px icon-only form
 * used between the md and lg breakpoints: labels stay in the accessibility tree and show
 * as the native hint on hover.
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
  const { openVerify, recentCases, approvalsWaiting } = useShell();

  const row = cn(
    "flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-sm text-ink-secondary transition-colors hover:bg-surface-raised hover:text-ink",
    rail && "md:max-lg:justify-center md:max-lg:px-0",
  );
  const label = cn("truncate", rail && "md:max-lg:sr-only");
  const active = "bg-accent-tint text-accent hover:bg-accent-tint hover:text-accent";
  const railHidden = rail && "md:max-lg:hidden";

  const renderItem = (item: NavLink) => {
    const count = item.count === "approvals" ? approvalsWaiting : null;
    return (
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
          {count !== null && count > 0 ? (
            <span className={cn("ml-auto font-mono text-2xs text-accent", railHidden)}>
              {count}
              <span className="sr-only"> awaiting approval</span>
            </span>
          ) : null}
        </Link>
      </li>
    );
  };

  const recent = (recentCases ?? []).slice(0, RECENT_LIMIT);

  return (
    <nav aria-label="Main" className="flex min-h-0 flex-1 flex-col">
      <div className={cn("flex h-14 shrink-0 items-center px-4", rail && "md:max-lg:justify-center md:max-lg:px-0")}>
        <Link
          href={APP_HOME}
          className="rounded-xs text-base font-medium text-ink"
          onClick={onNavigate}
          aria-label="DealProof, overview"
        >
          <span className={cn(railHidden)}>DealProof</span>
          {rail ? <span className="hidden md:max-lg:inline">DP</span> : null}
        </Link>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            title={rail ? "New" : undefined}
            className={cn(
              "press flex h-8 w-full shrink-0 items-center gap-2 rounded-md border border-line-strong bg-surface px-2 text-sm font-medium text-ink shadow-xs transition-colors hover:bg-surface-raised data-[state=open]:bg-surface-raised",
              rail && "md:max-lg:justify-center md:max-lg:px-0",
            )}
          >
            <Icon icon={Plus} className="shrink-0" />
            <span className={label}>New</span>
            <Icon icon={ChevronDown} className={cn("ml-auto shrink-0 text-ink-muted", railHidden)} />
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="start"
              sideOffset={6}
              collisionPadding={8}
              className="z-(--z-dialog) w-60 animate-overlay-in rounded-lg border border-line bg-surface p-1 shadow-md motion-reduce:animate-none"
            >
              <DropdownMenu.Item asChild className={menuItem}>
                <Link href="/app/discover/new" onClick={onNavigate}>
                  <Icon icon={ListFilter} />
                  New screening
                </Link>
              </DropdownMenu.Item>
              <DropdownMenu.Item
                className={menuItem}
                onSelect={() => {
                  onNavigate?.();
                  openVerify();
                }}
              >
                <Icon icon={BadgeCheck} />
                Verify a company
              </DropdownMenu.Item>
              <DropdownMenu.Item asChild className={menuItem}>
                <Link href="/app/investors/new" onClick={onNavigate}>
                  <Icon icon={Landmark} />
                  Find investors
                </Link>
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        {NAV_GROUPS.map((group, index) => (
          <div key={group.label}>
            <p className={cn("mb-2 px-2 text-xs text-ink-muted", index === 0 ? "mt-4" : "mt-6", railHidden)}>
              {group.label}
            </p>
            {rail ? <div aria-hidden className="mx-2 my-2 hidden border-t border-line md:max-lg:block" /> : null}
            <ul className="flex flex-col gap-0.5">{group.items.map(renderItem)}</ul>
          </div>
        ))}

        {recent.length > 0 ? (
          <div className={cn(railHidden)}>
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
                      className={cn(row, "pl-8", current && "text-ink")}
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
