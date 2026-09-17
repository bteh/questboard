/* Browse the full career inventory by source kind. "My roles" is the default
   focused view (candidates that match your target roles); the source chips
   open everything available from that kind of source. Founding is a separate,
   composable filter, so it can narrow My roles or any source category. Counts
   are the full inventory, showing the real breadth even when few roles match. */

import { chipActiveClass, chipClass, chipCountClass, chipInactiveClass } from './chip-classes';

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
        className={`${chipClass} ${selected === null ? chipActiveClass : chipInactiveClass}`}
      >
        My roles
      </button>
      <button
        type="button"
        aria-pressed={foundingOnly}
        onClick={onFoundingToggle}
        className={`${chipClass} ${foundingOnly ? chipActiveClass : chipInactiveClass}`}
      >
        Founding
      </button>
      {present.map((c) => (
        <button
          key={c}
          type="button"
          aria-pressed={selected === c}
          onClick={() => onSelect(selected === c ? null : c)}
          className={`${chipClass} ${selected === c ? chipActiveClass : chipInactiveClass}`}
        >
          {CATEGORY_LABELS[c] ?? c}{' '}
          <span className={chipCountClass}>{counts?.[c]}</span>
        </button>
      ))}
    </div>
  );
}
