/* The legacy query vocabulary for pre-kinds surfaces (home, log, restock).
   "All" derives from the kinds registry, never a hand list: it spans every
   registry vertical, so a clipped bank bonus or odd job shows up in the
   log and the home totals the same day its source ships. Newer surfaces
   use features/board/kind-params directly; this module retires when home
   and log migrate. Quest verticals ask the API for upcoming rows only, so
   stale tapings never reach a page. */

import { KINDS, verticalValuesFor } from '@questboard/kinds';
import type { ApplicationFilters } from '@/types/application';

export type VerticalKey = 'all' | 'career' | 'camera' | 'study' | 'lens';

export const VERTICAL_KEYS: VerticalKey[] = ['all', 'career', 'camera', 'study', 'lens'];
export const ALL_VERTICALS = KINDS.flatMap((k) => verticalValuesFor(k.id)).join(',');

export function verticalParams(
  key: VerticalKey,
): Pick<ApplicationFilters, 'vertical' | 'upcoming_only'> {
  return {
    vertical: key === 'all' ? ALL_VERTICALS : key,
    upcoming_only: key === 'career' ? undefined : true,
  };
}
