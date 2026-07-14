import { useState, type ReactNode } from 'react';
import { kindById } from '@questboard/kinds';
import { cx } from '../cx';
import { KindStamp } from './KindStamp';

/* A small company/source logo for the giver line. Hides itself if the image
   fails to load, so a poster with no resolvable logo just reads as before. */
function GiverLogo({ src, alt }: { src?: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;
  return (
    <img
      className="qb-p-logo"
      src={src}
      alt=""
      aria-label={alt}
      width={18}
      height={18}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

/* A quest poster: cream paper pinned to the felt. The pin stays upright in
   the slot while the paper tilts; the reward rides a tear-off tab; the
   bring line states the kind's true requirement and the catch names the
   honest trap when there is one. Pay renders only when the poster wrote it. */

export interface PosterProps {
  kind: string;
  title: string;
  href?: string;
  /** who posted it, e.g. "Focusgroups Org" */
  giver: string;
  /** optional company/source logo shown before the giver name */
  giverLogoUrl?: string;
  /** where, e.g. "Chicago" or "remote" */
  place?: string;
  /** honest freshness, e.g. "first seen Jul 2" or "posted yesterday" */
  posted?: string;
  /** the scannable one-liner, from the posting's own text */
  desc?: string;
  /** what to bring; a node so the fit line can carry an inline action */
  bring: ReactNode;
  /** true when the quest needs nothing: the line gets the friendly check */
  bringFree?: boolean;
  /** the honest trap, when the kind or the data carries one */
  catchLine?: string;
  /** referral disclosure; render only when the link actually carries a live tag */
  disclosure?: string;
  /** flavor tags: time and effort only, two at most */
  tags?: string[];
  pay?: string;
  payUnit?: string;
  /** e.g. "Applied, Jun 30"; wins over clippedDate */
  applied?: string;
  clippedDate?: string;
  /** stable per-posting tilt, degrees; keep within about ±1.5 */
  rotateDeg?: number;
  showExplain?: boolean;
  onClip?: () => void;
  onExplain?: () => void;
}

export function Poster({
  kind,
  title,
  href = '#',
  giver,
  giverLogoUrl,
  place,
  posted,
  desc,
  bring,
  bringFree,
  catchLine,
  disclosure,
  tags = [],
  pay,
  payUnit,
  applied,
  clippedDate,
  rotateDeg = 0,
  showExplain,
  onClip,
  onExplain,
}: PosterProps) {
  const meta = kindById(kind);
  const hue = meta?.hue ?? 'var(--ink)';
  return (
    <div className="qb-slot" style={{ ['--qb-hue' as string]: hue }}>
      <span className="qb-pin" aria-hidden="true" />
      <article className="qb-poster" style={{ ['--qb-rot' as string]: `${rotateDeg}deg` }}>
        {clippedDate || applied ? (
          <span className="qb-poster-clip qb-poster-clipped">{applied ?? `Clipped, ${clippedDate}`}</span>
        ) : (
          onClip && (
            <button type="button" className="qb-poster-clip" onClick={onClip}>
              Clip
            </button>
          )
        )}
        <div className="qb-p-head">
          <KindStamp kind={kind} size={24} />
          <span className="qb-p-kind" style={{ color: hue }}>{meta?.label ?? kind}</span>
          {posted && <span className="qb-p-posted">{posted}</span>}
        </div>
        <h3 className="qb-p-title">
          <a href={href} target="_blank" rel="noreferrer">{title}</a>
        </h3>
        <div className="qb-p-giver">
          <GiverLogo src={giverLogoUrl} alt={giver} />
          {giver}
          {place ? ` · ${place}` : ''}
          {showExplain && onExplain && (
            <button type="button" className="qb-p-explain" onClick={onExplain}>
              explain
            </button>
          )}
        </div>
        {desc && <p className="qb-p-desc">{desc}</p>}
        {tags.length > 0 && (
          <div className="qb-p-tags">
            {tags.map((tag) => (
              <span key={tag} className="qb-p-tag">{tag}</span>
            ))}
          </div>
        )}
        <div className={cx('qb-p-bring', bringFree && 'qb-p-bring-free')}>
          <span className="qb-p-bring-label">bring</span>
          <span className="qb-p-bring-body">{bring}</span>
        </div>
        {catchLine && (
          <div className="qb-p-catch">
            <span className="qb-p-catch-label">the catch</span>
            {catchLine}
          </div>
        )}
        <div className="qb-p-tear">
          <div className="qb-p-reward">
            <span className="qb-p-reward-label">reward</span>
            {pay ? (
              <span className="qb-p-reward-value">
                {pay}
                {payUnit && <em> {payUnit}</em>}
              </span>
            ) : (
              <span className="qb-p-reward-value qb-p-reward-unstated">not stated</span>
            )}
          </div>
          <a className="qb-p-take" href={href} target="_blank" rel="noreferrer">
            take it →
          </a>
        </div>
        {disclosure && <p className="qb-p-disclosure">{disclosure}</p>}
      </article>
    </div>
  );
}
