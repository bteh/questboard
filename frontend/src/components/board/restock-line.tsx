import { useApplications } from '@/hooks/use-applications';
import { useSearchContext } from '@/contexts/search-context';
import { ALL_VERTICALS } from '@/utils/board-verticals';
import { restockLine, restockProgress } from './restock-logic';
import { QuestRestockButton } from './quest-restock';

/* The restock line under the board head. Three states: a live run counted
   from its own progress messages, a fresh board dated by the newest row's
   date_found, and the stale ask once nothing new has landed for a week.
   Restock is a verb here, not a nav item; this line is the door. The door
   itself is the quest refresh: this line only renders on quest lanes, so
   it must never route to the career job-search form. */

export function RestockLine() {
  const { state, messages } = useSearchContext();
  /* the newest row on the whole board, one row, any vertical */
  const { data } = useApplications({
    vertical: ALL_VERTICALS,
    sort_by: 'date_found',
    sort_order: 'desc',
    page: 1,
    page_size: 1,
  });

  if (state === 'running') {
    const progress = restockProgress(messages);
    return (
      <p className="qb-restockline" role="status">
        {progress
          ? `Checking ${progress.total} sources, ${progress.done} reported so far.`
          : 'Checking the sources.'}
      </p>
    );
  }

  /* while loading, say nothing rather than guess a date */
  if (!data) return <p className="qb-restockline" aria-hidden="true">&nbsp;</p>;

  const line = restockLine(data.items[0]?.date_found ?? null);
  if (line.kind === 'stale') {
    return (
      <p className="qb-restockline">
        Nothing new this week. <QuestRestockButton />
      </p>
    );
  }
  return (
    <p className="qb-restockline">
      Fresh quests landed {line.label}. <QuestRestockButton label="Check for new" />
    </p>
  );
}
