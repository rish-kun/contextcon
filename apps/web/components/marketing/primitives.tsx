/** Layout pieces that only the home page needs. Product marks come from components/dealproof. */
import { cn } from "@/lib/utils";

export function Container({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-(--layout-marketing-max) px-4 md:px-6 lg:px-8",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SectionHead({
  eyebrow,
  title,
  lead,
  className,
}: {
  eyebrow?: string;
  title: string;
  lead?: string;
  className?: string;
}) {
  return (
    <div className={cn("max-w-2xl", className)}>
      {eyebrow ? <p className="mb-3 text-sm text-ink-muted">{eyebrow}</p> : null}
      <h2 className="font-serif text-3xl text-balance text-ink lg:text-4xl lg:tracking-display">
        {title}
      </h2>
      {lead ? (
        <p className="mt-4 text-base text-pretty text-ink-secondary lg:text-lg">
          {lead}
        </p>
      ) : null}
    </div>
  );
}

/** Every invented company, investor or case on the page carries this label. */
export function IllustrationLabel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center rounded-xs border border-line-strong px-2 text-xs whitespace-nowrap text-ink-secondary",
        className,
      )}
    >
      {children}
    </span>
  );
}
