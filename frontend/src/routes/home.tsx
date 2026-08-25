import { createRoute, Link } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import { Poster, SageButton, SplitFlap } from '@questboard/ui';
import { useApplications, useUpdateStatus } from '@/hooks/use-applications';
import { useBoardSummary } from '@/hooks/use-board-summary';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { CLIP_STATUS } from '@/utils/board-card';
import { ALL_VERTICALS, verticalParams } from '@/utils/board-verticals';
import { backendDownLine } from '@/features/board/backend-down';
import { checkedAgoLabel } from '@/features/board/freshness';
import { toPoster } from '@/features/board/poster-model';
import { logStripTiles, pickBounty } from '@/components/home/home-logic';
import type { ApplicationResponse } from '@/types/application';
import '@/components/home/home.css';

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/home',
  component: HomePage,
});

/* The returning reader's front page, in the felt language the landing and
   the board speak: live counts up top, ONE real poster pinned to a strip
   of felt as today's bounty, and the door to the board. Every number is a
   live query total or a field the source stated. */

/* The home horizon: the masthead's closing edge. */
function HomeHorizon() {
  return (
    <svg
      className="qb-home-horizon"
      viewBox="0 0 1032 128"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
    >
      <g stroke="currentColor" fill="none" strokeWidth="1.6" opacity=".3" strokeLinecap="round">
        <path d="M712 66 a34 34 0 0 1 56 -3" />
        <path d="M704 51 l-12 -7 M716 35 l-9 -10 M734 25 l-5 -12 M754 21 l0 -13 M774 24 l4 -12 M791 34 l9 -10 M803 50 l12 -7" />
      </g>
      <path
        d="M-10 78 C 110 58, 250 66, 380 75 S 640 90, 800 72 S 950 60, 1042 70 L 1042 138 L -10 138 Z"
        fill="var(--ground)"
      />
      <path
        d="M-10 78 C 110 58, 250 66, 380 75 S 640 90, 800 72 S 950 60, 1042 70"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        opacity=".26"
        strokeLinecap="round"
      />
      <g stroke="currentColor" strokeWidth="1" opacity=".14" strokeLinecap="round">
        <path d="M120 70 l-11 8 M164 68 l-11 8 M208 68 l-11 8 M836 78 l-11 8 M880 72 l-11 8 M924 68 l-11 8" />
      </g>
      <path
        d="M-10 110 C 170 94, 360 106, 540 112 S 830 114, 1042 100 L 1042 138 L -10 138 Z"
        fill="var(--ground)"
      />
      <path
        d="M-10 110 C 170 94, 360 106, 540 112 S 830 114, 1042 100"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        opacity=".34"
        strokeLinecap="round"
      />
      <g stroke="currentColor" strokeWidth="1" opacity=".16" strokeLinecap="round">
        <path d="M70 106 l-12 9 M118 104 l-12 9 M166 103 l-12 9 M382 112 l-12 9 M430 114 l-12 9 M600 120 l-12 9 M648 120 l-12 9 M920 108 l-12 9 M968 106 l-12 9" />
      </g>
      <g
        stroke="currentColor"
        fill="none"
        strokeWidth="1.6"
        opacity=".4"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M252 104 V 82 M252 85 h15 l5 4 -5 4 h-15 z" />
      </g>
      <g stroke="currentColor" fill="none" strokeWidth="1.4" opacity=".25" strokeLinecap="round">
        <path d="M556 34 q7 -8 14 0 q7 -8 14 0" />
        <path d="M610 20 q5 -6 10 0 q5 -6 10 0" />
      </g>
    </svg>
  );
}

/* Today's bounty: one REAL poster through the board's own model, same as
   the landing hero. The fit sheet lives in the app, so a career fit line
   renders as plain text here. */
function BountyPoster({ app, labels }: { app: ApplicationResponse; labels: Record<string, string> }) {
  const updateStatus = useUpdateStatus();
  const poster = toPoster(app, resolveSourceLabel(app.source, labels));
  const { card } = poster;
  const bring = poster.hasFit
    ? `a resume. this one covers ${card.fit!.strong} of the ${card.fit!.total} things they ask for`
    : poster.copy.bring;
  return (
    <Poster
      kind={poster.kind}
      title={card.title}
      href={card.href}
      giver={card.meta}
      desc={poster.desc}
      bring={bring}
      bringFree={poster.copy.bringFree && !poster.hasFit}
      catchLine={poster.copy.catchLine}
      tags={poster.tags}
      pay={card.pay}
      payUnit={card.payUnit}
      applied={card.applied}
      clippedDate={card.clippedDate}
      rotateDeg={poster.rotateDeg}
      onClip={() => updateStatus.mutate({ id: app.id, data: { status: CLIP_STATUS } })}
    />
  );
}

function useTotal(filters: Parameters<typeof useApplications>[0]): number | undefined {
  /* home reads the felt, not the log: hosted mode adds the shared pool */
  return useApplications({ ...filters, page: 1, page_size: 1, scope: 'board' }).data?.total;
}

function HomePage() {
  const labels = useSourceLabels();
  const summary = useBoardSummary().data;

  /* the lede: the same summary the board head and rail read, one number
     everywhere; the pay floor stays a live probe */
  const boardTotal = summary?.total;
  const pay500Total = useTotal({ ...verticalParams('all'), salary_min: 500 });
  const checkedAgo = checkedAgoLabel(summary?.checked_at);

  /* the flaps: the board rail's own new-today count, and rows whose taping
     or session date falls inside the next 7 days, any lane */
  const eventsWeek = useTotal({
    vertical: ALL_VERTICALS,
    upcoming_only: true,
    event_within_days: 7,
  });

  /* the bounty pool: rows with a provable post date in the last 3 days;
     honest fallback to the newest stated-pay row (pickBounty) */
  const newest = useApplications({
    ...verticalParams('all'),
    sort_by: 'date_found',
    sort_order: 'desc',
    page: 1,
    page_size: 24,
    scope: 'board',
  });
  const recent = useApplications({
    ...verticalParams('all'),
    posted_within_days: 3,
    sort_by: 'date_found',
    sort_order: 'desc',
    page: 1,
    page_size: 100,
    scope: 'board',
  });

  /* the log strip counts, from real statuses */
  const applied = useTotal({ vertical: ALL_VERTICALS, status: 'applied' });
  const interviewing = useTotal({ vertical: ALL_VERTICALS, status: 'interviewing' });
  const offers = useTotal({ vertical: ALL_VERTICALS, status: 'offer' });

  const bounty = pickBounty(recent.data?.items ?? [], newest.data?.items ?? []);
  const tiles = logStripTiles({ applied, interviewing, offers });

  return (
    <>
      <div className="qb-mast">
        <div className="qb-hwrap qb-mast-inner">
          {/* a fresh install has zero rows, and "0 quests. 0 pay $500."
              reads as a broken product. Before the first sweep the honest
              lede is that the board is stocking itself. */}
          <h1 className="qb-lede">
            {boardTotal === 0 ? (
              summary?.checked_at ? (
                'The board is empty right now. Open it to check the sources.'
              ) : (
                'The board is stocking itself. The first quests land in about a minute.'
              )
            ) : (
              boardTotal !== undefined &&
              pay500Total !== undefined && (
                <>
                  <span className="qb-num">{boardTotal}</span> quests on the board.{' '}
                  <span className="qb-num">{pay500Total}</span> pay{' '}
                  <span className="qb-num">$500</span> or more.
                </>
              )
            )}
          </h1>
          <p className="qb-msub">
            {checkedAgo ? `${checkedAgo[0].toUpperCase()}${checkedAgo.slice(1)}. ` : ''}
            Every listing links straight to the source.
          </p>
          <p className="qb-msub">
            Never done any of this? Most quests here need nothing you don't already have.{' '}
            <Link to="/board" className="qb-textlink">
              Start here
            </Link>
          </p>
          <div className="qb-flaprow">
            {summary !== undefined && (
              <SplitFlap
                value={String(summary.new_today)}
                caption="new today"
                srLabel={`${summary.new_today} quests new today.`}
              />
            )}
            {eventsWeek !== undefined && (
              <SplitFlap
                value={String(eventsWeek)}
                caption="tapings and sessions this week"
                srLabel={`${eventsWeek} tapings and sessions this week.`}
              />
            )}
          </div>
        </div>
        <div className="qb-hwrap">
          <HomeHorizon />
        </div>
      </div>

      <div className="qb-hwrap">
        {bounty && (
          <section className="qb-chapter" style={{ marginTop: 56 }}>
            <h2 className="qb-ch-title">
              {bounty.fallback ? 'Newest with stated pay' : "Today's bounty"}
            </h2>
            <div className="qb-home-felt">
              <BountyPoster app={bounty.app} labels={labels} />
            </div>
          </section>
        )}

        <section className="qb-chapter qb-home-door">
          <Link to="/board">
            <SageButton big>Open the board</SageButton>
          </Link>
          {newest.isError && (
            <p style={{ fontSize: 14.5, color: 'var(--soft)', margin: '16px 0 0' }}>
              {backendDownLine()}
            </p>
          )}
        </section>

        {tiles.length > 0 && (
          <section className="qb-chapter" style={{ marginBottom: 72 }}>
            <div className="qb-logstrip">
              {tiles.map((tile, i) => (
                <div key={tile.label} className={i === 0 ? 'qb-logstat qb-senior' : 'qb-logstat'}>
                  <div className="qb-lab">{tile.label}</div>
                  <div className="qb-val">{tile.count}</div>
                </div>
              ))}
            </div>
          </section>
        )}
        {tiles.length === 0 && <div style={{ height: 72 }} aria-hidden="true" />}
      </div>
    </>
  );
}
