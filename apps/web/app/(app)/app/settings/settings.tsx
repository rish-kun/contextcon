"use client";

import { Switch } from "radix-ui";
import { useId } from "react";
import { useShell } from "@/components/app-shell";
import { Button } from "@/components/ui";
import { useSound } from "@/lib/sound";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className="grid gap-x-8 gap-y-3 border-t border-line py-6 lg:grid-cols-[14rem_minmax(0,40rem)]"
    >
      <h2 className="text-sm font-medium text-ink">{title}</h2>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

const HANDLING: [string, string][] = [
  ["Case-only use", "Uploaded files are read only to check claims and prepare the memo for their case."],
  ["Never used for training", "Your documents are never used to train AI models."],
  ["Not shared across customers", "Files and extracted claims stay isolated to your workspace."],
  ["Personal details stripped", "Personal details that are not needed for screening are removed during processing."],
  ["Scheduled deletion", "Files uploaded to a case are deleted under the retention schedule, or earlier if you delete the case. Each case shows its own deletion date."],
];

export function Settings() {
  const { user, signOut } = useShell();
  const { enabled, setEnabled, playCue } = useSound();
  const soundId = useId();

  return (
    <div className="flex animate-row-in flex-col motion-reduce:animate-none">
      <h1 className="mb-6 text-2xl font-medium text-ink">Settings</h1>

      <Section title="Account">
        <dl className="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
          <dt className="text-ink-muted">Name</dt>
          <dd className="text-ink">{user.display_name}</dd>
          <dt className="text-ink-muted">Email</dt>
          <dd className="truncate font-mono text-dense text-ink">{user.email}</dd>
          <dt className="text-ink-muted">Workspace</dt>
          <dd className="text-ink-secondary">
            Your account belongs to one workspace, set by the admin who created it. Cases, theses
            and investor searches are visible only inside it.
          </dd>
        </dl>
        <p className="text-dense text-ink-secondary">
          Your signed-in name ({user.display_name}) is recorded on every request you approve.
        </p>
        <Button className="self-start" onClick={signOut}>
          Sign out
        </Button>
      </Section>

      <Section title="Preferences">
        <div className="flex items-start justify-between gap-6">
          <div className="flex flex-col gap-1">
            <label htmlFor={soundId} className="text-sm text-ink">
              Sounds for finished runs and sends
            </label>
            <p id={`${soundId}-hint`} className="text-dense text-ink-secondary">
              Off by default. Plays a quiet cue only when a run finishes, a request is sent or
              suppressed, or an error needs attention.
            </p>
          </div>
          <Switch.Root
            id={soundId}
            aria-describedby={`${soundId}-hint`}
            checked={enabled}
            onCheckedChange={setEnabled}
            className="relative mt-0.5 inline-flex h-6 w-10 shrink-0 items-center rounded-xl border border-line-strong bg-surface-sunken transition-colors data-[state=checked]:border-ink data-[state=checked]:bg-ink"
          >
            <Switch.Thumb className="block size-4 translate-x-1 rounded-xl bg-surface shadow-xs transition-transform data-[state=checked]:translate-x-5" />
          </Switch.Root>
        </div>
        <div className="flex items-center gap-3">
          <Button size="sm" disabled={!enabled} onClick={() => playCue("run_finished")}>
            Play the run-finished cue
          </Button>
          <span className="font-mono text-xs text-ink-muted" aria-live="polite">
            Sounds are {enabled ? "on" : "off"} in this browser
          </span>
        </div>
      </Section>

      <Section title="Data and confidentiality">
        <h3 className="text-sm text-ink">How uploaded documents are handled</h3>
        <dl className="flex flex-col">
          {HANDLING.map(([term, text]) => (
            <div key={term} className="grid gap-x-4 gap-y-1 border-t border-line py-3 sm:grid-cols-[12rem_minmax(0,1fr)]">
              <dt className="text-dense text-ink">{term}</dt>
              <dd className="text-dense text-ink-secondary">{text}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </div>
  );
}
