/* Side Quests as a dense list: one row per quest, opened in the detail
   sheet. The poster wall stays one toggle away. */

import { KindStamp } from '@questboard/ui';
import { kindForVertical } from '@questboard/kinds';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { questPay, remotePlaceLabel } from '@/utils/board-card';
import { postedAgoLabel } from '@/utils/job-trust';
import type { ApplicationResponse } from '@/types/application';
import '@/features/board/quest-list.css';

export interface QuestRowModel {
  id: number;
  title: string;
  kind: string;
  kindLabel: string;
  source: string;
  place: string;
  pay: string | null;
  payUnit: string;
  posted: string;
}

function questPlace(app: ApplicationResponse): string {
  if (app.is_remote) return remotePlaceLabel(app.location);
  return (app.location || '').trim();
}

function postedShort(app: ApplicationResponse): string {
  const label = postedAgoLabel(
    app.date_posted,
    app.date_confidence,
    app.freshness_basis,
    app.date_updated,
  );
  return label ? label.replace(/^Posted /, '') : '';
}

export function questRowModel(app: ApplicationResponse, sourceLabel = ''): QuestRowModel {
  const kind = kindForVertical(app.vertical || '');
  const pay = questPay(app);
  return {
    id: app.id,
    title: app.job_title,
    kind: kind?.id ?? 'odd',
    kindLabel: kind?.label ?? '',
    source: sourceLabel || app.source || '',
    place: questPlace(app),
    pay: pay?.pay ?? null,
    payUnit: pay?.payUnit ?? '',
    posted: postedShort(app),
  };
}

export function QuestList({
  items,
  labels,
  onOpenDetail,
}: {
  items: ApplicationResponse[];
  labels: Record<string, string>;
  onOpenDetail: (app: ApplicationResponse) => void;
}) {
  return (
    <div className="qb-qlist">
      <div className="qb-qrow qb-qhead" aria-hidden="true">
        <span>kind</span>
        <span>quest</span>
        <span>place</span>
        <span className="qb-qpay">pay</span>
        <span className="qb-qposted">posted</span>
      </div>
      <ul>
        {items.map((app) => {
          const row = questRowModel(app, resolveSourceLabel(app.source, labels));
          return (
            <li key={row.id}>
              <button type="button" className="qb-qrow" onClick={() => onOpenDetail(app)}>
                <span className="qb-qkind">
                  <KindStamp kind={row.kind} size={18} />
                  <span>{row.kindLabel}</span>
                </span>
                <span className="qb-qtitle">
                  <b>{row.title}</b>
                  {row.source && <span className="qb-qsource">{row.source}</span>}
                </span>
                <span className="qb-qplace">{row.place}</span>
                <span className="qb-qpay">
                  {row.pay ? (
                    <>
                      {row.pay} {row.payUnit && <span className="qb-u">{row.payUnit}</span>}
                    </>
                  ) : (
                    <span className="qb-qnone">not stated</span>
                  )}
                </span>
                <span className="qb-qposted">{row.posted}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
