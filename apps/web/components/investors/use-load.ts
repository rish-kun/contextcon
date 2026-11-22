"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Loads one thing by key and keeps the last good copy while a reload is in flight, so a
 * refresh never blanks the page. `loader` must be a stable function, such as a client
 * call imported from "@/lib/api/client".
 */
export function useLoad<T>(key: string, loader: (key: string) => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const [good, setGood] = useState<{ key: string; data: T } | null>(null);
  const [bad, setBad] = useState<{ key: string; attempt: number; error: unknown } | null>(null);

  useEffect(() => {
    let alive = true;
    loader(key).then(
      (data) => {
        if (alive) setGood({ key, data });
      },
      (error: unknown) => {
        if (alive) setBad({ key, attempt, error });
      },
    );
    return () => {
      alive = false;
    };
  }, [key, attempt, loader]);

  const data = good?.key === key ? good.data : null;
  const error = bad && bad.key === key && bad.attempt === attempt ? bad.error : null;
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  return { data, error, loading: data === null && error === null, reload };
}
