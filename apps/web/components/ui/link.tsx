import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";

/** A link in running text: accent ink, underlined. `external` opens a new tab and says so. */
export function TextLink({
  href,
  children,
  external = false,
  className,
}: {
  href: string;
  children: React.ReactNode;
  external?: boolean;
  className?: string;
}) {
  const shape = cn(
    "rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover",
    className,
  );
  return external ? (
    <a href={href} target="_blank" rel="noreferrer noopener" className={cn(shape, "inline-flex items-center gap-1")}>
      {children}
      <Icon icon={ExternalLink} size={14} />
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  ) : (
    <Link href={href} className={shape}>
      {children}
    </Link>
  );
}

/**
 * The name in the first cell of a row. With `stretch` its hit area covers the whole row,
 * which must then be `relative`; other controls in the row sit above it with `relative z-10`.
 */
export function RowLink({
  href,
  children,
  stretch = false,
  className,
}: {
  href: string;
  children: React.ReactNode;
  stretch?: boolean;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-xs font-medium text-ink transition-colors hover:text-accent",
        stretch && "after:absolute after:inset-0",
        className,
      )}
    >
      {children}
    </Link>
  );
}
