import { KindStamp } from '@questboard/ui';
import type { BoardSummaryFilters } from '@/api/board';
import { useBoardSummary } from '@/hooks/use-board-summary';
import { isCareerKind, questTotal, type KindKey } from '@/features/board/kind-params';

/* The kind rail: a labeled, even grid of two-line tags (name over real
   examples), counts right-aligned, in registry order.
   Supply honesty: a kind with nothing live stays off the rail rather than
   posing as a stocked shelf. That includes Party, which has no source and led
   to an empty board when tapped; it returns only if a real source ever fills it.
   Career rows never appear here: Find work is the board's other workflow,
   reached by the lane switcher above the rail, so the quest grid stays
   quests and a job posting never poses as a side quest. */

function Tag({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button type="button" className={active ? 'qb-ktag qb-ktag-on' : 'qb-ktag'} onClick={onClick}>
      {children}
    </button>
  );
}

export function KindRail({
  selected,
  onSelect,
  filters,
}: {
  selected: KindKey;
  onSelect: (key: KindKey) => void;
  /** The board's active filters: the counts must describe the board the
      reader is actually looking at, not the unfiltered whole. */
  filters?: BoardSummaryFilters;
}) {
  const { data } = useBoardSummary(filters);
  if (!data) return null;
  const quests = data.kinds.filter((k) => k.count > 0 && !isCareerKind(k.id));
  const questCount = questTotal(data.kinds);
  const questNew = data.kinds.reduce((sum, k) => (isCareerKind(k.id) ? sum : sum + k.new_today), 0);
  return (
    <>
      <div className="qb-rail-top">
        <span className="qb-rail-label">Kinds of quests</span>
        <Tag active={selected === 'all'} onClick={() => onSelect('all')}>
          <span className="qb-ktag-dot" aria-hidden="true" />
          <span className="qb-ktag-col"><b>All quests</b></span>
          <span className="qb-ktag-count">{questCount.toLocaleString()}</span>
        </Tag>
        {questNew > 0 && (
          <span className="qb-rail-new">{questNew} new today</span>
        )}
      </div>
      <div className="qb-rail">
        {quests.map((kind) => (
          <Tag key={kind.id} active={selected === kind.id} onClick={() => onSelect(kind.id)}>
            <KindStamp kind={kind.id} size={21} className="qb-ktag-stamp" />
            <span className="qb-ktag-col">
              <b>{kind.label}</b>
              <span className="qb-ktag-sub">{kind.sub}</span>
            </span>
            <span className="qb-ktag-count">{kind.count.toLocaleString()}</span>
          </Tag>
        ))}
      </div>
    </>
  );
}
