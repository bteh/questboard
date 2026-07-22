/* The wall of posters, extracted from routes/board.tsx so the Jobs lane can
   group loaded rows around the reader's last visit. Pure render: the route
   owns the page queries and hands the loaded rows in. */

import { Fragment, type ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Poster } from '@questboard/ui';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { useUpdateStatus } from '@/hooks/use-applications';
import { CLIP_STATUS } from '@/utils/board-card';
import { fitDigest, fitGroups, toPoster } from '@/features/board/poster-model';
import { isNewSince, splitBySince } from '@/features/board/new-since';
import { decoratePosterLink } from '@/monetization/affiliate';
import type { ApplicationResponse } from '@/types/application';

interface PosterWallProps {
  items: ApplicationResponse[];
  labels: Record<string, string>;
  /** the Jobs lane's frozen last-visit cutoff; rows after it read "new here" */
  cutoff?: string | null;
  /** split the wall at the cutoff with the since/earlier rule */
  grouped?: boolean;
  /** group by the assistant's verdicts: digest line, labeled rules, skip fold */
  fitGrouped?: boolean;
  onOpenSheet: (app: ApplicationResponse) => void;
  onExplain: (app: ApplicationResponse) => void;
  onOpenDetail?: (app: ApplicationResponse) => void;
}

/* the rule between the two groups; column-span keeps it across the felt */
function SinceRule() {
  return (
    <div className="qb-since-rule" role="separator">
      <span>since your last visit</span>
      <span className="qb-since-line" aria-hidden="true" />
      <span>earlier</span>
    </div>
  );
}

/* one labeled rule per verdict group, in the since-rule's quiet grammar */
function FitRule({ label }: { label: string }) {
  return (
    <div className="qb-fit-rule" role="separator" aria-label={label}>
      <span>{label}</span>
      <span className="qb-since-line" aria-hidden="true" />
    </div>
  );
}

export function PosterWall({
  items,
  labels,
  cutoff,
  grouped,
  fitGrouped,
  onOpenSheet,
  onExplain,
  onOpenDetail,
}: PosterWallProps) {
  const updateStatus = useUpdateStatus();
  const navigate = useNavigate();

  function renderPoster(app: ApplicationResponse) {
    const poster = toPoster(app, resolveSourceLabel(app.source, labels));
    const { card } = poster;
    /* render edge only: decoration runs after ordering, so the bounty
       can never touch what shows or the order */
    const link = decoratePosterLink(card.href, Boolean(poster.copy.catchLine));
    /* career rows bring their real resume fit; the kind template yields */
    const bring: ReactNode = poster.hasFit ? (
      <>
        a resume. this one covers {card.fit!.strong} of the {card.fit!.total} things they ask for
        {card.fit!.missing > 0 && (
          <>
            {' '}
            <button
              type="button"
              className="qb-textlink"
              style={{ fontSize: 'inherit' }}
              onClick={() => onOpenSheet(app)}
            >
              see the {card.fit!.missing} missing
            </button>
          </>
        )}
      </>
    ) : (
      poster.copy.bring
    );
    return (
      <Poster
        key={app.id}
        kind={poster.kind}
        title={card.title}
        href={link.href}
        giver={card.meta}
        giverLogoUrl={poster.logoUrl}
        logoWell={poster.logoWell}
        newHere={cutoff ? isNewSince(app.date_found, cutoff) : false}
        desc={poster.desc}
        bring={bring}
        bringFree={poster.copy.bringFree && !poster.hasFit}
        catchLine={poster.copy.catchLine}
        disclosure={link.disclosure}
        tags={poster.tags}
        fitBadge={poster.fitBadge}
        skillBadge={poster.skillBadge}
        pay={card.pay}
        payUnit={card.payUnit}
        applied={card.applied}
        clippedDate={card.clippedDate}
        onOpenLog={() => navigate({ to: '/log' })}
        rotateDeg={poster.rotateDeg}
        showExplain
        onExplain={() => onExplain(app)}
        onDetails={onOpenDetail ? () => onOpenDetail(app) : undefined}
        onClip={() => updateStatus.mutate({ id: app.id, data: { status: CLIP_STATUS } })}
      />
    );
  }

  if (fitGrouped) {
    const wall = fitGroups(items);
    const digest = fitDigest(wall);
    return (
      <>
        {digest && <p className="qb-fit-digest">{digest}</p>}
        {wall.groups.map((group) => (
          <Fragment key={group.verdict}>
            <FitRule label={`${group.label} (${group.items.length})`} />
            {group.items.map(renderPoster)}
          </Fragment>
        ))}
        {/* rows the assistant never judged: after the groups, under their own
            rule so they never read as part of the last verdict */}
        {wall.unranked.length > 0 && wall.groups.length > 0 && (
          <FitRule label={`Not ranked (${wall.unranked.length})`} />
        )}
        {wall.unranked.map(renderPoster)}
        {wall.skips.length > 0 && (
          <details className="qb-skip-fold">
            <summary>Skipped by your assistant ({wall.skips.length})</summary>
            <div className="qb-skip-posters">{wall.skips.map(renderPoster)}</div>
          </details>
        )}
      </>
    );
  }
  if (grouped && cutoff) {
    const { fresh, earlier } = splitBySince(items, cutoff);
    return (
      <>
        {fresh.map(renderPoster)}
        {fresh.length > 0 && earlier.length > 0 && <SinceRule />}
        {earlier.map(renderPoster)}
      </>
    );
  }
  return <>{items.map(renderPoster)}</>;
}
