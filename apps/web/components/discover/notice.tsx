import { cn } from "@/lib/utils";

/** A failed request, said in words with what the user can do next. */
export function ErrorNotice({
  title,
  children,
  actions,
  className,
}: {
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col gap-2 rounded-md border border-contradicted-line bg-contradicted-tint px-4 py-3 text-dense text-contradicted",
        className,
      )}
    >
      <p className="font-medium">{title}</p>
      {children ? <p>{children}</p> : null}
      {actions ? <div className="flex flex-wrap gap-2 pt-1">{actions}</div> : null}
    </div>
  );
}

/** An empty state: one heading, one explanation, the actions that move on from it. */
export function EmptyState({
  title,
  children,
  actions,
  className,
}: {
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex max-w-2xl flex-col gap-2 rounded-lg border border-line bg-surface p-4 sm:p-6",
        className,
      )}
    >
      <h2 className="text-xl font-medium text-ink">{title}</h2>
      <p className="text-sm text-ink-secondary">{children}</p>
      {actions ? <div className="flex flex-wrap gap-2 pt-2">{actions}</div> : null}
    </div>
  );
}
