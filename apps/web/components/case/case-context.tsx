"use client";

/**
 * The shared case loader. `app/(app)/app/cases/[id]/layout.tsx` mounts one CaseProvider
 * per case; every tab under it reads the same `GET /cases/{id}` payload from here and
 * never fetches the case itself.
 *
 *   const detail = useCaseDetail();          // the loaded case, inside the case layout
 *   const { reload, mutate, verify, run, runActive, claimLive } = useCase();
 *
 * The provider also follows the latest run (server-sent events, with the client's
 * polling fallback), keeps that run's activity for the live views, and reloads the case
 * when a claim settles and when the run ends.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ApiError,
  type CaseDetail,
  type RunOut,
  type RunStreamEvent,
  getCase,
  checkClaim as checkClaimApi,
  getRun,
  isFixtureMode,
  startVerify,
} from "@/lib/api/client";
import { withStepSpend } from "@/lib/api/run-cost";
import { deriveView, type RunActivityView, visibleEvents } from "@/lib/run/activity-store";
import type { Activity } from "@/lib/run/types";
import { EMPTY_FEED, RunFeed, type RunFeedSnapshot } from "@/lib/run/use-run-activity";
import { isRunActive } from "./adapt";
import { claimLiveState, type ClaimLive } from "./claim-live-state";

export type CaseLoadState = "loading" | "ready" | "not_found" | "error";

export interface CaseContextValue {
  caseId: string;
  /** `/app/cases/{id}`: prefix for links between tabs. */
  basePath: string;
  /** The whole case from `GET /cases/{id}`. Null until loaded. */
  detail: CaseDetail | null;
  state: CaseLoadState;
  /** Why the case did not load, in words. */
  error: string | null;
  /** Fetch the case again and replace `detail`. */
  reload: () => Promise<void>;
  /** Apply a local change to `detail`, for example after `addClaim` returns the new claim. */
  mutate: (update: (detail: CaseDetail) => CaseDetail) => void;
  /** The latest run for this case, updated live while it is going. */
  run: RunOut | null;
  runActive: boolean;
  /** Why the last attempt to start a run failed. */
  runError: string | null;
  /** `POST /cases/{id}/verify`, then follow the run. Costs credits. */
  verify: () => Promise<void>;
  /** `POST /cases/{id}/claims/{claim_id}/check`: one claim only, then follow the run. */
  checkClaim: (claimId: string) => Promise<void>;
  /** Follow a run started elsewhere, for example by a document upload. */
  followRun: (run: RunOut) => void;
  /** True while a live run has not yet settled this claim. Drives the ledger's pending rows. */
  isClaimPending: (claimId: string) => boolean;
  /** The followed run's activity: events, pacing watermarks, pause state. */
  feed: RunFeedSnapshot;
  /** What that activity adds up to: sources, tally, findings by subject. */
  activity: RunActivityView;
  /** Freeze the paced regions of the live view. Events are still received. */
  setFeedPaused: (paused: boolean) => void;
  /**
   * Where one claim stands in the run being followed: waiting for identity, queued,
   * checking (with what is being done and what was read), or just settled. Null when the
   * run does not touch the claim, so the row shows its stored state.
   */
  claimLive: (claimId: string) => ClaimLive | null;
}

const CaseContext = createContext<CaseContextValue | null>(null);

export function useCase(): CaseContextValue {
  const value = useContext(CaseContext);
  if (!value) throw new Error("useCase must be used under the case layout (CaseProvider).");
  return value;
}

/**
 * The loaded case. Use it in any page under the case layout: the layout renders its
 * children only once the case is ready, so this never returns null there.
 */
export function useCaseDetail(): CaseDetail {
  const { detail } = useCase();
  if (!detail) throw new Error("useCaseDetail was called before the case loaded.");
  return detail;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "You are signed out. Sign in again to open this case.";
    return typeof error.detail === "string" ? error.detail : `The API answered ${error.status}.`;
  }
  return "The case could not be loaded. Check the connection and try again.";
}

const SETTLED_STEP = new Set(["done", "failed", "skipped_budget"]);

/** The claim id a step key checks (`checks.claim:<id>`, `…@2`, `…~1`), or null. */
function claimOfStep(key: string): string | null {
  const match = /(?:^|\.)claim:([^@~:]+)(?:[@~]\d+)?$/.exec(key);
  return match ? match[1] : null;
}

/** A finding that changes what `GET /cases/{id}` returns: a claim settling, identity, the assessment. */
function settlesSomething(event: Activity): boolean {
  if (event.kind !== "finding") return false;
  if (event.subject === "identity" || event.subject === "assessment") return true;
  return (
    event.subject === "claim" &&
    (event.items ?? []).some((item) => item.stage === "settled" || item.stage === "not_checked")
  );
}

function mergeEvent(current: RunOut | null, event: RunStreamEvent): RunOut | null {
  if (event.event === "activity" || event.event === "live") return current;
  if (event.event === "run") {
    // The stream's closing `run` event may carry no steps; keep the ones already seen.
    const steps = event.data.steps.length > 0 ? event.data.steps : (current?.steps ?? []);
    return withStepSpend({ ...event.data, steps });
  }
  if (!current) return current;
  const steps = current.steps.some((s) => s.id === event.data.id)
    ? current.steps.map((s) => (s.id === event.data.id ? event.data : s))
    : [...current.steps, event.data];
  return withStepSpend({ ...current, steps });
}

export function CaseProvider({
  caseId,
  initial,
  children,
}: {
  caseId: string;
  /** The case fetched on the server, when that worked. */
  initial: CaseDetail | null;
  children: React.ReactNode;
}) {
  const [detail, setDetail] = useState<CaseDetail | null>(initial);
  const [state, setState] = useState<CaseLoadState>(initial ? "ready" : "loading");
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<RunOut | null>(initial?.case.run ?? null);
  const [runActive, setRunActive] = useState(isRunActive(initial?.case.run));
  const [runError, setRunError] = useState<string | null>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const feedRef = useRef<RunFeed | null>(null);
  const [feed, setFeed] = useState<RunFeedSnapshot>(EMPTY_FEED);

  const reload = useCallback(async () => {
    try {
      const next = await getCase(caseId);
      setDetail(next);
      setState("ready");
      setError(null);
    } catch (cause) {
      setError(describe(cause));
      // A failed refresh keeps the case already on screen.
      setState((previous) =>
        previous === "ready"
          ? "ready"
          : cause instanceof ApiError && cause.status === 404
            ? "not_found"
            : "error",
      );
    }
  }, [caseId]);

  // A settling claim refreshes the case so its row has the full evidence list, at most
  // once every two seconds however many settle together.
  const reloadTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastReload = useRef(0);
  const softReload = useCallback(() => {
    if (reloadTimer.current) return;
    const wait = Math.max(0, lastReload.current + 2000 - Date.now());
    reloadTimer.current = setTimeout(() => {
      reloadTimer.current = null;
      lastReload.current = Date.now();
      void reload();
    }, wait);
  }, [reload]);

  const followRun = useCallback(
    (next: RunOut) => {
      stopRef.current?.();
      setRunError(null);
      setRunActive(isFixtureMode || isRunActive(next));
      // A fixture replay carries the recorded run's old timestamps; clock it from now and
      // replay it from the start. A real run keeps its snapshot (steps done so far, state),
      // so a reload mid-run shows exactly the progress it had.
      const startedAt = isFixtureMode ? new Date().toISOString() : next.created_at;
      const seed: RunOut = isFixtureMode
        ? { ...next, state: "running", steps: [], created_at: startedAt, finished_at: null }
        : withStepSpend(next);
      setRun(seed);
      const runFeed = new RunFeed(seed, {
        onEvent: (raw) => {
          const event: RunStreamEvent =
            isFixtureMode && raw.event === "run"
              ? {
                  event: "run",
                  data: {
                    ...raw.data,
                    created_at: startedAt,
                    finished_at: isRunActive(raw.data) ? null : new Date().toISOString(),
                  },
                }
              : raw;
          setRun((current) => mergeEvent(current, event));
          if (event.event === "step" && SETTLED_STEP.has(event.data.state)) {
            // A claim check or the identity step finishing changes what the case holds.
            if (/(^|\.)(claim|facts):|identity/.test(event.data.key)) softReload();
          }
          if (event.event === "activity" && settlesSomething(event.data)) softReload();
          if (event.event === "run" && !isRunActive(event.data)) {
            setRunActive(false);
            void reload();
          }
        },
      });
      feedRef.current = runFeed;
      setFeed(runFeed.getSnapshot());
      const off = runFeed.subscribe(setFeed);
      runFeed.start();
      stopRef.current = () => {
        off();
        runFeed.stop();
        stopRef.current = null;
      };
    },
    [reload, softReload],
  );

  const checkClaim = useCallback(
    async (claimId: string) => {
      setRunError(null);
      try {
        followRun(await checkClaimApi(caseId, claimId));
      } catch (cause) {
        setRunError(describe(cause));
      }
    },
    [caseId, followRun],
  );

  const verify = useCallback(async () => {
    setRunError(null);
    try {
      let next = await startVerify(caseId);
      if (isFixtureMode) {
        // Fixtures hand back the case's latest run; replay its full verify run instead,
        // so every claim is seen settling.
        const first = detail?.runs.find((r) => r.kind === "verify");
        if (first) next = await getRun(first.id);
      }
      followRun(next);
    } catch (cause) {
      setRunError(describe(cause));
    }
  }, [caseId, detail, followRun]);

  // First load when the server could not fetch the case; pick up a run already going.
  useEffect(() => {
    if (!initial) {
      void (async () => {
        try {
          const next = await getCase(caseId);
          setDetail(next);
          setState("ready");
          setRun(next.case.run);
          if (next.case.run && isRunActive(next.case.run)) followRun(next.case.run);
        } catch (cause) {
          setError(describe(cause));
          setState(cause instanceof ApiError && cause.status === 404 ? "not_found" : "error");
        }
      })();
    } else if (initial.case.run && isRunActive(initial.case.run)) {
      followRun(initial.case.run);
    }
    return () => {
      stopRef.current?.();
      if (reloadTimer.current) clearTimeout(reloadTimer.current);
    };
    // Runs once per case: `initial` is the server's snapshot for this mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const mutate = useCallback((update: (detail: CaseDetail) => CaseDetail) => {
    setDetail((current) => (current ? update(current) : current));
  }, []);

  const isClaimPending = useCallback(
    (claimId: string) => {
      if (!runActive || !run) return false;
      // A claim is pending while one of its own check steps is unsettled. Re-checks
      // carry a suffix: `checks.claim:<id>@2` (after a pick), `…~1` (deferred).
      const steps = run.steps.filter((s) => claimOfStep(s.key) === claimId);
      if (steps.length > 0) return steps.some((s) => !SETTLED_STEP.has(s.state));
      // A fixture replay starts with no steps; its verify run checks every claim.
      return isFixtureMode && (run.kind === "verify" || run.kind === "evaluate");
    },
    [run, runActive],
  );

  const shown = useMemo(() => visibleEvents(feed.events, feed.upto), [feed.events, feed.upto]);
  const activity = useMemo(() => deriveView(shown), [shown]);
  const setFeedPaused = useCallback((paused: boolean) => feedRef.current?.setPaused(paused), []);
  const claimLive = useCallback(
    (claimId: string) =>
      detail ? claimLiveState(claimId, { detail, run, runActive, view: activity, events: shown, settledSeq: feed.settled.findings }) : null,
    [detail, run, runActive, activity, shown, feed.settled.findings],
  );

  const value = useMemo<CaseContextValue>(
    () => ({
      caseId,
      basePath: `/app/cases/${encodeURIComponent(caseId)}`,
      detail,
      state,
      error,
      reload,
      mutate,
      run,
      runActive,
      runError,
      verify,
      checkClaim,
      followRun,
      isClaimPending,
      feed,
      activity,
      setFeedPaused,
      claimLive,
    }),
    [caseId, detail, state, error, reload, mutate, run, runActive, runError, verify, checkClaim, followRun, isClaimPending, feed, activity, setFeedPaused, claimLive],
  );

  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
}
