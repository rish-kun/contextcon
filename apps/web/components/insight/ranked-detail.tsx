"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";
import { useMediaQuery } from "./hooks";

/**
 * A ranked list with the selected entry's detail beside it. From 1024px the list is the
 * left column and the detail stays in view on the right while the list scrolls. Below
 * that the detail opens in place under the selected row, so a phone never has to scroll
 * past the whole list to read it.
 *
 * The order of `items` is the ranking; this layout adds no score of its own.
 */
export function RankedDetail<T>({
  items,
  getId,
  selectedId,
  onSelect,
  renderRow,
  renderDetail,
  label,
  listHeader,
  className,
}: {
  items: T[];
  getId: (item: T) => string;
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** The row's content. It sits inside a button, so it must not contain controls. */
  renderRow: (item: T, selected: boolean) => React.ReactNode;
  renderDetail: (item: T) => React.ReactNode;
  /** Names the list: "Investors, ranked by comparable investments found". */
  label: string;
  /** A band above the list, for column headings or a shared axis. */
  listHeader?: React.ReactNode;
  className?: string;
}) {
  const wide = useMediaQuery("(min-width: 64rem)");
  const panelId = useId();
  const selected = items.find((item) => getId(item) === selectedId) ?? items[0] ?? null;
  const currentId = selected ? getId(selected) : null;

  return (
    <div className={cn("grid items-start gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]", className)}>
      <div className="overflow-hidden rounded-lg border border-line bg-surface">
        {listHeader ? (
          <div className="border-b border-line bg-surface-sunken px-4 py-2">{listHeader}</div>
        ) : null}
        <ol aria-label={label} className="divide-y divide-line">
          {items.map((item) => {
            const id = getId(item);
            const isSelected = id === currentId;
            return (
              <li key={id} id={id} className="scroll-mt-24">
                <button
                  type="button"
                  aria-expanded={isSelected}
                  aria-controls={isSelected ? panelId : undefined}
                  onClick={() => onSelect(id)}
                  className={cn(
                    "focus-inset block w-full px-4 py-3 text-left transition-colors",
                    isSelected ? "selected-bar bg-accent-tint" : "hover:bg-surface-raised",
                  )}
                >
                  {renderRow(item, isSelected)}
                </button>
                {isSelected && !wide ? (
                  <div id={panelId} className="animate-fade-in border-t border-line bg-surface p-4 motion-reduce:animate-none">
                    {renderDetail(item)}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      </div>

      {wide && selected ? (
        <section
          id={panelId}
          aria-live="polite"
          className="sticky top-20 hidden max-h-[calc(100dvh-6rem)] overflow-y-auto rounded-lg border border-line bg-surface p-5 lg:block"
        >
          {renderDetail(selected)}
        </section>
      ) : null}
    </div>
  );
}
