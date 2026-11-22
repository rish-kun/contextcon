import type { LucideIcon, LucideProps } from "lucide-react";

/**
 * One icon size and stroke everywhere: 16px, stroke 1.5, in the ink of the adjacent text.
 * Decorative by default. Pass `label` when the icon stands alone and carries meaning.
 */
export function Icon({
  icon: Glyph,
  size = 16,
  label,
  ...props
}: Omit<LucideProps, "ref"> & { icon: LucideIcon; label?: string }) {
  return (
    <Glyph
      size={size}
      strokeWidth={1.5}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
      focusable={false}
      {...props}
    />
  );
}
