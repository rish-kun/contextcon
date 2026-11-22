/**
 * Fit and the share it rests on, never apart: the words, then one bar whose hatched end is
 * the share of criteria that could not be assessed. `pct` is 0 to 100.
 */
export function FitBar({ fit, pct }: { fit: number; pct: number }) {
  const share = Math.round(pct);
  return (
    <span className="flex min-w-0 flex-col gap-1">
      <span className="font-mono text-xs font-medium whitespace-nowrap text-ink">
        Fit {Math.round(fit)} · {share}% assessable
      </span>
      <span aria-hidden className="flex h-1.5 w-full max-w-40 gap-0.5">
        {share > 0 ? <span className="h-full bg-ink" style={{ width: `${share}%` }} /> : null}
        {share < 100 ? <span className="hatch-dense h-full flex-1 border border-dashed border-not-checked-line" /> : null}
      </span>
    </span>
  );
}
