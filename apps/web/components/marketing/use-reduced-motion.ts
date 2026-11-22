"use client";

import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void) {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/**
 * The reader's reduced-motion preference, safe to branch markup on.
 *
 * It is `null` on the server and for the whole of hydration, so the first client render
 * matches the server whatever the preference is. React then re-renders with the real
 * value. Treat `null` as "not known yet": draw the server's markup and start nothing.
 */
export function useReducedMotionPreference(): boolean | null {
  return useSyncExternalStore<boolean | null>(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => null,
  );
}
