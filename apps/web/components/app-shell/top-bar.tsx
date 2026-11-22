"use client";

import { ChevronDown, LogOut, Menu, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { DropdownMenu } from "radix-ui";
import { Icon, Kbd } from "@/components/ui";
import { breadcrumb } from "./nav";
import { useShell } from "./shell-context";

const menuItem =
  "flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-sm text-ink-secondary outline-none data-highlighted:bg-surface-raised data-highlighted:text-ink";

/** 56px bar: where you are on the left; the command menu and the signed-in user on the right. */
export function TopBar({ onOpenNav }: { onOpenNav: () => void }) {
  const pathname = usePathname();
  const { user, signOut, openCommandMenu, recentCases } = useShell();
  const crumbs = breadcrumb(
    pathname,
    (id) => recentCases?.find((item) => item.id === id)?.name ?? null,
  );

  return (
    <header className="sticky top-0 z-(--z-sticky) flex h-14 shrink-0 items-center gap-3 border-b border-line bg-paper px-4 md:px-6 lg:px-8">
      <button
        type="button"
        aria-label="Open navigation"
        onClick={onOpenNav}
        className="-ml-2 inline-flex size-9 shrink-0 items-center justify-center rounded-md text-ink transition-colors hover:bg-surface-raised md:hidden"
      >
        <Icon icon={Menu} />
      </button>

      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex min-w-0 items-center gap-2 text-sm">
          {crumbs.map((crumb, index) => {
            const last = index === crumbs.length - 1;
            return (
              <li key={crumb.label} className="flex min-w-0 items-center gap-2">
                {index > 0 ? <span aria-hidden className="text-ink-muted">/</span> : null}
                {crumb.href && !last ? (
                  <Link href={crumb.href} className="rounded-xs text-ink-secondary transition-colors hover:text-ink">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current={last ? "page" : undefined} className="truncate text-ink">
                    {crumb.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      <button
        type="button"
        aria-label="Open command menu"
        onClick={openCommandMenu}
        className="hidden h-8 shrink-0 items-center gap-6 rounded-md border border-line-strong bg-surface pr-1.5 pl-3 text-dense text-ink-muted transition-colors hover:border-ink-muted sm:inline-flex"
      >
        Jump to
        <Kbd>⌘K</Kbd>
      </button>

      <DropdownMenu.Root>
        <DropdownMenu.Trigger className="inline-flex h-8 max-w-48 shrink-0 items-center gap-1 rounded-md px-2 text-sm text-ink transition-colors hover:bg-surface-raised data-[state=open]:bg-surface-raised">
          <span className="truncate">{user.display_name}</span>
          <Icon icon={ChevronDown} className="shrink-0 text-ink-muted" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={6}
            collisionPadding={8}
            className="z-(--z-drawer) w-60 animate-overlay-in rounded-lg border border-line bg-surface p-1 shadow-md motion-reduce:animate-none"
          >
            <div className="border-b border-line px-2 pt-1 pb-2">
              <p className="truncate text-sm text-ink">{user.display_name}</p>
              <p className="truncate font-mono text-2xs text-ink-muted">{user.email}</p>
            </div>
            <div className="pt-1">
              <DropdownMenu.Item asChild className={menuItem}>
                <Link href="/app/settings">
                  <Icon icon={Settings} />
                  Settings
                </Link>
              </DropdownMenu.Item>
              <DropdownMenu.Item className={menuItem} onSelect={signOut}>
                <Icon icon={LogOut} />
                Sign out
              </DropdownMenu.Item>
            </div>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </header>
  );
}
