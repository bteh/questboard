import { KindStamp } from '@questboard/ui';
import { useBoardSummary } from '@/hooks/use-board-summary';
import { isCareerKind, questTotal, type KindKey } from '@/features/board/kind-params';

/* The kind rail: a labeled, even grid of two-line tags (name over real
   examples), counts right-aligned, biggest supply first by registry order.
   Supply honesty: kinds with nothing live stay off the rail rather than
   posing as stocked shelves; Party always shows because it is user-made.
   Career sits apart in its own Jobs lane so the quest grid stays quests. */

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
  const shown = data.kinds.filter((k) => k.count > 0 || k.id === 'party');
  const quests = shown.filter((k) => !isCareerKind(k.id));
  const jobs = data.kinds.filter((k) => isCareerKind(k.id) && k.count > 0);
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
            <span className="qb-ktag-count">
              {kind.count > 0 ? kind.count.toLocaleString() : 'make your own'}
            </span>
          </Tag>
        ))}
      </div>
      {jobs.length > 0 && (
        <div className="qb-rail-work">
          <span className="qb-rail-label qb-rail-work-label">Looking for a job?</span>
          <div className="qb-rail">
            {jobs.map((kind) => (
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
        </div>
      )}
    </>
  );
}
