"use client";

import { X } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

/**
 * A dialog interrupts, so it is used in one place: confirming a send.
 * Focus is trapped and returned to the trigger, and Escape closes it (Radix).
 */
export function DialogContent({
  className,
  children,
  hideClose = false,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { hideClose?: boolean }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-(--z-dialog) grid animate-fade-in place-items-center overflow-y-auto bg-scrim p-4 motion-reduce:animate-none">
        <DialogPrimitive.Content
          className={cn(
            "relative flex w-full max-w-lg animate-overlay-in flex-col gap-4 rounded-xl border border-line bg-surface p-6 text-ink shadow-lg motion-reduce:animate-none",
            className,
          )}
          {...props}
        >
          {children}
          {hideClose ? null : (
            <DialogPrimitive.Close
              aria-label="Close"
              className="absolute top-4 right-4 inline-flex size-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-surface-raised hover:text-ink"
            >
              <Icon icon={X} />
            </DialogPrimitive.Close>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Overlay>
    </DialogPrimitive.Portal>
  );
}

export function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-1 pr-8", className)} {...props} />;
}

export function DialogTitle({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      className={cn("text-xl font-medium text-ink", className)}
      {...props}
    />
  );
}

export function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      className={cn("text-sm text-ink-secondary", className)}
      {...props}
    />
  );
}

export function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}
      {...props}
    />
  );
}
