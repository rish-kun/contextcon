import { cn } from "@/lib/utils";

/**
 * The "incomplete" family: a hatched, dashed frame around a plain interior, so the hatch
 * is unmistakable and the text inside stays easy to read. Used for anything that did not
 * happen: a judgment not assessed, a send suppressed in test mode, a check not run.
 */
export function HatchedBlock({
  className,
  innerClassName,
  children,
  ...props
}: React.ComponentProps<"div"> & { innerClassName?: string }) {
  return (
    <div
      className={cn("hatch rounded-md border border-dashed border-not-checked-line p-2", className)}
      {...props}
    >
      <div
        className={cn("rounded-xs bg-not-checked-tint px-3 py-2 text-not-checked", innerClassName)}
      >
        {children}
      </div>
    </div>
  );
}

/**
 * Shown when the data handed to a component breaks one of the product's rules, for
 * example a fact with no source or a change with no stated cause. It is loud on purpose:
 * these are bugs, not states.
 */
export function RuleBreakBlock({
  title,
  children,
  className,
}: {
  title: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-md border border-contradicted bg-contradicted-tint px-3 py-2 text-dense text-contradicted",
        className,
      )}
    >
      <p className="font-medium">{title}</p>
      {children ? <p>{children}</p> : null}
    </div>
  );
}
