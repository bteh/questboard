/* The vertical chips row's query vocabulary, shared by the board and the
   landing page so both surfaces count the same live totals. "All" spans
   every vertical the board serves; party stays off until a party source
   exists. Quest verticals ask the API for upcoming rows only, so stale
   tapings never reach the board. */

import type { ApplicationFilters } from '@/types/application';

export type VerticalKey = 'all' | 'career' | 'camera' | 'study' | 'lens';

export const VERTICAL_KEYS: VerticalKey[] = ['all', 'career', 'camera', 'study', 'lens'];
export const ALL_VERTICALS = 'career,camera,study,lens';

export function verticalParams(
  key: VerticalKey,
): Pick<ApplicationFilters, 'vertical' | 'upcoming_only'> {
  return {
    vertical: key === 'all' ? ALL_VERTICALS : key,
    upcoming_only: key === 'career' ? undefined : true,
  };
}
