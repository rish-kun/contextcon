"use client";

import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import { useRef, useState } from "react";
import {
  startSearch,
  updateCriteria,
  type CriterionIn,
  type CriterionOut,
  type RunOut,
  type Schemas,
  type ThesisOut,
} from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import { errorText } from "./adapt";
import { ErrorNotice } from "./notice";

type Kind = Schemas["CriterionKind"];
type Operator = Schemas["CriterionOperator"];

/** The scoring policy sets the weight from the kind. It is shown, not typed. */
const WEIGHT: Record<Kind, number> = { must: 2, preference: 1 };

const OPERATOR_LABEL: Record<Operator, string> = {
  eq: "is",
  in: "is one of",
  gte: "is at least",
  lte: "is at most",
  between: "is between",
  contains_any: "mentions any of",
  is_true: "is true",
};
const OPERATORS = Object.keys(OPERATOR_LABEL) as Operator[];

interface Row {
  /** Stable React key. */
  key: string;
  /** The saved criterion's id; null for a row added here. */
  id: string | null;
  label: string;
  kind: Kind;
  dimension: Schemas["CriterionDimension"];
  operator: Operator;
  /** The operand as typed. Lists are comma-separated. */
  value: string;
  /** The upper bound, for "is between". */
  valueTo: string;
  filter: CriterionOut["crustdata_filter"];
  /** The condition was changed here, so the saved search-field mapping no longer matches. */
  conditionEdited: boolean;
}

function toRow(criterion: CriterionOut): Row {
  const { value, operator } = criterion;
  const list = Array.isArray(value) ? value.map(String) : null;
  return {
    key: criterion.id,
    id: criterion.id,
    label: criterion.label,
    kind: criterion.kind,
    dimension: criterion.dimension,
    operator,
    value:
      operator === "is_true"
        ? ""
        : operator === "between"
          ? (list?.[0] ?? "")
          : list
            ? list.join(", ")
            : value == null
              ? ""
              : String(value),
    valueTo: operator === "between" ? (list?.[1] ?? "") : "",
    filter: criterion.crustdata_filter,
    conditionEdited: false,
  };
}

/** "50" stays a number so the search can compare it; anything else stays text. */
function scalar(text: string): string | number {
  const trimmed = text.trim();
  return /^-?\d+(\.\d+)?$/.test(trimmed) ? Number(trimmed) : trimmed;
}

function operand(row: Row): unknown {
  switch (row.operator) {
    case "is_true":
      return true;
    case "between":
      return [scalar(row.value), scalar(row.valueTo)];
    case "in":
    case "contains_any":
      return row.value
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean);
    default:
      return scalar(row.value);
  }
}

function toCriterionIn(row: Row): CriterionIn {
  return {
    id: row.id,
    label: row.label.trim(),
    kind: row.kind,
    dimension: row.dimension,
    operator: row.operator,
    value: operand(row),
    // A mapping that no longer matches the condition is dropped, never sent stale.
    crustdata_filter: row.conditionEdited ? null : row.filter,
  };
}

function rowError(row: Row): string | null {
  if (row.label.trim().length === 0) return "Name the criterion";
  if (row.operator === "is_true") return null;
  if (row.value.trim().length === 0) return "Add a value";
  if (row.operator === "between" && row.valueTo.trim().length === 0) return "Add the upper value";
  return null;
}

function AssessedFrom({ row }: { row: Row }) {
  const field = !row.conditionEdited && typeof row.filter?.field === "string" ? row.filter.field : null;

  if (row.filter && !row.conditionEdited) {
    return (
      <p className="flex flex-col text-dense text-ink">
        <span>Company record</span>
        <span className="font-mono text-2xs break-all text-ink-secondary">
          {field ? `search field ${field}` : "mapped to a search field"}
        </span>
      </p>
    );
  }
  return (
    <p className="flex flex-col text-dense text-ink">
      <span className="inline-flex items-center gap-2">
        <span
          aria-hidden
          className="hatch-dense size-2.5 shrink-0 rounded-xs border border-dashed border-not-checked-line"
        />
        Assessed from evidence
      </span>
      <span className="text-xs text-ink-secondary">
        {row.filter
          ? "Your edit removed the search-field mapping"
          : "No search field covers this; unknown until evidence is read"}
      </span>
    </p>
  );
}

function CriterionRow({
  row,
  error,
  disabled,
  onChange,
  onRemove,
}: {
  row: Row;
  error: string | null;
  disabled: boolean;
  onChange: (patch: Partial<Row>) => void;
  onRemove: () => void;
}) {
  const name = row.label.trim() || "this criterion";
  const condition = (patch: Partial<Row>) => onChange({ ...patch, conditionEdited: true });
  const moveLabel = row.kind === "must" ? "Move to preference" : "Move to must have";

  return (
    <li className="grid grid-cols-1 gap-x-3 gap-y-2 px-4 py-3 lg:grid-cols-[minmax(0,5fr)_10rem_minmax(0,4fr)_3rem_minmax(0,4fr)_4.5rem] lg:items-start">
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className={cn(
            "size-2 shrink-0 border border-ink",
            row.kind === "must" ? "bg-ink" : "bg-surface",
          )}
        />
        <Input
          value={row.label}
          onChange={(event) => onChange({ label: event.target.value })}
          aria-label="Criterion"
          aria-invalid={error === "Name the criterion" ? true : undefined}
          placeholder="Headquartered in India"
          disabled={disabled}
        />
      </div>

      <Select
        value={row.operator}
        onValueChange={(operator) => condition({ operator: operator as Operator })}
        disabled={disabled}
      >
        <SelectTrigger aria-label={`Condition for ${name}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {OPERATORS.map((operator) => (
            <SelectItem key={operator} value={operator}>
              {OPERATOR_LABEL[operator]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex min-w-0 flex-col gap-1">
        {row.operator === "is_true" ? (
          <p className="flex h-9 items-center text-dense text-ink-muted">No value needed</p>
        ) : (
          <div className="flex items-center gap-2">
            <Input
              value={row.value}
              onChange={(event) => condition({ value: event.target.value })}
              aria-label={`Value for ${name}`}
              aria-invalid={error === "Add a value" ? true : undefined}
              placeholder={
                row.operator === "in" || row.operator === "contains_any"
                  ? "Separate values with commas"
                  : undefined
              }
              disabled={disabled}
            />
            {row.operator === "between" ? (
              <>
                <span className="text-dense text-ink-muted">and</span>
                <Input
                  value={row.valueTo}
                  onChange={(event) => condition({ valueTo: event.target.value })}
                  aria-label={`Upper value for ${name}`}
                  aria-invalid={error === "Add the upper value" ? true : undefined}
                  disabled={disabled}
                />
              </>
            ) : null}
          </div>
        )}
        {error ? (
          <p role="alert" className="text-xs text-contradicted">
            Error: {error.toLowerCase()}
          </p>
        ) : null}
      </div>

      <p className="flex items-center gap-2 lg:h-9 lg:justify-end">
        <span className="text-xs text-ink-muted lg:sr-only">Weight</span>
        <span className="font-mono text-sm text-ink">{WEIGHT[row.kind]}</span>
      </p>

      <AssessedFrom row={row} />

      <div className="flex items-center gap-1 lg:justify-end">
        <Tooltip content={moveLabel}>
          <Button
            variant="quiet"
            size="icon"
            aria-label={`${moveLabel}: ${name}`}
            onClick={() => onChange({ kind: row.kind === "must" ? "preference" : "must" })}
            disabled={disabled}
          >
            <Icon icon={row.kind === "must" ? ArrowDown : ArrowUp} />
          </Button>
        </Tooltip>
        <Tooltip content="Remove criterion">
          <Button
            variant="quiet"
            size="icon"
            aria-label={`Remove criterion: ${name}`}
            onClick={onRemove}
            disabled={disabled}
          >
            <Icon icon={X} />
          </Button>
        </Tooltip>
      </div>
    </li>
  );
}

const GROUPS: { kind: Kind; title: string; note: string }[] = [
  {
    kind: "must",
    title: "Must have",
    note: "A company is removed only when a record verifiably fails one of these",
  },
  {
    kind: "preference",
    title: "Preference",
    note: "Counts toward fit. Never removes a company",
  },
];

/**
 * Step 2: the criteria DealProof read from the thesis, editable before anything runs.
 * "Run search" saves the rows and starts the run.
 */
export function CriteriaEditor({
  thesis,
  onStarted,
  onCancel,
}: {
  thesis: ThesisOut;
  onStarted: (run: RunOut, thesis: ThesisOut) => void;
  /** Shown as "Keep current shortlist" when the thesis already has one. */
  onCancel?: () => void;
}) {
  const [rows, setRows] = useState<Row[]>(() => thesis.criteria.map(toRow));
  const [showErrors, setShowErrors] = useState(false);
  const [pending, setPending] = useState<"saving" | "starting" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const nextKey = useRef(0);

  const errors = new Map(rows.map((row) => [row.key, rowError(row)]));
  const invalid = rows.length === 0 || [...errors.values()].some(Boolean);
  const disabled = pending !== null;

  const change = (key: string, patch: Partial<Row>) =>
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));

  function add(kind: Kind) {
    nextKey.current += 1;
    setRows((current) => [
      ...current,
      {
        key: `new-${nextKey.current}`,
        id: null,
        label: "",
        kind,
        dimension: "other",
        operator: "is_true",
        value: "",
        valueTo: "",
        filter: null,
        conditionEdited: false,
      },
    ]);
  }

  async function run() {
    setShowErrors(true);
    if (invalid || disabled) return;
    setFailure(null);
    try {
      setPending("saving");
      // Must-haves first, so positions follow the order on screen.
      const ordered = GROUPS.flatMap((group) => rows.filter((row) => row.kind === group.kind));
      const saved = await updateCriteria(thesis.id, ordered.map(toCriterionIn));
      setPending("starting");
      const started = await startSearch(thesis.id);
      onStarted(started, { ...saved, run: started });
    } catch (caught) {
      setFailure(errorText(caught));
      setPending(null);
    }
  }

  return (
    <section aria-labelledby="criteria-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 id="criteria-heading" className="text-xl font-medium text-ink">
          Criteria
        </h2>
        <p className="text-sm text-ink-secondary">Edit before searching. Nothing runs yet.</p>
      </div>

      <div className="overflow-hidden rounded-lg border border-line bg-surface">
        <div
          aria-hidden
          className="hidden gap-x-3 border-b border-line bg-surface-sunken px-4 py-2 text-xs text-ink-secondary lg:grid lg:grid-cols-[minmax(0,5fr)_10rem_minmax(0,4fr)_3rem_minmax(0,4fr)_4.5rem]"
        >
          <span className="pl-5">Criterion</span>
          <span className="col-span-2">Condition</span>
          <span className="text-right">Weight</span>
          <span>Assessed from</span>
          <span />
        </div>

        {GROUPS.map((group) => {
          const groupRows = rows.filter((row) => row.kind === group.kind);
          return (
            <div key={group.kind} className="border-b border-line last:border-b-0">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 pt-4 pb-1">
                <h3 className="text-sm font-medium text-ink">
                  {group.title}
                  <span className="pl-2 font-mono text-xs font-normal text-ink-muted">
                    {groupRows.length}
                  </span>
                </h3>
                <p className="text-xs text-ink-muted">{group.note}</p>
              </div>
              {groupRows.length > 0 ? (
                <ul className="divide-y divide-line">
                  {groupRows.map((row) => (
                    <CriterionRow
                      key={row.key}
                      row={row}
                      error={showErrors ? (errors.get(row.key) ?? null) : null}
                      disabled={disabled}
                      onChange={(patch) => change(row.key, patch)}
                      onRemove={() =>
                        setRows((current) => current.filter((item) => item.key !== row.key))
                      }
                    />
                  ))}
                </ul>
              ) : (
                <p className="px-4 py-3 text-dense text-ink-muted">
                  {group.kind === "must"
                    ? "No must-haves. No company will be removed"
                    : "No preferences"}
                </p>
              )}
              <div className="px-2 pb-2">
                <Button variant="quiet" size="sm" onClick={() => add(group.kind)} disabled={disabled}>
                  <Icon icon={Plus} />
                  Add criterion
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-ink-muted">
        Weight follows the kind under the scoring policy: must have 2, preference 1. Moving a
        criterion between the groups changes its weight.
      </p>

      {showErrors && rows.length === 0 ? (
        <ErrorNotice title="Add at least one criterion before searching" />
      ) : null}
      {failure ? (
        <ErrorNotice title="The search did not start">
          {failure}. Your edits are still here, and nothing was searched.
        </ErrorNotice>
      ) : null}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
        <p className="text-xs text-ink-muted sm:mr-auto" role="status">
          {pending === "saving"
            ? "Saving criteria"
            : pending === "starting"
              ? "Starting the search"
              : "Running the search spends credits against the run budget"}
        </p>
        {onCancel ? (
          <Button onClick={onCancel} disabled={disabled}>
            Keep current shortlist
          </Button>
        ) : null}
        <Button variant="primary" onClick={run} disabled={disabled}>
          Run search
        </Button>
      </div>
    </section>
  );
}
