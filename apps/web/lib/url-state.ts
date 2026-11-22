"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/**
 * Filters and selections kept in the query string, so a view can be linked and shared.
 * `set` replaces the entry in history (a filter is not a page), and drops a key when its
 * value is empty or null. The component must sit under a `<Suspense>`.
 */
export function useUrlState(): [URLSearchParams, (patch: Record<string, string | null>) => void, () => void] {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const set = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      }
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  const reset = useCallback(() => router.replace(pathname, { scroll: false }), [pathname, router]);

  return [params, set, reset];
}
