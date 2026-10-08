import type { QuestView } from '@/features/board/quest-view';

export function QuestViewBar({
  view,
  onView,
  shown,
  total,
}: {
  view: QuestView;
  onView: (view: QuestView) => void;
  shown: number;
  total: number | undefined;
}) {
  return (
    <div className="qb-viewbar">
      <span className="qb-viewbar-count">
        {total !== undefined ? `${shown.toLocaleString()} of ${total.toLocaleString()}` : ''}
      </span>
      <div className="qb-viewtoggle" role="group" aria-label="View">
        <button type="button" aria-pressed={view === 'list'} onClick={() => onView('list')}>
          list
        </button>
        <button type="button" aria-pressed={view === 'wall'} onClick={() => onView('wall')}>
          wall
        </button>
      </div>
    </div>
  );
}
