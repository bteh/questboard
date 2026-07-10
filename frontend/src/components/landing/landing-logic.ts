import { kindForVertical } from '@questboard/kinds';
import { boardVertical, toBoardCard } from '@/utils/board-card';
import { postedAgoLabel } from '@/utils/job-trust';
import { markEntered } from '@/lib/entry';
import type { ApplicationResponse } from '@/types/application';

type EnterNavigate = (opts: { to: '/board' }) => void | Promise<void>;

/* Any CTA click counts as entering: set the flag, land on the board. */
export function handleEnter(navigate: EnterNavigate): void {
  markEntered();
  void navigate({ to: '/board' });
}

function hasStatedPay(app: ApplicationResponse): boolean {
  return app.salary_min != null || app.salary_max != null;
}

/* Up to three posters for the hero, per the first-run beats: mixed KINDS,
   stated pay, newest first. Posters with stated pay outrank the rest; one
   per kind while kinds remain unseen (career and lens both fold into
   skill, so they never crowd out another kind), then newest leftovers.
   Items arrive newest-first from the query. */
export function pickLandingCards(items: ApplicationResponse[]): ApplicationResponse[] {
  const ranked = [...items.filter(hasStatedPay), ...items.filter((app) => !hasStatedPay(app))];
  const picks: ApplicationResponse[] = [];
  const seen = new Set<string>();
  for (const app of ranked) {
    const kind = kindForVertical(app.vertical || 'career')?.id ?? 'skill';
    if (!seen.has(kind)) {
      seen.add(kind);
      picks.push(app);
      if (picks.length === 3) return picks;
    }
  }
  for (const app of ranked) {
    if (!picks.includes(app)) {
      picks.push(app);
      if (picks.length === 3) break;
    }
  }
  return picks;
}

/* keyed by the legacy verticals that earn a specific noun; every other
   lane (house, odd, flip, body, ...) falls back to plain "quest" */
const QUEST_NOUN: Record<string, string> = {
  career: 'job posting',
  camera: 'casting call',
  study: 'study listing',
  lens: 'gig',
  party: 'party quest',
  personal: 'quest',
};

/* The explain-sheet content for a card, built only from the card's own
   stated fields (title, pay, source, place, true post date). It never adds
   a number or claim the posting does not carry, so it stays honest as the
   real data changes. */
export function plainWords(
  app: ApplicationResponse,
  sourceLabel: string,
): { kicker: string; text: string } {
  const card = toBoardCard(app, sourceLabel);
  const noun = QUEST_NOUN[card.vertical] ?? 'quest';
  const pay = card.pay
    ? ` It pays ${card.pay}${card.payUnit ? ` ${card.payUnit}` : ''}.`
    : '';
  return {
    kicker: `That ${noun}, boiled down:`,
    text: `${card.title}.${pay} ${card.meta}.`,
  };
}

/* The trust block's card sells the true post date, so a spare row that can
   actually say "posted N days ago" wins, then stated pay, then the study
   shape whose session pay reads cleanly. Newest wins every tie. */
export function pickTrustCard(
  items: ApplicationResponse[],
  pinned: ApplicationResponse[],
): ApplicationResponse | null {
  const spare = items.filter((app) => !pinned.includes(app));
  if (spare.length === 0) return null;
  const rank = (app: ApplicationResponse): number =>
    (postedAgoLabel(app.date_posted, app.date_confidence) ? 4 : 0) +
    (hasStatedPay(app) ? 2 : 0) +
    (boardVertical(app) === 'study' ? 1 : 0);
  let best = spare[0];
  for (const app of spare) {
    if (rank(app) > rank(best)) best = app;
  }
  return best;
}
