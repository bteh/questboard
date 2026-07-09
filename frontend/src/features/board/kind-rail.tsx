import { KindStamp } from '@questboard/ui';
import { useBoardSummary } from '@/hooks/use-board-summary';
import type { KindKey } from '@/features/board/kind-params';

/* The kind rail: a labeled, even grid of two-line tags (name over real
   examples), counts right-aligned, biggest supply first by registry order.
   Supply honesty: kinds with nothing live stay off the rail rather than
   posing as stocked shelves; Party always shows because it is user-made. */

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
}: {
  selected: KindKey;
  onSelect: (key: KindKey) => void;
}) {
  const { data } = useBoardSummary();
  if (!data) return null;
  const visible = data.kinds.filter((k) => k.count > 0 || k.id === 'party');
  return (
    <>
      <div className="qb-rail-top">
        <span className="qb-rail-label">Kinds of quests</span>
        <Tag active={selected === 'all'} onClick={() => onSelect('all')}>
          <span className="qb-ktag-dot" aria-hidden="true" />
          <span className="qb-ktag-col"><b>All quests</b></span>
          <span className="qb-ktag-count">{data.total.toLocaleString()}</span>
        </Tag>
        {data.new_today > 0 && (
          <span className="qb-rail-new">{data.new_today} new today</span>
        )}
      </div>
      <div className="qb-rail">
        {visible.map((kind) => (
          <Tag key={kind.id} active={selected === kind.id} onClick={() => onSelect(kind.id)}>
            <KindStamp kind={kind.id} size={21} className="qb-ktag-stamp" />
            <span className="qb-ktag-col">
              <b>{kind.label}</b>
              <span className="qb-ktag-sub">{kind.sub}</span>
            </span>
            <span className="qb-ktag-count">
              {kind.count > 0 ? kind.count.toLocaleString() : 'make your own'}
            </span>
          </Tag>
        ))}
      </div>
    </>
  );
}
