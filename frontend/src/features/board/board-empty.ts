/* Which empty board is this? Pinned by board-empty.test.ts.
   An empty result has two honest causes and each gets its own message:
   - filtered-empty: something the reader set cut every row, so the fix is
     clearing a chip or the search;
   - truly-empty: nothing has been fetched yet, so the fix is a restock.
   "Clear a chip" must never show to a reader with no chips to clear.
   One refinement of that rule: before any source has ever run (checked_at
   null) there was nothing a chip could have hidden, so the place a new
   user just answered at /start never reads back as the problem. */

export type BoardEmptyKind = 'loaded' | 'filtered-empty' | 'truly-empty';

export interface BoardFilterSignals {
  search?: string;
  place?: string;
  payFrom?: string;
  payTo?: string;
  facet?: string;
  presetCount?: number;
  sourceCategory?: string | null;
  /** the posted-within window (?days); set means the reader narrowed by date */
  postedDays?: string;
}

function set(text: string | undefined): boolean {
  return Boolean(text && text.trim());
}

export function boardFiltersActive(signals: BoardFilterSignals): boolean {
  return (
    set(signals.search) ||
    set(signals.place) ||
    set(signals.payFrom) ||
    set(signals.payTo) ||
    Boolean(signals.facet) ||
    (signals.presetCount ?? 0) > 0 ||
    Boolean(signals.sourceCategory) ||
    Boolean(signals.postedDays)
  );
}

export function boardEmptyState(
  total: number | undefined,
  filtersActive: boolean,
  neverChecked = false,
): BoardEmptyKind {
  if (total === undefined || total > 0) return 'loaded';
  if (neverChecked) return 'truly-empty';
  return filtersActive ? 'filtered-empty' : 'truly-empty';
}

/** The truly-empty board's two moments. The backend fires its first sweep
    about 90 seconds after boot, so before any source has run the board is
    stocking itself and says so; after a sweep the door is a manual check.
    Both keep the restock button as the impatient path. */
export function trulyEmptyLines(neverChecked: boolean): { lead: string; body: string } {
  if (neverChecked) {
    return {
      lead: 'The board is stocking itself for the first time.',
      body: 'Quests start landing in about a minute. The check below runs one now.',
    };
  }
  return {
    lead: 'The board is empty right now.',
    body: 'No quests have come in yet. One check fills it from the live sources.',
  };
}
