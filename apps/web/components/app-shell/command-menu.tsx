"use client";

import { useRouter } from "next/navigation";
import { useId, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle, Kbd } from "@/components/ui";
import { cn } from "@/lib/utils";
import { FOOTER_NAV, NAV_GROUPS, caseHref } from "./nav";
import { useShell } from "./shell-context";

interface Command {
  id: string;
  group: "Actions" | "Recent cases" | "Navigation";
  label: string;
  run: () => void;
}

const GROUPS: Command["group"][] = ["Actions", "Recent cases", "Navigation"];
const RECENT_LIMIT = 8;

/** ⌘K: jump to a case or start something. A filtered list, arrow keys and Enter. */
export function CommandMenu({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent hideClose className="max-w-xl gap-0 self-start p-0 sm:mt-24">
        <DialogTitle className="sr-only">Command menu</DialogTitle>
        <DialogDescription className="sr-only">
          Type to filter, use the arrow keys to move and Enter to choose
        </DialogDescription>
        {/* Mounted per opening, so the query and the selection start fresh each time. */}
        <CommandList close={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function CommandList({ close }: { close: () => void }) {
  const router = useRouter();
  const listId = useId();
  const { openVerify, recentCases } = useShell();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);

  const commands = useMemo<Command[]>(() => {
    const go = (href: string) => () => router.push(href);
    return [
      { id: "new-thesis", group: "Actions", label: "New screening", run: go("/app/discover/new") },
      { id: "new-case", group: "Actions", label: "Verify a company", run: openVerify },
      { id: "find-investors", group: "Actions", label: "Find investors", run: go("/app/investors/new") },
      { id: "policy", group: "Actions", label: "View scoring policy", run: go("/app/policy") },
      ...(recentCases ?? []).slice(0, RECENT_LIMIT).map(
        (item): Command => ({
          id: `case-${item.id}`,
          group: "Recent cases",
          label: item.name,
          run: go(caseHref(item.id)),
        }),
      ),
      ...[...NAV_GROUPS.flatMap((group) => group.items), ...FOOTER_NAV].map(
        (item): Command => ({
          id: `nav-${item.href}`,
          group: "Navigation",
          label: item.label,
          run: go(item.href),
        }),
      ),
    ];
  }, [router, openVerify, recentCases]);

  const needle = query.trim().toLowerCase();
  const matches = needle
    ? commands.filter((command) => command.label.toLowerCase().includes(needle))
    : commands;
  const selected = Math.min(index, Math.max(0, matches.length - 1));

  function choose(command: Command) {
    close();
    command.run();
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setIndex((selected + 1) % Math.max(1, matches.length));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setIndex((selected - 1 + matches.length) % Math.max(1, matches.length));
    } else if (event.key === "Enter" && matches[selected]) {
      event.preventDefault();
      choose(matches[selected]);
    }
  }

  return (
    <>
      <div className="flex items-center gap-3 border-b border-line px-4">
        <input
          role="combobox"
          aria-expanded
          aria-controls={listId}
          aria-activedescendant={matches[selected] ? `${listId}-${matches[selected].id}` : undefined}
          aria-label="Jump to a case, a place or an action"
          placeholder="Jump to a case, a place or an action"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setIndex(0);
          }}
          onKeyDown={onKeyDown}
          autoFocus
          className="h-12 min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted"
        />
        <Kbd>Esc</Kbd>
      </div>
      <div id={listId} role="listbox" aria-label="Commands" className="max-h-80 overflow-y-auto p-2">
        {matches.length === 0 ? (
          <p className="px-2 py-6 text-center text-dense text-ink-secondary">
            No matching cases or actions
          </p>
        ) : (
          GROUPS.map((group) => {
            const items = matches.filter((command) => command.group === group);
            if (items.length === 0) return null;
            return (
              <div key={group} role="group" aria-label={group} className="pb-2 last:pb-0">
                <p className="px-2 pt-2 pb-1 text-xs text-ink-muted">{group}</p>
                {items.map((command) => {
                  const isSelected = matches[selected]?.id === command.id;
                  return (
                    <div
                      key={command.id}
                      id={`${listId}-${command.id}`}
                      role="option"
                      aria-selected={isSelected}
                      onPointerMove={() => setIndex(matches.indexOf(command))}
                      onClick={() => choose(command)}
                      className={cn(
                        "flex h-9 cursor-default items-center rounded-md px-2 text-sm text-ink-secondary",
                        isSelected && "bg-accent-tint text-accent",
                      )}
                    >
                      <span className="truncate">{command.label}</span>
                    </div>
                  );
                })}
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
