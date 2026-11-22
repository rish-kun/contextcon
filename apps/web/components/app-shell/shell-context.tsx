"use client";

import { createContext, useContext } from "react";
import type { CaseSummary, UserOut } from "@/lib/api/client";

export interface ShellContextValue {
  /** The signed-in user. Pages inside the shell render only once this is known. */
  user: UserOut;
  /** Ends the session and returns to the login page. */
  signOut: () => void;
  /** Opens the "Verify a company" dialog from anywhere in the app. */
  openVerify: () => void;
  /** Opens the command menu. */
  openCommandMenu: () => void;
  /** Cases for the sidebar and the command menu. Null until the first load finishes. */
  recentCases: CaseSummary[] | null;
}

export const ShellContext = createContext<ShellContextValue | null>(null);

/** Shell state for any page rendered inside `app/(app)/layout.tsx`. */
export function useShell(): ShellContextValue {
  const value = useContext(ShellContext);
  if (!value) throw new Error("useShell must be used inside the app shell");
  return value;
}

/** The signed-in user, whose name is recorded on approvals. */
export function useSessionUser(): UserOut {
  return useShell().user;
}
