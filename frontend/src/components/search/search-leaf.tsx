import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MatchStrictness } from '@/types/search';

export const MODE_LABELS: Record<string, string> = {
  search_only: 'Find Jobs', search_score: 'Find & Rank', full_pipeline: 'Find, Rank & Prepare',
};

export function formatCurrency(value: number | null | undefined, currency = 'USD'): string {
  if (value == null) return 'Not set';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function compactList(values: string[], limit = 8): { visible: string[]; hidden: number } {
  return {
    visible: values.slice(0, limit),
    hidden: Math.max(values.length - limit, 0),
  };
}

export function titleCase(value: string): string {
  if (!value) return value;
  return value
    .split(/\s+/)
    .map((word) => (word.length === 0 ? word : word[0].toUpperCase() + word.slice(1).toLowerCase()))
    .join(' ');
}

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

// Category color mapping — applied dynamically from whatever categories the API returns
export const CATEGORY_COLORS: Record<string, string> = {
  jobspy: 'text-blue-600 dark:text-blue-400',
  remote: 'text-emerald-600 dark:text-emerald-400',
  startup: 'text-violet-600 dark:text-violet-400',
  ats: 'text-sky-600 dark:text-sky-400',
  community: 'text-amber-600 dark:text-amber-400',
  crypto: 'text-orange-600 dark:text-orange-400',
  general: 'text-slate-600 dark:text-slate-400',
};

export const CATEGORY_DOTS: Record<string, string> = {
  jobspy: 'bg-blue-500',
  remote: 'bg-emerald-500',
  startup: 'bg-violet-500',
  ats: 'bg-sky-500',
  community: 'bg-amber-500',
  crypto: 'bg-orange-500',
  general: 'bg-slate-400',
};

export type StageInfo = { key: string; label: string };

export const STAGE_MAP: Record<string, StageInfo[]> = {
  search_only: [
    { key: 'searching', label: 'Searching' },
    { key: 'saving', label: 'Saving' },
  ],
  search_score: [
    { key: 'searching', label: 'Searching' },
    { key: 'scoring', label: 'Ranking' },
    { key: 'ai_scoring', label: 'Analyzing' },
    { key: 'saving', label: 'Saving' },
  ],
  full_pipeline: [
    { key: 'searching', label: 'Searching' },
    { key: 'scoring', label: 'Ranking' },
    { key: 'ai_scoring', label: 'Analyzing' },
    { key: 'enhancing', label: 'Preparing' },
    { key: 'saving', label: 'Saving' },
  ],
};

export const getStagesForMode = (m: string): StageInfo[] => STAGE_MAP[m] || STAGE_MAP.search_score;

export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function isStageComplete(stageKey: string, currentStage: string | undefined, m: string): boolean {
  if (!currentStage) return false;
  const stages = getStagesForMode(m);
  const stageIdx = stages.findIndex((s) => s.key === stageKey);
  const currentIdx = stages.findIndex((s) => s.key === currentStage);
  return stageIdx >= 0 && currentIdx >= 0 && stageIdx < currentIdx;
}
