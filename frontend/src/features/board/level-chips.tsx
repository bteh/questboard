/* Real case (Sep 17 2026): 61 lead and 211 manager postings, newest first,
   24 a page. A reader paged a few times and concluded there were no lead
   roles. Counts per level make the split visible; a chip narrows to it.
   Counts come from the API over the visible lane before any level
   narrowing, so they stay put while one chip is selected. */

import { chipActiveClass, chipClass, chipCountClass, chipInactiveClass } from './chip-classes';

const LEVEL_LABELS: Record<string, string> = {
  lead: 'Lead',
  manager: 'Manager',
  director: 'Director',
  vp: 'VP',
  chief: 'Chief',
};
const LEVEL_ORDER = ['lead', 'manager', 'director', 'vp', 'chief'];

interface LevelChipsProps {
  counts: Record<string, number> | undefined;
  selected: string | null;
  onSelect: (level: string | null) => void;
}

export function LevelChips({ counts, selected, onSelect }: LevelChipsProps) {
  const present = LEVEL_ORDER.filter((level) => (counts?.[level] ?? 0) > 0);
  if (present.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by level">
      {present.map((level) => (
        <button
          key={level}
          type="button"
          aria-pressed={selected === level}
          onClick={() => onSelect(selected === level ? null : level)}
          className={`${chipClass} ${selected === level ? chipActiveClass : chipInactiveClass}`}
        >
          {LEVEL_LABELS[level] ?? level}{' '}
          <span className={chipCountClass}>{counts?.[level]}</span>
        </button>
      ))}
    </div>
  );
}
