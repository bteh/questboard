import { toBoardCard } from '@/utils/board-card';
import type { ApplicationResponse } from '@/types/application';

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
