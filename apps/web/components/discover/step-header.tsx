import { cn } from "@/lib/utils";

const STEPS = ["Thesis", "Criteria", "Shortlist"] as const;

/**
 * The page title and the quiet three-step header shared by every Discover state:
 * 1 Thesis, 2 Criteria, 3 Shortlist. The current step is said in words to a screen
 * reader; earlier steps are ink, later ones muted.
 */
export function DiscoverHeader({
  step,
  actions,
  children,
}: {
  /** 1, 2 or 3. Omit on the list of theses. */
  step?: 1 | 2 | 3;
  actions?: React.ReactNode;
  /** A line under the title, for example the thesis in the user's words. */
  children?: React.ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-2xl font-medium text-ink">Discover</h1>
          {children}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>

      {step ? (
        <ol className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line pb-3 text-sm">
          {STEPS.map((label, index) => {
            const number = index + 1;
            const current = number === step;
            return (
              <li
                key={label}
                aria-current={current ? "step" : undefined}
                className={cn(
                  "flex items-center gap-2",
                  current ? "font-medium text-ink" : number < step ? "text-ink-secondary" : "text-ink-muted",
                )}
              >
                {index > 0 ? <span aria-hidden className="h-px w-4 bg-line-strong sm:w-8" /> : null}
                <span className="font-mono text-xs">{number}</span>
                {label}
              </li>
            );
          })}
        </ol>
      ) : null}
    </header>
  );
}

/** The page frame: fills the content area, capped at 1440 and left-aligned. */
export function DiscoverPage({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex w-full max-w-360 animate-row-in flex-col gap-8 motion-reduce:animate-none",
        className,
      )}
      {...props}
    />
  );
}
