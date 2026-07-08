import type { ReactNode } from 'react';
import { cx } from '../cx';

/**
 * The one result block behind "Explain this". It upgrades in place (bump
 * `swap` to remount with the swap animation); there are never two stacked
 * answers. The method line under the text is how a read self-describes.
 */
export interface ExplainNoteProps {
  /** The serif header over the read. */
  head?: string;
  body: ReactNode;
  /** e.g. "Pulled from the posting's own words." */
  method: string;
  /** Bump to retrigger the in-place upgrade animation; 0 means no animation. */
  swap?: number;
}

export function ExplainNote({ head = 'In plain words', body, method, swap = 0 }: ExplainNoteProps) {
  return (
    <div key={swap} className={cx('qb-note', swap > 0 && 'qb-xswap')}>
      <div className="qb-xhead">{head}</div>
      <div>{body}</div>
      <div className="qb-xmethod">{method}</div>
    </div>
  );
}

/**
 * The quiet card that appears UNDER an already-delivered answer. The same
 * frame also carries the progress line and the done note, so nothing ever
 * jumps position.
 */
export interface ConsentCardProps {
  title?: string;
  body?: ReactNode;
  /** action row, e.g. the start and not-now buttons */
  actions?: ReactNode;
  foot?: ReactNode;
}

export function ConsentCard({ title, body, actions, foot }: ConsentCardProps) {
  const footOnly = !title && !body && !actions;
  return (
    <div className="qb-xconsent">
      {title && <div className="qb-xc-title">{title}</div>}
      {body && <div className="qb-xc-body">{body}</div>}
      {actions && <div className="qb-xc-row">{actions}</div>}
      {foot && (
        <div className="qb-xc-foot" style={footOnly ? { marginTop: 0 } : undefined}>
          {foot}
        </div>
      )}
    </div>
  );
}
