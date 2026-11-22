/**
 * Tells browser-side caches that the signed-in account may have changed.
 *
 * Signing out and signing in are client navigations, so module state survives them: a
 * cache filled for one account is still in memory when the next account arrives in the
 * same tab. Anything that keeps account data in a module registers here and drops it.
 */
const listeners = new Set<() => void>();

/** Run `listener` whenever a sign-in, sign-out or sign-up is attempted. Returns an unsubscribe. */
export function onSessionChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Called around every call that can change who is signed in. */
export function sessionChanged(): void {
  for (const listener of listeners) listener();
}
