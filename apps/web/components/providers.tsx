"use client";

import { MotionConfig } from "motion/react";
import { Tooltip } from "radix-ui";
import { SoundProvider } from "@/lib/sound";
import { transition } from "@/lib/transitions";

/**
 * App-wide client providers.
 * - MotionConfig: one curve for every Motion animation, and transforms and layout
 *   animations are dropped when the reader asks for reduced motion.
 * - Tooltip.Provider: one shared delay for every tooltip.
 * - SoundProvider: opt-in cues, off by default.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user" transition={transition.base}>
      <Tooltip.Provider delayDuration={300} skipDelayDuration={200}>
        <SoundProvider>{children}</SoundProvider>
      </Tooltip.Provider>
    </MotionConfig>
  );
}
