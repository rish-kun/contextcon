import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import { cn } from "@/lib/utils";

/**
 * Primary is ink, not accent. Secondary is surface with a strong hairline.
 * Quiet is the text button for tertiary actions. Destructive is Contradicted ink on a
 * secondary button and always needs a confirmation step.
 */
export const buttonVariants = cva(
  "press inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-[background-color,border-color,color,transform] select-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-ink text-ink-inverse shadow-xs hover:bg-ink-secondary",
        secondary:
          "border border-line-strong bg-surface text-ink shadow-xs hover:bg-surface-raised",
        quiet: "text-ink-secondary hover:bg-surface-raised hover:text-ink",
        destructive:
          "border border-line-strong bg-surface text-contradicted shadow-xs hover:border-contradicted-line hover:bg-contradicted-tint",
        link: "rounded-xs text-accent underline underline-offset-4 hover:text-accent-hover",
      },
      size: {
        /** 32px: dense toolbars */
        sm: "h-8 px-3",
        /** 36px: the app default */
        md: "h-9 px-4",
        /** 44px: touch and the home page */
        lg: "h-11 px-5",
        /** Sits in running text */
        inline: "h-auto p-0",
        /** Square, for a single icon. Needs an aria-label */
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ComponentProps<"button">,
    VariantProps<typeof buttonVariants> {
  /** Render the child element with button styling, for example a Next.js Link. */
  asChild?: boolean;
}

export function Button({
  className,
  variant,
  size,
  asChild = false,
  type,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      type={asChild ? undefined : (type ?? "button")}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
