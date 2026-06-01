// Non-component helpers for the search UI. Kept in a separate module from
// search-leaf.tsx so that file can export only components (required for React
// Fast Refresh / react-refresh/only-export-components).

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
