import { BadgeCheck, CircleQuestionMark } from "lucide-react";
import { plural } from "@/lib/format";
import type { Identity, IdentityCandidate, IdentityKey } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { SourceLine } from "./source-line";

function KeyRows({ keys }: { keys: IdentityKey[] }) {
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-4 gap-y-2 text-dense">
      {keys.map((item) => (
        <div key={item.key} className="contents">
          <dt className="text-ink-muted">{item.label}</dt>
          <dd className="flex flex-wrap items-center gap-x-2 gap-y-1 text-ink">
            <span>{item.value}</span>
            <SourceLine evidence={item.evidence} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Identity comes first. Confirmed shows the matching keys, each with its source line:
 * the keys are the proof, so there is no green wash. Unresolved lists the candidates
 * side by side with the keys that match and the keys that differ, and offers one action.
 *
 * variant="inline" is the one-line form for the case header and dashboard rows.
 */
export function IdentityBadge({
  identity,
  variant = "band",
  onChoose,
  className,
}: {
  identity: Identity;
  variant?: "band" | "inline";
  /** Called with the chosen candidate. Without it the candidates are read-only. */
  onChoose?: (candidate: IdentityCandidate) => void;
  className?: string;
}) {
  if (variant === "inline") {
    return identity.state === "confirmed" ? (
      <span className={cn("inline-flex items-center gap-1 text-dense text-ink", className)}>
        <Icon icon={BadgeCheck} className="shrink-0" />
        <span>
          Identity confirmed
          <span className="text-ink-secondary">
            {" "}
            · {identity.keys.map((key) => key.label.toLowerCase()).join(", ")}
          </span>
        </span>
      </span>
    ) : (
      <span className={cn("inline-flex items-center gap-1 text-dense text-cannot-verify", className)}>
        <Icon icon={CircleQuestionMark} className="shrink-0" />
        <span>
          Identity unresolved · {plural(identity.candidates.length, "candidate")}
        </span>
      </span>
    );
  }

  if (identity.state === "confirmed") {
    return (
      <section
        aria-label="Identity"
        className={cn("flex flex-col gap-3 rounded-lg border border-line bg-surface p-4", className)}
      >
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <Icon icon={BadgeCheck} />
          Identity confirmed
          <span className="font-normal text-ink-secondary">{identity.entity_name}</span>
        </p>
        <KeyRows keys={identity.keys} />
      </section>
    );
  }

  return (
    <section
      aria-label="Identity"
      className={cn(
        "flex flex-col gap-4 rounded-lg border border-cannot-verify bg-cannot-verify-tint p-4",
        className,
      )}
    >
      <div className="flex flex-col gap-1">
        <p className="flex items-center gap-2 text-sm font-medium text-cannot-verify">
          <Icon icon={CircleQuestionMark} />
          Identity unresolved · {plural(identity.candidates.length, "candidate")}
        </p>
        <p className="text-dense text-ink-secondary">
          Nothing is attached to a company on a matching name alone. Until the entity is
          chosen, the disposition is Cannot assess.
        </p>
      </div>
      <ul className="grid gap-3 md:grid-cols-2">
        {identity.candidates.map((candidate) => (
          <li
            key={candidate.id}
            className="flex flex-col gap-3 rounded-md border border-line bg-surface p-3"
          >
            <p className="text-sm font-medium text-ink">{candidate.name}</p>
            <div className="flex flex-col gap-2">
              <p className="text-xs text-ink-muted">Matches</p>
              <KeyRows keys={candidate.matching} />
            </div>
            <div className="flex flex-col gap-2 border-t border-line pt-3">
              <p className="text-xs text-ink-muted">Differs</p>
              <KeyRows keys={candidate.differing} />
            </div>
            {onChoose ? (
              <Button
                size="sm"
                className="self-start"
                onClick={() => onChoose(candidate)}
                aria-label={`Choose the entity: ${candidate.name}`}
              >
                Choose the entity
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Replaces the content of an identity-dependent tab until the entity is chosen. */
export function WaitingOnIdentity({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border border-cannot-verify-line bg-cannot-verify-tint px-4 py-6 text-sm text-cannot-verify",
        className,
      )}
    >
      <Icon icon={CircleQuestionMark} />
      Waiting on identity
    </div>
  );
}
