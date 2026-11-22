"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui";
import { cn } from "@/lib/utils";

/**
 * One dropdown filter in a toolbar, 32px. The first option is the unfiltered one and is
 * passed as `all`; choosing it reports null, so the caller can drop the key from the URL.
 */
export function FilterSelect({
  label,
  all,
  value,
  options,
  onChange,
  className,
}: {
  /** Names the control for a screen reader: "Filter by screening". */
  label: string;
  /** The words for no filter: "All screenings". */
  all: string;
  value: string | null;
  options: { value: string; label: string }[];
  onChange: (value: string | null) => void;
  className?: string;
}) {
  const known = value !== null && options.some((option) => option.value === value);
  return (
    <Select value={known ? value : "all"} onValueChange={(next) => onChange(next === "all" ? null : next)}>
      <SelectTrigger aria-label={label} className={cn("h-8 w-auto max-w-56 min-w-36 bg-surface text-dense", className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{all}</SelectItem>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
