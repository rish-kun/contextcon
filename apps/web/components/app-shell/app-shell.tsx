"use client";

import { usePathname, useRouter } from "next/navigation";
import { Dialog as SheetPrimitive } from "radix-ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Skeleton,
} from "@/components/ui";
import { ApiError, listCases, logout, me, type CaseSummary, type UserOut } from "@/lib/api/client";
import { CommandMenu } from "./command-menu";
import { ShellContext, type ShellContextValue } from "./shell-context";
import { SidebarNav } from "./sidebar-nav";
import { TopBar } from "./top-bar";
import { VerifyCompanyForm, describeError } from "./verify-company-form";

type Session =
  | { status: "loading" }
  | { status: "ready"; user: UserOut }
  | { status: "error"; message: string };

const SIDEBAR =
  "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line md:flex md:w-(--layout-sidebar-collapsed) lg:w-(--layout-sidebar)";
const MAIN = "px-4 py-6 md:px-6 lg:px-8 lg:py-8";

/** Sidebar and top bar around a content column that fills the viewport, capped at 1440. */
function Frame({
  sidebar,
  topBar,
  children,
}: {
  sidebar: React.ReactNode;
  topBar: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-dvh bg-paper">
      <aside className={SIDEBAR}>{sidebar}</aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {topBar}
        <main className={MAIN}>
          <div className="max-w-(--layout-content-max)">{children}</div>
        </main>
      </div>
    </div>
  );
}

function FrameSkeleton({ children }: { children?: React.ReactNode }) {
  return (
    <Frame
      sidebar={
        <div className="flex flex-col gap-3 p-4" aria-hidden>
          <span className="text-base font-medium text-ink md:max-lg:hidden">DealProof</span>
          <Skeleton className="mt-4 w-3/4 md:max-lg:w-full" />
          <Skeleton className="w-2/3 md:max-lg:w-full" />
          <Skeleton className="w-3/4 md:max-lg:w-full" />
        </div>
      }
      topBar={<div className="h-14 shrink-0 border-b border-line" />}
    >
      {children}
    </Frame>
  );
}

/**
 * The signed-in frame for every route under `/app`. It resolves the session first
 * (`GET /auth/me`): without one it sends the reader to `/login?next=…`, and pages inside
 * render only once the user is known.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<Session>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [recentCases, setRecentCases] = useState<CaseSummary[] | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    me().then(
      (user) => {
        if (!cancelled) setSession({ status: "ready", user });
      },
      (error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          const next = window.location.pathname + window.location.search;
          router.replace(`/login?next=${encodeURIComponent(next)}`);
          return;
        }
        setSession({
          status: "error",
          message: describeError(error, "Your session could not be checked"),
        });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt, router]);

  // The sidebar's recent cases and the command menu. Refreshed on navigation so a case
  // opened a moment ago is listed. A failure leaves the list empty; the dashboard reports
  // its own loading errors.
  const ready = session.status === "ready";
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    listCases().then(
      (cases) => {
        if (!cancelled) setRecentCases(cases);
      },
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, [ready, pathname]);

  useEffect(() => {
    if (!ready) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [ready]);

  const signOut = useCallback(() => {
    setSignOutError(null);
    logout().then(
      () => router.replace("/login"),
      (error: unknown) =>
        setSignOutError(`You are still signed in. ${describeError(error, "Sign out did not finish")}`),
    );
  }, [router]);

  const openVerify = useCallback(() => setVerifyOpen(true), []);
  const openCommandMenu = useCallback(() => setCommandOpen(true), []);

  const user = session.status === "ready" ? session.user : null;
  const context = useMemo<ShellContextValue | null>(
    () => (user ? { user, signOut, openVerify, openCommandMenu, recentCases } : null),
    [user, signOut, openVerify, openCommandMenu, recentCases],
  );

  if (session.status === "loading") {
    return (
      <FrameSkeleton>
        <div role="status" aria-label="Checking your session" className="flex flex-col gap-4">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="w-64" />
          <Skeleton className="mt-4 h-40 w-full rounded-lg" />
        </div>
      </FrameSkeleton>
    );
  }

  if (session.status === "error" || !context) {
    return (
      <FrameSkeleton>
        <div role="alert" className="flex max-w-xl flex-col items-start gap-3">
          <h1 className="text-2xl font-medium text-ink">DealProof could not open</h1>
          <p className="text-sm text-ink-secondary">
            {session.status === "error" ? session.message : null}
          </p>
          <Button
            onClick={() => {
              setSession({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          >
            Try again
          </Button>
        </div>
      </FrameSkeleton>
    );
  }

  return (
    <ShellContext.Provider value={context}>
      <a
        href="#content"
        className="sr-only rounded-md bg-ink px-3 py-2 text-sm text-ink-inverse focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-(--z-toast)"
      >
        Skip to content
      </a>
      <div className="flex min-h-dvh bg-paper">
        <aside className={SIDEBAR}>
          <SidebarNav rail />
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onOpenNav={() => setNavOpen(true)} />
          {signOutError ? (
            <p role="alert" className="border-b border-line bg-surface-raised px-4 py-2 text-dense text-ink md:px-6 lg:px-8">
              {signOutError}
            </p>
          ) : null}
          <main id="content" className={MAIN}>
            <div className="max-w-(--layout-content-max)">{children}</div>
          </main>
        </div>
      </div>

      <SheetPrimitive.Root open={navOpen} onOpenChange={setNavOpen}>
        <SheetPrimitive.Portal>
          <SheetPrimitive.Overlay className="fixed inset-0 z-(--z-dialog) animate-fade-in bg-scrim motion-reduce:animate-none md:hidden" />
          <SheetPrimitive.Content
            aria-describedby={undefined}
            className="fixed inset-y-0 left-0 z-(--z-dialog) flex w-72 max-w-[85vw] animate-fade-in flex-col border-r border-line bg-paper shadow-lg motion-reduce:animate-none md:hidden"
          >
            <SheetPrimitive.Title className="sr-only">Navigation</SheetPrimitive.Title>
            <SidebarNav onNavigate={() => setNavOpen(false)} />
          </SheetPrimitive.Content>
        </SheetPrimitive.Portal>
      </SheetPrimitive.Root>

      <Dialog open={verifyOpen} onOpenChange={setVerifyOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Verify a company</DialogTitle>
            <DialogDescription>
              Start verification for a company you already have in mind
            </DialogDescription>
          </DialogHeader>
          <VerifyCompanyForm autoFocus onCreated={() => setVerifyOpen(false)} />
        </DialogContent>
      </Dialog>

      <CommandMenu open={commandOpen} onOpenChange={setCommandOpen} />
    </ShellContext.Provider>
  );
}
