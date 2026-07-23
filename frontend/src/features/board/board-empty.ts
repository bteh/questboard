/* Which empty board is this? Pinned by board-empty.test.ts.
   An empty result has two honest causes and each gets its own message:
   - filtered-empty: something the reader set cut every row, so the fix is
     clearing a chip or the search;
   - truly-empty: nothing has been fetched yet, so the fix is a restock.
   "Clear a chip" must never show to a reader with no chips to clear. */

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
): BoardEmptyKind {
  if (total === undefined || total > 0) return 'loaded';
  return filtersActive ? 'filtered-empty' : 'truly-empty';
}
