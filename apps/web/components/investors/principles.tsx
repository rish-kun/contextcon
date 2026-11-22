import { cn } from "@/lib/utils";

const RULES = [
  "An investor appears only when a dated funding record connects them to a comparable company.",
  "The ranking describes past investments. It does not predict whether an investor will invest.",
  "DealProof does not collect investors' personal contact details.",
  "Any message to an investor waits for a person's approval.",
];

/** What the shortlist is and is not, stated before a search spends anything. */
export function Principles({ className }: { className?: string }) {
  return (
    <aside
      aria-labelledby="principles-heading"
      className={cn("flex flex-col gap-3 border-l border-line-strong pl-5", className)}
    >
      <h2 id="principles-heading" className="text-sm font-medium text-ink">
        How the shortlist is built
      </h2>
      <ol className="flex flex-col gap-3 text-dense text-ink-secondary">
        {RULES.map((rule, index) => (
          <li key={rule} className="grid grid-cols-[1.25rem_minmax(0,1fr)]">
            <span className="font-mono text-xs leading-5 text-ink-muted">{index + 1}</span>
            <span>{rule}</span>
          </li>
        ))}
      </ol>
    </aside>
  );
}
