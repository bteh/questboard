import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MatchStrictness } from '@/types/search';
import { compactList } from './search-leaf-helpers';

const STRICTNESS_OPTIONS: { value: MatchStrictness; label: string; hint: string }[] = [
  { value: 'loose', label: 'Loose', hint: 'Wider net — more results, looser matches' },
  { value: 'balanced', label: 'Balanced', hint: 'Default behavior — matches most users' },
  { value: 'strict', label: 'Strict', hint: 'Tight matches only — fewer, more relevant results' },
];

export function MatchStrictnessControl({
  value,
  onChange,
}: {
  value: MatchStrictness;
  onChange: (value: MatchStrictness) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Match strictness"
      className="grid grid-cols-3 gap-1 rounded-lg border border-border-default bg-bg-card p-1"
    >
      {STRICTNESS_OPTIONS.map((opt) => {
        const selected = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={selected}
            title={opt.hint}
            onClick={() => onChange(opt.value)}
            className={cn(
              'rounded-md px-2 py-1.5 text-xs font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand',
              selected
                ? 'bg-brand-light/60 text-brand'
                : 'text-text-tertiary hover:text-text-secondary',
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

export function SnapshotField({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-card/70 px-3 py-2">
      <p
        className="text-[11px] font-medium text-text-muted"
        title={hint}
      >
        {label}
      </p>
      <p className="mt-0.5 text-sm text-text-primary tabular-nums">{value}</p>
    </div>
  );
}

export function SnapshotList({
  label,
  values,
  emptyLabel = 'Not set',
  hint,
}: {
  label: string;
  values: string[];
  emptyLabel?: string;
  hint?: string;
}) {
  const filtered = values.filter(Boolean);
  const { visible, hidden } = compactList(filtered);

  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-medium text-text-muted" title={hint}>
        {label}
      </p>
      {visible.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {visible.map((value) => (
            <span
              key={value}
              className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default"
            >
              {value}
            </span>
          ))}
          {hidden > 0 && (
            <span className="inline-flex items-center rounded-full bg-bg-subtle px-2.5 py-1 text-[11px] text-text-muted ring-1 ring-border-default">
              +{hidden} more
            </span>
          )}
        </div>
      ) : (
        <p className="text-xs text-text-muted">{emptyLabel}</p>
      )}
    </div>
  );
}

export function SuggestLoadingState() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((prev) => prev + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const hint = elapsed < 10
    ? 'Reading your resume...'
    : elapsed < 25
      ? 'Identifying roles, keywords, and target companies...'
      : elapsed < 60
        ? 'Generating suggestions — speed depends on your AI provider...'
        : 'Still working — slower models may take a couple minutes...';
  return (
    <div className="w-full rounded-xl border-2 border-dashed border-brand/25 bg-gradient-to-br from-brand-light/40 to-brand-light/20 p-6 text-center">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-brand/10">
        <Loader2 className="h-5 w-5 text-brand animate-spin" />
      </div>
      <p className="text-sm font-semibold text-brand">Analyzing your resume...</p>
      <p className="text-xs text-text-muted mt-1">{hint}</p>
      <p className="text-[11px] text-text-muted/60 mt-2 tabular-nums">{elapsed}s</p>
    </div>
  );
}
