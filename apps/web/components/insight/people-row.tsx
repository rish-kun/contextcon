"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/** One sourced statement about a person: a title or a dated role. */
export interface PersonFact {
  text: string;
  /** The source chip. Required: a role with no source is not shown. */
  source: React.ReactNode;
}

export interface PersonCard {
  id: string;
  name: string;
  /** Current title at the company. */
  role?: PersonFact | null;
  /** Dated career facts, in the order the record gives them: "Head of operations, 2009–2014". */
  history: PersonFact[];
}

const VISIBLE_FACTS = 3;

function initials(name: string): string {
  const words = name.replace(/\(.*?\)/g, "").trim().split(/\s+/).filter(Boolean);
  return ((words[0]?.[0] ?? "") + (words.length > 1 ? (words[words.length - 1][0] ?? "") : "")).toUpperCase();
}

function Person({ person }: { person: PersonCard }) {
  const [showAll, setShowAll] = useState(false);
  const facts = showAll ? person.history : person.history.slice(0, VISIBLE_FACTS);
  const extra = person.history.length - VISIBLE_FACTS;

  return (
    <li className="flex min-w-0 gap-3 rounded-lg border border-line bg-surface p-4">
      <span
        aria-hidden
        className="flex size-9 shrink-0 items-center justify-center rounded-full bg-surface-sunken font-mono text-xs text-ink-secondary"
      >
        {initials(person.name)}
      </span>
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex min-w-0 flex-col items-start gap-1">
          <p className="text-sm font-medium text-ink">{person.name}</p>
          {person.role ? (
            <>
              <p className="text-dense text-ink">{person.role.text}</p>
              {person.role.source}
            </>
          ) : (
            <p className="text-dense text-ink-muted">Current title not returned</p>
          )}
        </div>
        {person.history.length > 0 ? (
          <ul className="flex flex-col gap-2 border-t border-line pt-2">
            {facts.map((fact) => (
              <li key={fact.text} className="flex min-w-0 flex-col items-start gap-1">
                <span className="text-dense text-ink-secondary">{fact.text}</span>
                {fact.source}
              </li>
            ))}
          </ul>
        ) : (
          <p className="border-t border-line pt-2 text-xs text-ink-muted">No dated career record attached</p>
        )}
        {extra > 0 ? (
          <button
            type="button"
            aria-expanded={showAll}
            onClick={() => setShowAll((value) => !value)}
            className="self-start rounded-xs text-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
          >
            {showAll ? "Show fewer" : `+ ${extra} more dated roles`}
          </button>
        ) : null}
      </div>
    </li>
  );
}

/**
 * Founders and leaders side by side: name, current title and the dated roles the record
 * holds, each with its source. It reports roles and dates and makes no judgment of the
 * person. A career record is attached on the company's identifier plus the name; a
 * name-only match is never listed here, and the note under the row says so.
 */
export function PeopleRow({ people, className }: { people: PersonCard[]; className?: string }) {
  if (people.length === 0) {
    return (
      <p className={cn("text-dense text-ink-muted", className)}>
        No leadership record could be attached on company identifier and name
      </p>
    );
  }
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {people.map((person) => (
          <Person key={person.id} person={person} />
        ))}
      </ul>
      <p className="text-xs text-ink-secondary">
        Attached on company identifier and name. A match on the name alone is not shown as a record
      </p>
    </div>
  );
}
