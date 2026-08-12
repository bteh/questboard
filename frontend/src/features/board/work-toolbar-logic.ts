const WORKPLACE_WORDS: Record<string, string> = {
  remote_friendly: 'remote friendly',
  remote_only: 'remote only',
  location_only: 'on location',
};

export function primaryRunKind(assistantReady: boolean): 'assistant' | 'pull' {
  return assistantReady ? 'assistant' : 'pull';
}

export function pullReceipt(
  prefs:
    | {
        roles: string[];
        preferred_places: { label: string }[];
        workplace_preference: string;
        compensation: { min_base: number | null };
      }
    | undefined,
  assistantReady = false,
): string {
  if (prefs === undefined) return 'Pulls fresh postings for your target roles.';
  if (!prefs.roles.length) return 'No target roles saved yet.';
  const roles =
    prefs.roles.length === 1
      ? prefs.roles[0]
      : `${prefs.roles[0]} and ${prefs.roles.length - 1} more role${prefs.roles.length > 2 ? 's' : ''}`;
  const lead = assistantReady
    ? `Pulls fresh postings and ranks them for ${roles}`
    : `Pulls fresh postings for ${roles}`;
  const parts = [lead];
  if (prefs.preferred_places.length > 0) parts.push(prefs.preferred_places[0].label);
  const stance = WORKPLACE_WORDS[prefs.workplace_preference];
  if (stance) parts.push(stance);
  const floor = prefs.compensation?.min_base;
  if (floor) parts.push(`$${Math.round(floor / 1000)}K+ base`);
  return `${parts.join(' · ')}.`;
}

export function filterPlaceholder(count: number | undefined): string {
  return count !== undefined && count > 1 ? `Filter these ${count} jobs` : 'Filter these jobs';
}

/** Keep the local view action separate from the external source refresh. */
export function filterTrayCaption(filtering: boolean): string {
  const state = filtering ? 'Applying filters…' : 'Filters update this board automatically';
  return `${state} · Get new jobs checks sources and reranks using your saved search`;
}

export function filterStatusText({
  shown,
  laneTotal,
  filtered,
  checkedAgo,
  hiddenNote,
  scopeNote,
}: {
  shown: number | undefined;
  laneTotal: number | undefined;
  filtered: boolean;
  checkedAgo: string | null;
  hiddenNote?: string | null;
  scopeNote?: string | null;
}): string {
  if (shown === undefined) return checkedAgo ?? '';
  const jobs = (n: number) => `${n} job${n === 1 ? '' : 's'}`;
  const lead = filtered
    ? laneTotal !== undefined && laneTotal >= shown
      ? `Showing ${shown} of ${jobs(laneTotal)}`
      : `Showing ${jobs(shown)}`
    : jobs(shown);
  return [lead, checkedAgo, scopeNote, hiddenNote].filter(Boolean).join(' · ');
}
