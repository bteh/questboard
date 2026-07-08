import { useRef, type ReactNode } from 'react';
import { verticals, type Vertical } from '../tokens';
import { cx } from '../cx';
import { Stamp } from './Stamp';

export interface QuestCardParty {
  total: number;
  /* initials of the seats already filled */
  seated: string[];
  /* set when the party is full and a day is picked, e.g. "Sat Jul 18" */
  date?: string;
}

export interface QuestCardProps {
  vertical: Exclude<Vertical, 'personal'>;
  title: string;
  href?: string;
  meta: string;
  /* usually a string; a node lets the needs line carry an inline action */
  needs: ReactNode;
  /* the small mono barrier word, e.g. "prep" */
  bar?: string;
  firstQuest?: boolean;
  /* omit both pay fields when the posting states no pay; nothing renders */
  pay?: string;
  payUnit?: string;
  /* e.g. "Applied, Jun 30"; wins over clippedDate */
  applied?: string;
  /* set once the quest is clipped, e.g. "Jul 7" */
  clippedDate?: string;
  party?: QuestCardParty;
  showExplain?: boolean;
  onClip?: () => void;
  onMakeParty?: () => void;
  onExplain?: () => void;
}

function partyLabel(party: QuestCardParty): string {
  return party.seated.length === party.total && party.date
    ? `party full, on for ${party.date}`
    : `party of ${party.total}, ${party.seated.length} in`;
}

export function QuestCard({
  vertical,
  title,
  href = '#',
  meta,
  needs,
  bar,
  firstQuest = false,
  pay,
  payUnit,
  applied,
  clippedDate,
  party,
  showExplain = false,
  onClip,
  onMakeParty,
  onExplain,
}: QuestCardProps) {
  const v = verticals[vertical];
  /* clipped after mount gets the press-in animation; already-clipped does not */
  const stampedAtMount = useRef(Boolean(applied || clippedDate));

  let right;
  if (party) {
    right = (
      <button type="button" className="qb-clip" style={{ color: 'var(--wine)' }} onClick={onMakeParty}>
        make a party
      </button>
    );
  } else if (applied) {
    right = <span className="qb-applied-stamp">{applied}</span>;
  } else if (clippedDate) {
    right = (
      <span
        className={cx('qb-applied-stamp', !stampedAtMount.current && 'qb-pressin')}
        style={{ color: v.hue, borderColor: v.hue }}
      >
        Clipped, {clippedDate}
      </span>
    );
  } else {
    right = (
      <button type="button" className="qb-clip" onClick={onClip} aria-label="Clip this quest">
        Clip
      </button>
    );
  }

  return (
    <article className="qb-qcard">
      <div className={cx('qb-band', `qb-${v.bandClass}`)}>
        <Stamp vertical={vertical} size={16} inheritColor />
        <span>{v.label}</span>
      </div>
      <div className="qb-qbody">
        <div className="qb-qtitle">
          <a
            href={href}
            target={href.startsWith('http') ? '_blank' : undefined}
            rel={href.startsWith('http') ? 'noreferrer' : undefined}
          >
            {title}
          </a>
        </div>
        <div className="qb-meta">
          {meta}
          {firstQuest && (
            <>
              {' '}
              <span className="qb-fq" style={{ color: v.hue }}>
                first quest
              </span>
            </>
          )}
        </div>
        <div className="qb-needs">
          {needs}
          {bar && (
            <>
              {' '}
              <span className="qb-bword">{bar}</span>
            </>
          )}
        </div>
        {party && (
          <div className="qb-partyline">
            <span className="qb-seats">
              {Array.from({ length: party.total }, (_, i) => {
                const initial = party.seated[i] ?? '';
                return (
                  <span key={i} className={cx('qb-seat', initial !== '' && 'qb-in')}>
                    {initial}
                  </span>
                );
              })}
            </span>
            {partyLabel(party)}
          </div>
        )}
      </div>
      <div className="qb-qfoot">
        {pay && (
          <span className="qb-pay">
            {pay} {payUnit && <span className="qb-u">{payUnit}</span>}
          </span>
        )}
        {showExplain && !applied && (
          <button type="button" className="qb-clip qb-xbtn" onClick={onExplain}>
            Explain this
          </button>
        )}
        {right}
      </div>
    </article>
  );
}
