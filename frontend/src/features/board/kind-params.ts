/* The kind rail's query vocabulary. A kind maps onto every stored vertical
   value it answers to (legacy names plus its own id), so old rows and new
   kind-id rows both land in the same lane. upcoming_only stays on for the
   whole board: rows whose taping already happened drop, rows with no event
   date (career jobs) pass untouched. */

import { KINDS, kindForVertical, verticalValuesFor } from '@questboard/kinds';
import type { ApplicationFilters } from '@/types/application';

export type KindKey = string; /* a kind id from @questboard/kinds, or 'all' */

export const KIND_KEYS: string[] = ['all', ...KINDS.map((k) => k.id)];

const ALL_VALUES = KINDS.flatMap((k) => verticalValuesFor(k.id)).join(',');

export function kindParams(key: KindKey): Pick<ApplicationFilters, 'vertical' | 'upcoming_only'> {
  return {
    vertical: key === 'all' ? ALL_VALUES : verticalValuesFor(key).join(','),
    upcoming_only: true,
  };
}

/** Old ?v= values (career, camera, study, lens) keep working: they resolve
    to the kind that absorbed them. Unknown values fall back to All. */
export function normalizeKindKey(raw: string | undefined): KindKey | undefined {
  if (!raw || raw === 'all') return undefined;
  if (KIND_KEYS.includes(raw)) return raw;
  return kindForVertical(raw)?.id;
}
