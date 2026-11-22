"use client";

import { motion } from "motion/react";
import { Tabs as TabsPrimitive } from "radix-ui";
import { createContext, useContext, useId, useState } from "react";
import { transition } from "@/lib/transitions";
import { cn } from "@/lib/utils";

const TabsContext = createContext<{ value: string | undefined; indicatorId: string }>({
  value: undefined,
  indicatorId: "tabs",
});

/**
 * Tabs with an underline that moves to the selected tab over 200ms.
 * The selected tab is also ink and medium weight, so the underline is not the only sign.
 * Arrow keys move between tabs (Radix).
 */
export function Tabs({
  value: controlled,
  defaultValue,
  onValueChange,
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const value = controlled ?? uncontrolled;
  const indicatorId = useId();

  return (
    <TabsContext.Provider value={{ value, indicatorId }}>
      <TabsPrimitive.Root
        value={value}
        onValueChange={(next) => {
          setUncontrolled(next);
          onValueChange?.(next);
        }}
        className={cn("flex flex-col gap-4", className)}
        {...props}
      />
    </TabsContext.Provider>
  );
}

export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn(
        "flex items-end gap-6 overflow-x-auto border-b border-line-strong",
        className,
      )}
      {...props}
    />
  );
}

export function TabsTrigger({
  className,
  children,
  value,
  count,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger> & {
  /** A mono count after the label, as in "Claims 12". */
  count?: number;
}) {
  const { value: selected, indicatorId } = useContext(TabsContext);
  const active = selected === value;

  return (
    <TabsPrimitive.Trigger
      value={value}
      className={cn(
        "relative inline-flex h-9 shrink-0 items-center gap-2 rounded-xs text-sm text-ink-muted transition-colors hover:text-ink disabled:pointer-events-none disabled:opacity-50 data-[state=active]:font-medium data-[state=active]:text-ink",
        className,
      )}
      {...props}
    >
      {children}
      {count !== undefined ? (
        <span className="font-mono text-xs font-normal text-ink-muted">{count}</span>
      ) : null}
      {active ? (
        <motion.span
          layoutId={indicatorId}
          transition={transition.base}
          className="absolute inset-x-0 bottom-0 h-0.5 bg-ink"
          aria-hidden
        />
      ) : null}
    </TabsPrimitive.Trigger>
  );
}

export function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      className={cn("animate-fade-in rounded-xs motion-reduce:animate-none", className)}
      {...props}
    />
  );
}
