/* Browse the full career inventory by source kind. "My roles" is the default
   focused view (candidates that match your target roles); the other chips open
   everything available from that kind of source — founder/VC boards, crypto,
   remote-first boards, company ATS pages, the big boards. Counts are the full
   inventory, so you see the real breadth even when your roles match few. */

const CATEGORY_LABELS: Record<string, string> = {
  startup: 'Startup & founder',
  crypto: 'Crypto',
  remote: 'Remote',
  ats: 'Company',
  jobspy: 'Big boards',
  community: 'Community',
};
/* Founder + crypto first: the lanes people most often want to browse wide. */
const CATEGORY_ORDER = ['startup', 'crypto', 'remote', 'ats', 'jobspy', 'community'];

interface SourceCategoryChipsProps {
  counts: Record<string, number> | undefined;
  selected: string | null;
  onSelect: (category: string | null) => void;
}

export function SourceCategoryChips({ counts, selected, onSelect }: SourceCategoryChipsProps) {
  const present = CATEGORY_ORDER.filter((c) => (counts?.[c] ?? 0) > 0);
  if (present.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5" role="tablist" aria-label="Browse by source">
      <button
        type="button"
        role="tab"
        aria-selected={selected === null}
        onClick={() => onSelect(null)}
        className={`rounded-full border px-3 py-1 text-xs transition-colors ${
          selected === null
            ? 'border-brand bg-brand/10 font-medium text-brand'
            : 'border-border-default text-text-secondary hover:text-text-primary'
        }`}
      >
        My roles
      </button>
      {present.map((c) => (
        <button
          key={c}
          type="button"
          role="tab"
          aria-selected={selected === c}
          onClick={() => onSelect(selected === c ? null : c)}
          className={`rounded-full border px-3 py-1 text-xs transition-colors ${
            selected === c
              ? 'border-brand bg-brand/10 font-medium text-brand'
              : 'border-border-default text-text-secondary hover:text-text-primary'
          }`}
        >
          {CATEGORY_LABELS[c] ?? c}{' '}
          <span className="font-mono text-text-muted tabular-nums">{counts?.[c]}</span>
        </button>
      ))}
    </div>
  );
}
