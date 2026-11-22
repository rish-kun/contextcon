"use client";

import { CircleQuestionMark } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import {
  Button,
  EmptyState,
  Icon,
  Panel,
  PanelBody,
  PanelFooter,
  PanelHeader,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui";
import { useCase } from "./case-context";

/**
 * An explanation that is asked for. The default view of a tab states facts; how a figure
 * is worked out, or why something is shown, opens from this one quiet control.
 */
export function Why({
  children,
  label = "Why?",
  className,
}: {
  children: React.ReactNode;
  /** The trigger's words: "Why?", "How this works". */
  label?: string;
  className?: string;
}) {
  return (
    <Popover>
      <PopoverTrigger
        className={cn(
          "inline-flex h-7 shrink-0 items-center rounded-xs text-xs text-ink-muted underline decoration-dotted underline-offset-4 transition-colors hover:text-ink data-[state=open]:text-ink print:hidden",
          className,
        )}
      >
        {label}
      </PopoverTrigger>
      <PopoverContent align="end" className="flex flex-col gap-2 text-dense text-ink-secondary">
        {children}
      </PopoverContent>
    </Popover>
  );
}

/**
 * The one section of a case tab: a panel with its title, a mono count or date, an
 * optional explanation behind "Why?", and one quiet action. Tables and lists go in
 * `flush`. Every tab is built from these and nothing else.
 */
export function TabSection({
  title,
  meta,
  why,
  whyLabel,
  action,
  footer,
  flush = false,
  id,
  className,
  bodyClassName,
  children,
}: {
  title: string;
  meta?: React.ReactNode;
  why?: React.ReactNode;
  whyLabel?: string;
  action?: React.ReactNode;
  footer?: React.ReactNode;
  flush?: boolean;
  id?: string;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <Panel id={id} aria-labelledby={headingId} aria-label={headingId ? undefined : title} className={cn("scroll-mt-24", className)}>
      <PanelHeader
        id={headingId}
        title={title}
        meta={meta}
        action={
          why || action ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {why ? <Why label={whyLabel}>{why}</Why> : null}
              {action}
            </div>
          ) : undefined
        }
      />
      <PanelBody flush={flush} className={bodyClassName}>
        {children}
      </PanelBody>
      {footer ? <PanelFooter>{footer}</PanelFooter> : null}
    </Panel>
  );
}

/** A tab is a column of sections, 16 apart. */
export function TabStack({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-4", className)} {...props} />;
}

/**
 * Stands in for the content of an identity-dependent tab until the legal entity is
 * chosen. Nothing is attached to a company on a matching name alone.
 */
export function BlockedByIdentity({ what, className }: { what?: string; className?: string }) {
  const { basePath } = useCase();
  return (
    <section
      aria-label="Waiting on identity"
      className={cn(
        "flex flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-lg border border-cannot-verify bg-cannot-verify-tint px-4 py-3",
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <h2 className="flex items-center gap-2 text-sm font-medium text-cannot-verify">
          <Icon icon={CircleQuestionMark} />
          Waiting on identity
        </h2>
        <p className="text-dense text-ink">{what ?? "Confirm the legal entity first"}</p>
      </div>
      <Button asChild variant="primary" size="sm" className="h-11 md:h-8">
        <Link href={`${basePath}/identity`}>Resolve identity</Link>
      </Button>
    </section>
  );
}

/** An empty tab: one panel that says what is absent and offers the way to it. */
export function TabEmpty({
  title,
  children,
  actions,
}: {
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <Panel>
      <EmptyState title={title} actions={actions}>
        {children}
      </EmptyState>
    </Panel>
  );
}

/**
 * Stands where an assessment would be when the case has none: the step that is running,
 * the step that failed, or that nothing has run, and the one action that recovers.
 */
export function AssessmentPending({ what = "The assessment" }: { what?: string }) {
  const { detail, run, runActive, runError, verify } = useCase();
  const ran = (detail?.runs.length ?? 0) > 0;
  const steps = run ? [...run.steps].sort((a, b) => a.position - b.position) : [];
  const failed = steps.find((step) => step.state === "failed");
  const current = steps.find((step) => step.state === "running") ?? steps.find((step) => step.state === "pending");
  const skipped = steps.filter((step) => step.state === "skipped_budget").length;

  const title = runActive ? "Assessment in progress" : failed ? "Assessment did not finish" : "Assessment pending";
  const line = runActive
    ? current
      ? `Now: ${current.label}`
      : "Verification is running"
    : failed
      ? `Stopped at “${failed.label}”${failed.error ? `: ${failed.error}` : ""}`
      : skipped > 0
        ? `${skipped} ${skipped === 1 ? "step was" : "steps were"} not run: budget reached`
        : run || ran
          ? "The last run ended before the assessment step"
          : "No verification has run on this case";

  return (
    <Panel aria-label={title}>
      <EmptyState
        title={title}
        actions={
          <Button variant="primary" size="sm" className="h-11 md:h-8" onClick={() => void verify()} disabled={runActive}>
            {runActive ? "Running" : "Run assessment"}
          </Button>
        }
      >
        {what} appears once it has run. {line}
        {runError ? ` · ${runError}` : null}
      </EmptyState>
    </Panel>
  );
}
