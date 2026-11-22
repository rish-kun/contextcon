"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

/** The rendered width of an element in px, so a chart draws at its real size. */
export function useElementWidth(element: HTMLElement | null, fallback: number): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry.contentRect.width);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return width;
}

/** True when the media query matches. Assumes a wide screen until the browser says otherwise. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => true,
  );
}
