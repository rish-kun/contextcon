import { cn } from "@/lib/utils";

/**
 * A placeholder block. It fades twice (two seconds) and then holds still: nothing loops.
 * If loading can run longer than that, show a "Still working" line next to it.
 * Wrap a group of skeletons in an element with role="status" and a label.
 */
export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      aria-hidden
      className={cn(
        "h-4 animate-skeleton rounded-xs bg-surface-sunken motion-reduce:animate-none",
        className,
      )}
      {...props}
    />
  );
}

/** Lines of text, the last one shorter. Announces itself once as loading. */
export function SkeletonText({
  lines = 3,
  label = "Loading",
  className,
}: {
  lines?: number;
  label?: string;
  className?: string;
}) {
  return (
    <div role="status" aria-label={label} className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className={index === lines - 1 ? "w-2/3" : "w-full"} />
      ))}
    </div>
  );
}
