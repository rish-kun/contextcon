"use client";

/**
 * The shared case loader. `app/(app)/app/cases/[id]/layout.tsx` mounts one CaseProvider
 * per case; every tab under it reads the same `GET /cases/{id}` payload from here and
 * never fetches the case itself.
 *
 *   const detail = useCaseDetail();          // the loaded case, inside the case layout
 *   const { reload, mutate, verify, run, runActive, isClaimPending } = useCase();
 *
 * The provider also follows the latest run (server-sent events, with the client's
 * polling fallback) and reloads the case when the run ends.
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
  getRun,
  isFixtureMode,
  startVerify,
  subscribeRun,
} from "@/lib/api/client";
import { isRunActive } from "./adapt";

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
  /** Follow a run started elsewhere, for example by a document upload. */
  followRun: (run: RunOut) => void;
  /** True while a live run has not yet settled this claim. Drives the ledger's pending rows. */
  isClaimPending: (claimId: string) => boolean;
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

function mergeEvent(current: RunOut | null, event: RunStreamEvent): RunOut | null {
  if (event.event === "activity" || event.event === "live") return current;
  if (event.event === "run") {
    // The stream's closing `run` event may carry no steps; keep the ones already seen.
    const steps = event.data.steps.length > 0 ? event.data.steps : (current?.steps ?? []);
    return { ...event.data, steps };
  }
  if (!current) return current;
  const steps = current.steps.some((s) => s.id === event.data.id)
    ? current.steps.map((s) => (s.id === event.data.id ? event.data : s))
    : [...current.steps, event.data];
  return { ...current, steps };
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

  const followRun = useCallback(
    (next: RunOut) => {
      stopRef.current?.();
      setRunError(null);
      setRunActive(true);
      // A fixture replay carries the recorded run's old timestamps; clock it from now.
      const startedAt = isFixtureMode ? new Date().toISOString() : next.created_at;
      setRun({ ...next, state: "running", steps: [], created_at: startedAt, finished_at: null });
      stopRef.current = subscribeRun(next.id, (raw) => {
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
        if (event.event === "run" && !isRunActive(event.data)) {
          setRunActive(false);
          stopRef.current = null;
          void reload();
        }
      });
    },
    [reload],
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
    return () => stopRef.current?.();
    // Runs once per case: `initial` is the server's snapshot for this mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const mutate = useCallback((update: (detail: CaseDetail) => CaseDetail) => {
    setDetail((current) => (current ? update(current) : current));
  }, []);

  const isClaimPending = useCallback(
    (claimId: string) => {
      if (!runActive || !run) return false;
      const step = run.steps.find((s) => s.key.endsWith(`:${claimId}`));
      if (step) return !SETTLED_STEP.has(step.state);
      // A verify run checks every claim; a recheck touches only the claims it names.
      return run.kind === "verify" || run.kind === "evaluate";
    },
    [run, runActive],
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
      followRun,
      isClaimPending,
    }),
    [caseId, detail, state, error, reload, mutate, run, runActive, runError, verify, followRun, isClaimPending],
  );

  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
}
