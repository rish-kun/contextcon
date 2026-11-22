import {
  ArrowDownRight,
  ArrowUpRight,
  CircleQuestionMark,
  type LucideIcon,
  Search,
} from "lucide-react";
import { DISPOSITION_LABEL } from "@/lib/labels";
import type { Disposition, DispositionResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icon";
import { SourceLine } from "./source-line";

const STAMP_STYLE: Record<Disposition, string> = {
  prioritise: "border-prioritise bg-prioritise-tint text-prioritise",
  investigate_further: "border-investigate bg-investigate-tint text-investigate",
  // Graphite, not red: red means a claim was Contradicted.
  deprioritise: "border-deprioritise bg-deprioritise-tint text-deprioritise",
  cannot_assess: "border-cannot-assess bg-cannot-assess-tint text-cannot-assess",
};

const STAMP_ICON: Record<Disposition, LucideIcon> = {
  prioritise: ArrowUpRight,
  investigate_further: Search,
  deprioritise: ArrowDownRight,
  cannot_assess: CircleQuestionMark,
};

/**
 * A disposition is a stamp, not a tag: taller, a 1.5px border in its own ink, label at
 * weight 600. Only dispositions use this form, so one is never mistaken for a claim
 * status even where the hue is shared.
 */
export function DispositionStamp({
  disposition,
  size = "default",
  struck = false,
  className,
}: {
  disposition: Disposition;
  /** default is 32px. header is 40px, for the case header. sm is 24px, for table cells and cards. */
  size?: "default" | "header" | "sm";
  /** Strike the label through: the previous value in a diff. */
  struck?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-sm font-semibold whitespace-nowrap",
        size === "sm" ? "h-6 gap-1 border px-2 text-xs" : "gap-2 border-stamp text-sm",
        size === "header" ? "h-10 px-4" : size === "default" ? "h-8 px-3" : null,
        STAMP_STYLE[disposition],
        className,
      )}
    >
      <Icon icon={STAMP_ICON[disposition]} size={size === "sm" ? 14 : 16} />
      <span className={cn(struck && "line-through")}>{DISPOSITION_LABEL[disposition]}</span>
    </span>
  );
}

/**
 * The stamp with what must always sit beneath it: one to three reasons, the claims it
 * rests on, and the policy version that produced it.
 */
export function DispositionSummary({
  result,
  size,
  className,
}: {
  result: DispositionResult;
  size?: "default" | "header";
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-start gap-3", className)}>
      <DispositionStamp disposition={result.disposition} size={size} />
      <ul className="flex flex-col gap-2 text-dense text-ink">
        {result.reasons.map((reason) => (
          <li key={reason.text} className="flex flex-col items-start gap-1">
            <span>{reason.text}</span>
            {reason.evidence && reason.evidence.length > 0 ? (
              <SourceLine evidence={reason.evidence} />
            ) : null}
          </li>
        ))}
      </ul>
      <p className="font-mono text-2xs text-ink-secondary">
        {result.rests_on_claims && result.rests_on_claims.length > 0
          ? `Rests on claims ${result.rests_on_claims.join(", ")} · `
          : null}
        policy {result.policy_version}
      </p>
    </div>
  );
}
