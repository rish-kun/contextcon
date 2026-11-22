"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";

/**
 * Sound is opt-in and off by default. Three cues exist and no others:
 * a run finished, a request was approved and sent, an error that needs attention.
 * A suppressed (test mode) send uses the neutral run-finished cue, never the success cue.
 * A cue always accompanies a visible, announced state change. It is never the only signal.
 */
export type SoundCue = "run_finished" | "request_sent" | "error";

const CUE_TO_SOUND = {
  run_finished: "ready",
  request_sent: "success",
  error: "error",
} as const;

const STORAGE_KEY = "dealproof.sounds";
const CHANGE_EVENT = "dealproof:sounds";

function readEnabled(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "on";
  } catch {
    return false;
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

interface SoundContextValue {
  /** False until the user turns sounds on in settings. */
  enabled: boolean;
  setEnabled: (value: boolean) => void;
  /** Plays a cue when sounds are on. Does nothing otherwise. */
  playCue: (cue: SoundCue) => void;
}

const SoundContext = createContext<SoundContextValue>({
  enabled: false,
  setEnabled: () => {},
  playCue: () => {},
});

export function SoundProvider({ children }: { children: React.ReactNode }) {
  const enabled = useSyncExternalStore(subscribe, readEnabled, () => false);

  const setEnabled = useCallback((value: boolean) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, value ? "on" : "off");
    } catch {
      // Storage can be blocked. The setting then lasts for this page only.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  const playCue = useCallback(
    (cue: SoundCue) => {
      if (!enabled) return;
      // Loaded on first use, so nobody who leaves sounds off downloads the synth.
      void import("cuelume")
        .then(({ play }) => play(CUE_TO_SOUND[cue]))
        .catch(() => {});
    },
    [enabled],
  );

  const value = useMemo(
    () => ({ enabled, setEnabled, playCue }),
    [enabled, setEnabled, playCue],
  );

  return <SoundContext.Provider value={value}>{children}</SoundContext.Provider>;
}

export function useSound(): SoundContextValue {
  return useContext(SoundContext);
}
