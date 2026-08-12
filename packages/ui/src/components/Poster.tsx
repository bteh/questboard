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

export interface PosterLogoWellProps {
  src?: string;
  /** monogram fallback, deterministic from the company name */
  initial?: string;
  color?: string;
}

/* Career posters: a fixed square tile beside the title so logos survive the
   cream paper and the layout never shifts. A failed or missing image falls
   to the monogram. alt stays empty: the company name is adjacent text. */
function LogoWell({ src, initial, color }: PosterLogoWellProps) {
  const [failed, setFailed] = useState(false);
  return (
    <span className="qb-p-well" aria-hidden="true">
      {src && !failed ? (
        <img
          src={src}
          alt=""
          width={30}
          height={30}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : initial ? (
        <span className="qb-p-well-mono" style={{ background: color }}>
          {initial}
        </span>
      ) : null}
    </span>
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
  /** career posters: the fixed logo tile beside the title */
  logoWell?: PosterLogoWellProps;
  /** where, e.g. "Chicago" or "remote" */
  place?: string;
  /** honest freshness, e.g. "first seen Jul 2" or "posted yesterday" */
  posted?: string;
  /** landed after the reader's last visit; a quiet text label, never a badge */
  newHere?: boolean;
  /** the scannable one-liner, from the posting's own text */
  desc?: string;
  /** what to bring; a node so the fit line can carry an inline action */
  bring: ReactNode;
  /** Side Quests name this plainly; career posters keep the original label. */
  bringLabel?: string;
  /** true when the quest needs nothing: the line gets the friendly check */
  bringFree?: boolean;
  /** the honest trap, when the kind or the data carries one */
  catchLine?: string;
  /** referral disclosure; render only when the link actually carries a live tag */
  disclosure?: string;
  /** flavor tags: time and effort only, two at most */
  tags?: string[];
  /** setup/application effort; never the time to complete or win the quest */
  effort?: {
    level: 'quick' | 'some_prep' | 'involved';
    label: string;
    time: string;
    typical?: boolean;
  };
  /** the connected assistant's fit verdict for this row, from its last run */
  fitBadge?: { label: string; verdict: 'strong' | 'good' | 'reach' | 'skip' };
  /** fast offline skill-coverage hint, shown until the agent's verdict lands */
  skillBadge?: { label: string; band: 'close' | 'partial' | 'weak' };
  pay?: string;
  payUnit?: string;
  /** e.g. "Applied, Jun 30"; wins over clippedDate */
  applied?: string;
  clippedDate?: string;
  /** opens Your log; when set, the clipped stamp names where the row went
      and becomes the door there. Absent, the stamp stays a plain label. */
  onOpenLog?: () => void;
  /** stable per-posting tilt, degrees; keep within about ±1.5 */
  rotateDeg?: number;
  showExplain?: boolean;
  onClip?: () => void;
  onExplain?: () => void;
  /** opens the poster's own detail sheet (the Jobs lane) */
  onDetails?: () => void;
}

export function Poster({
  kind,
  title,
  href = '#',
  giver,
  giverLogoUrl,
  logoWell,
  place,
  posted,
  newHere,
  desc,
  bring,
  bringLabel = 'bring',
  bringFree,
  catchLine,
  disclosure,
  tags = [],
  effort,
  fitBadge,
  skillBadge,
  pay,
  payUnit,
  applied,
  clippedDate,
  onOpenLog,
  rotateDeg = 0,
  showExplain,
  onClip,
  onExplain,
  onDetails,
}: PosterProps) {
  const meta = kindById(kind);
  const hue = meta?.hue ?? 'var(--ink)';
  return (
    <div className="qb-slot" style={{ ['--qb-hue' as string]: hue }}>
      <span className="qb-pin" aria-hidden="true" />
      <article className="qb-poster" style={{ ['--qb-rot' as string]: `${rotateDeg}deg` }}>
        {applied ? (
          <span className="qb-poster-clip qb-poster-clipped">{applied}</span>
        ) : clippedDate ? (
          onOpenLog ? (
            <button
              type="button"
              className="qb-poster-clip qb-poster-clipped qb-poster-clip-log"
              onClick={onOpenLog}
            >
              {`Clipped, ${clippedDate} · in your log`}
            </button>
          ) : (
            <span className="qb-poster-clip qb-poster-clipped">{`Clipped, ${clippedDate}`}</span>
          )
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
          {(posted || newHere) && (
            <span className="qb-p-posted">
              {posted}
              {posted && newHere ? ' · ' : ''}
              {newHere && <span className="qb-p-new">new here</span>}
            </span>
          )}
        </div>
        {(fitBadge || skillBadge) && (
          <div className="qb-p-fitrow">
            {fitBadge ? (
              <span className={cx('qb-p-fit', `qb-p-fit-${fitBadge.verdict}`)}>{fitBadge.label}</span>
            ) : skillBadge ? (
              <span className={cx('qb-p-skill', `qb-p-skill-${skillBadge.band}`)}>{skillBadge.label}</span>
            ) : null}
          </div>
        )}
        {logoWell ? (
          <div className="qb-p-titlerow">
            <LogoWell {...logoWell} />
            <h3 className="qb-p-title">
              <a href={href} target="_blank" rel="noreferrer">{title}</a>
            </h3>
          </div>
        ) : (
          <h3 className="qb-p-title">
            <a href={href} target="_blank" rel="noreferrer">{title}</a>
          </h3>
        )}
        <div className="qb-p-giver">
          <GiverLogo src={giverLogoUrl} alt={giver} />
          {giver}
          {place ? ` · ${place}` : ''}
          {onDetails && (
            <button type="button" className="qb-p-explain" onClick={onDetails}>
              details
            </button>
          )}
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
        {effort && (
          <div className="qb-p-effort" aria-label={`Application effort: ${effort.label}, ${effort.time}`}>
            <span className="qb-p-effort-label">effort</span>
            <span className="qb-p-effort-marks" aria-hidden="true">
              {[1, 2, 3].map((mark) => (
                <i
                  key={mark}
                  className={cx(
                    mark === 1 ||
                      (mark === 2 && effort.level !== 'quick') ||
                      (mark === 3 && effort.level === 'involved')
                      ? 'is-filled'
                      : undefined,
                  )}
                />
              ))}
            </span>
            <span className="qb-p-effort-body">
              <strong>{effort.label}</strong> · {effort.time}
              {effort.typical && <em> · typical</em>}
            </span>
          </div>
        )}
        <div className={cx('qb-p-bring', effort && 'qb-p-bring-after-effort', bringFree && 'qb-p-bring-free')}>
          <span className="qb-p-bring-label">{bringLabel}</span>
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
