/* Browse the full career inventory by source kind. "My roles" is the default
   focused view (candidates that match your target roles); the source chips
   open everything available from that kind of source. Founding is a separate,
   composable filter, so it can narrow My roles or any source category. Counts
   are the full inventory, showing the real breadth even when few roles match. */

const CATEGORY_LABELS: Record<string, string> = {
  startup: 'Startups & founding',
  vc: 'VC portfolios',
  crypto: 'Crypto',
  remote: 'Remote',
  ats: 'Company',
  jobspy: 'Big boards',
  /* BuiltIn and The Muse: broad tech boards that list everyone from seed
     startups to Netflix. Kept out of Startup & founder so that chip keeps
     its promise. */
  general: 'Tech boards',
  community: 'Community',
};
/* Founder + crypto first: the lanes people most often want to browse wide. */
const CATEGORY_ORDER = ['startup', 'vc', 'crypto', 'remote', 'ats', 'jobspy', 'general', 'community'];

interface SourceCategoryChipsProps {
  counts: Record<string, number> | undefined;
  selected: string | null;
  onSelect: (category: string | null) => void;
  foundingOnly: boolean;
  onFoundingToggle: () => void;
}

const inactiveClass = 'border-border-default text-text-secondary hover:text-text-primary';
const activeClass = 'border-brand bg-brand/10 font-medium text-brand';
const chipClass =
  'focus-ring min-h-11 rounded-full border px-3 py-1 text-xs transition-colors md:min-h-0';

export function SourceCategoryChips({
  counts,
  selected,
  onSelect,
  foundingOnly,
  onFoundingToggle,
}: SourceCategoryChipsProps) {
  const present = CATEGORY_ORDER.filter((c) => (counts?.[c] ?? 0) > 0);

  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-1.5"
      role="group"
      aria-label="Browse and filter work"
    >
      <button
        type="button"
        aria-pressed={selected === null}
        onClick={() => onSelect(null)}
        className={`${chipClass} ${selected === null ? activeClass : inactiveClass}`}
      >
        My roles
      </button>
      <button
        type="button"
        aria-pressed={foundingOnly}
        onClick={onFoundingToggle}
        className={`${chipClass} ${foundingOnly ? activeClass : inactiveClass}`}
      >
        Founding
      </button>
      {present.map((c) => (
        <button
          key={c}
          type="button"
          aria-pressed={selected === c}
          onClick={() => onSelect(selected === c ? null : c)}
          className={`${chipClass} ${selected === c ? activeClass : inactiveClass}`}
        >
          {CATEGORY_LABELS[c] ?? c}{' '}
          <span className="font-mono text-text-secondary tabular-nums">{counts?.[c]}</span>
        </button>
      ))}
    </div>
  );
}
