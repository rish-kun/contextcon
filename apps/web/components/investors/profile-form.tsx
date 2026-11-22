"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiError,
  createInvestorSearch,
  getPolicy,
  type InvestorSearchIn,
} from "@/lib/api/client";
import { formatCredits } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  FUNDING_OPTIONS,
  fundingLabel,
  type Option,
  SIZE_OPTIONS,
  sizeLabel,
  STAGE_OPTIONS,
  stageLabel,
  withCurrent,
} from "./format";

type Errors = Partial<Record<keyof InvestorSearchIn, string>>;

const EMPTY: InvestorSearchIn = {
  sector: "",
  location: "",
  stage: "",
  size: "",
  funding_sought: "",
};

function validate(profile: InvestorSearchIn): Errors {
  const errors: Errors = {};
  if (profile.sector.trim().length < 2) errors.sector = "Name the sector the business works in";
  if (profile.location.trim().length < 2) errors.location = "Name a country or region";
  if (!profile.stage) errors.stage = "Choose a stage";
  if (!profile.size) errors.size = "Choose a size";
  if (!profile.funding_sought) errors.funding_sought = "Choose the kind of funding sought";
  return errors;
}

function startError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has ended. Sign in again to start a search.";
    if (typeof error.detail === "string") return error.detail;
  }
  return "The search could not start. Nothing was spent. Try again.";
}

function Choice({
  label,
  placeholder,
  options,
  value,
  error,
  onChange,
}: {
  label: string;
  placeholder: string;
  options: Option[];
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label} error={error}>
      {(control) => (
        <Select value={value || undefined} onValueChange={onChange}>
          <SelectTrigger {...control}>
            <SelectValue placeholder={placeholder} />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </Field>
  );
}

/**
 * The business profile: sector, location, stage, size and the kind of funding sought.
 * Submitting starts one search and goes to its page, where the run can be watched.
 */
export function ProfileForm({ initial }: { initial?: Partial<InvestorSearchIn> }) {
  const router = useRouter();
  const [profile, setProfile] = useState<InvestorSearchIn>({ ...EMPTY, ...initial });
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [budget, setBudget] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    getPolicy()
      .then((policy) => {
        if (live) setBudget(policy.budgets.investor_credits);
      })
      .catch(() => {
        /* the budget line is left out when the policy cannot be read */
      });
    return () => {
      live = false;
    };
  }, []);

  const set = (key: keyof InvestorSearchIn) => (value: string) => {
    setProfile((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  };

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = validate(profile);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    setFailure(null);
    try {
      const search = await createInvestorSearch({
        ...profile,
        sector: profile.sector.trim(),
        location: profile.location.trim(),
      });
      router.push(`/app/investors/${encodeURIComponent(search.id)}?new=1`);
    } catch (error) {
      setFailure(startError(error));
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      aria-labelledby="profile-heading"
      className="flex flex-col rounded-lg border border-line bg-surface shadow-xs"
    >
      <div className="flex flex-col gap-5 p-5">
        <h2 id="profile-heading" className="text-xl font-medium text-ink">
          Your business
        </h2>
        <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
          <Field
            label="Sector"
            hint="The activity, in the words an investor would use"
            error={errors.sector}
            className="sm:col-span-2"
          >
            {(control) => (
              <Input
                {...control}
                name="sector"
                value={profile.sector}
                onChange={(e) => set("sector")(e.target.value)}
                placeholder="Warehousing technology"
                maxLength={300}
                autoComplete="off"
              />
            )}
          </Field>
          <Field label="Location" error={errors.location}>
            {(control) => (
              <Input
                {...control}
                name="location"
                value={profile.location}
                onChange={(e) => set("location")(e.target.value)}
                placeholder="India"
                maxLength={200}
                autoComplete="off"
              />
            )}
          </Field>
          <Choice
            label="Stage"
            placeholder="Choose a stage"
            options={withCurrent(STAGE_OPTIONS, initial?.stage ?? "", stageLabel)}
            value={profile.stage}
            error={errors.stage}
            onChange={set("stage")}
          />
          <Choice
            label="Size"
            placeholder="Choose a size"
            options={withCurrent(SIZE_OPTIONS, initial?.size ?? "", sizeLabel)}
            value={profile.size}
            error={errors.size}
            onChange={set("size")}
          />
          <Choice
            label="Funding sought"
            placeholder="Choose a funding kind"
            options={withCurrent(FUNDING_OPTIONS, initial?.funding_sought ?? "", fundingLabel)}
            value={profile.funding_sought}
            error={errors.funding_sought}
            onChange={set("funding_sought")}
          />
        </div>
      </div>

      {failure ? (
        <p
          role="alert"
          className="border-t border-line bg-contradicted-tint px-5 py-3 text-dense text-contradicted"
        >
          {failure}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 rounded-b-lg border-t border-line px-5 py-4">
        <p className="text-xs text-ink-secondary">
          {budget != null ? (
            <>
              One search uses up to{" "}
              <span className="font-mono text-ink">{formatCredits(budget)} credits</span>, then
              stops
            </>
          ) : (
            "One search runs against a fixed credit budget, then stops"
          )}
        </p>
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? "Starting search" : "Find investors"}
        </Button>
      </div>
    </form>
  );
}
