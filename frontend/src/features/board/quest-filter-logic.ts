/* Side Quests place and pay rules. A place means near-only: the reader
   typing "Los Angeles" wants Los Angeles, and 7,000 remote user tests
   buried 1,700 local quests when remote passed by default (owner report,
   Oct 2026). "+ remote" adds remote and no-place quests back. */

export interface QuestFilterState {
  place: string;
  withRemote: boolean;
  paidOnly: boolean;
}

export function questLocationStrict(place: string, withRemote: boolean): boolean {
  return Boolean(place.trim()) && !withRemote;
}

/** The place and pay params the list, the rail counts, and the chip probes share. */
export function questFilterParams({ place, withRemote, paidOnly }: QuestFilterState): {
  location?: string;
  location_strict?: boolean;
  pay_stated?: boolean;
} {
  const trimmed = place.trim();
  return {
    location: trimmed || undefined,
    location_strict: questLocationStrict(trimmed, withRemote) || undefined,
    pay_stated: paidOnly || undefined,
  };
}

export function questPlaceNote(place: string, withRemote: boolean): string {
  const trimmed = place.trim();
  if (!trimmed) {
    return 'Pick a place to see quests near you. Pay shows only when the posting states it.';
  }
  return withRemote
    ? `${trimmed} plus remote and no-place quests.`
    : `Only quests in ${trimmed}. Add remote to see online ones too.`;
}
