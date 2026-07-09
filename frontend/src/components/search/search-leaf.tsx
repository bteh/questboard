import { useState, useEffect } from 'react';
import { cx } from '@questboard/ui';
import type { MatchStrictness } from '@/types/search';
import { compactList } from './search-leaf-helpers';
import './restock.css';

const STRICTNESS_OPTIONS: { value: MatchStrictness; label: string; hint: string }[] = [
  { value: 'loose', label: 'Loose', hint: 'Wider net: more results, looser matches' },
  { value: 'balanced', label: 'Balanced', hint: 'The default; fits most people' },
  { value: 'strict', label: 'Strict', hint: 'Tight matches only, fewer results' },
];

export function MatchStrictnessControl({
  value,
  onChange,
}: {
  value: MatchStrictness;
  onChange: (value: MatchStrictness) => void;
}) {
  return (
    <div role="radiogroup" aria-label="Match strictness" className="qb-seg">
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
            className={cx(selected && 'qb-active')}
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
    <div className="qb-snaprow">
      <div className="qb-snaplabel" title={hint}>{label}</div>
      <div className="qb-snapval">{value}</div>
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
    <div className="qb-snaprow">
      <div className="qb-snaplabel" title={hint}>{label}</div>
      <div className="qb-snapval">
        {visible.length > 0
          ? `${visible.join(', ')}${hidden > 0 ? ` and ${hidden} more` : ''}`
          : emptyLabel}
      </div>
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
      ? 'Picking out roles, keywords, and target companies...'
      : elapsed < 60
        ? 'Writing suggestions; speed depends on your AI provider...'
        : 'Still working; slower models can take a couple of minutes...';
  return (
    <div className="qb-restock-note" role="status">
      <b>Reading your resume...</b>
      <div className="qb-notefoot">
        {hint} <span className="qb-num">{elapsed}s</span>
      </div>
    </div>
  );
}
