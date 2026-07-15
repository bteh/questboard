/* The kind rail's query vocabulary. A kind maps onto every stored vertical
   value it answers to (legacy names plus its own id), so old rows and new
   kind-id rows both land in the same lane. upcoming_only stays on for the
   whole board: rows whose taping already happened drop, rows with no event
   date (career jobs) pass untouched. */

import { KINDS, facetsFor, kindForVertical, verticalValuesFor } from '@questboard/kinds';
import type { ApplicationFilters } from '@/types/application';

export type KindKey = string; /* a kind id from @questboard/kinds, or 'all' */

export const KIND_KEYS: string[] = ['all', ...KINDS.map((k) => k.id)];

/* Career sits in its own lane, apart from the quest kinds. The default
   "All quests" board is side-quests only, so a wall of ordinary job
   postings never buries the real quests and the resume-fit line (a career
   thing) never shows on a quest poster. The Jobs lane is where career rows
   and their fit belong. This is the one place that names the career kinds;
   the registry stays a clean per-kind list. */
export const CAREER_KIND_IDS: readonly string[] = ['work'];
const CAREER = new Set(CAREER_KIND_IDS);

export function isCareerKind(id: string | undefined): boolean {
  return id !== undefined && CAREER.has(id);
}

/* every stored vertical value the default board spans: quest kinds only,
   career excluded */
const ALL_QUEST_VALUES = KINDS.filter((k) => !isCareerKind(k.id))
  .flatMap((k) => verticalValuesFor(k.id))
  .join(',');

export function kindParams(key: KindKey): Pick<ApplicationFilters, 'vertical' | 'upcoming_only'> {
  return {
    vertical: key === 'all' ? ALL_QUEST_VALUES : verticalValuesFor(key).join(','),
    upcoming_only: true,
  };
}

/* "All quests" counts side-quests only; the Jobs lane owns its own count.
   Reads the per-kind summary the rail already has, so the two agree. */
export function questTotal(kinds: readonly { id: string; count: number }[]): number {
  return kinds.reduce((sum, k) => (isCareerKind(k.id) ? sum : sum + k.count), 0);
}

/** Old ?v= values (career, camera, study, lens) keep working: they resolve
    to the kind that absorbed them. Unknown values fall back to All. */
export function normalizeKindKey(raw: string | undefined): KindKey | undefined {
  if (!raw || raw === 'all') return undefined;
  if (KIND_KEYS.includes(raw)) return raw;
  return kindForVertical(raw)?.id;
}

/** Keep a ?f= facet only when the active kind actually carries it. */
export function normalizeFacetKey(
  kind: KindKey | undefined,
  raw: string | undefined,
): string | undefined {
  if (!kind || kind === 'all' || !raw) return undefined;
  return facetsFor(kind).some((facet) => facet.id === raw) ? raw : undefined;
}
