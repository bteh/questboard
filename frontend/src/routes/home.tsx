import { useState } from 'react';
import { createRoute, Link } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import { SplitFlap, StampDefs, TextLink } from '@questboard/ui';
import { LanePostmark, LaneStamp, laneDisplay } from '@/components/shared/lane-display';
import { useApplications, useUpdateStatus } from '@/hooks/use-applications';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { CLIP_STATUS, shortDate, toBoardCard } from '@/utils/board-card';
import { ALL_VERTICALS, verticalParams } from '@/utils/board-verticals';
import { CredoLine } from '@/components/home/credo-line';
import { logStripTiles, pickBounty, pickNewRows } from '@/components/home/home-logic';
import type { ApplicationResponse } from '@/types/application';
import '@/components/home/home.css';

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/home',
  component: HomePage,
});

/* The masthead home, ported from packages/ui/reference/quest-board-mock.html
   (#page-home): the returning reader's front page. Every number on it is a
   live query total or a field the source stated; the flaps and the credo
   line are the page's two motions, the postmark press on Clip the third. */

const QUEST_VERTICALS = 'camera,study,lens';

/* The mock's home horizon, verbatim: the masthead's closing edge. */
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

/* Today's bounty: the mock's featured card, filled by a real row. */
function BountyCard({ app, labels }: { app: ApplicationResponse; labels: Record<string, string> }) {
  const updateStatus = useUpdateStatus();
  const card = toBoardCard(app, resolveSourceLabel(app.source, labels));
  const v = laneDisplay(card.vertical);
  /* clipped after mount gets the press; already-clipped renders settled */
  const [stampedAtMount] = useState(() => Boolean(card.applied || card.clippedDate));
  return (
    <article className="qb-feat">
      <div className={`qb-band qb-${v.bandClass}`}>
        <LaneStamp vertical={card.vertical} size={18} inheritColor />
        <span>{v.label}</span>
      </div>
      <div className="qb-feat-body">
        <div className="qb-feat-left">
          <h3>
            {card.href ? (
              <a href={card.href} target="_blank" rel="noreferrer">
                {card.title}
              </a>
            ) : (
              card.title
            )}
          </h3>
          <div className="qb-feat-meta">{card.meta}</div>
          {card.needs && <div className="qb-feat-needs">{card.needs}</div>}
          <div className="qb-feat-actions">
            {card.href && <TextLink href={card.href}>Apply at source</TextLink>}
            {card.applied ? (
              <span className="qb-applied-stamp">{card.applied}</span>
            ) : card.clippedDate ? (
              <span className="qb-feat-meta">Clipped, {card.clippedDate}</span>
            ) : (
              <button
                type="button"
                className="qb-clip"
                aria-label="Clip this quest"
                onClick={() => updateStatus.mutate({ id: app.id, data: { status: CLIP_STATUS } })}
              >
                Clip
              </button>
            )}
          </div>
        </div>
        <div className="qb-feat-pay">
          {card.clippedDate && !card.applied && (
            <LanePostmark vertical={card.vertical} press={!stampedAtMount} />
          )}
          <div className="qb-p">{card.pay}</div>
          {card.payUnit && <div className="qb-u">{card.payUnit}</div>}
        </div>
      </div>
    </article>
  );
}

/* One row of "New on the board", the mock's ledger-row grammar. */
function HomeRow({ app, labels }: { app: ApplicationResponse; labels: Record<string, string> }) {
  const updateStatus = useUpdateStatus();
  const card = toBoardCard(app, resolveSourceLabel(app.source, labels));
  const [stampedAtMount] = useState(() => Boolean(card.applied || card.clippedDate));
  return (
    <div className="qb-hrow">
      <div className="qb-stampcell">
        <LaneStamp vertical={card.vertical} size={34} />
      </div>
      <div className="qb-hmain">
        <div className="qb-htitle">
          {card.href ? (
            <a href={card.href} target="_blank" rel="noreferrer">
              {card.title}
            </a>
          ) : (
            card.title
          )}
        </div>
        <div className="qb-hmeta">
          {card.meta}
          {card.clippedDate ? `, clipped ${card.clippedDate}` : ''}
          {card.firstQuest && (
            <>
              {' '}
              <span className="qb-fq" style={{ color: laneDisplay(card.vertical).hue }}>
                first quest
              </span>
            </>
          )}
        </div>
      </div>
      <div className="qb-hneeds">
        {card.applied ? <span className="qb-applied-stamp">{card.applied}</span> : card.needs}
      </div>
      <div className="qb-paycell">
        {card.pay ? (
          <span className="qb-hpay">
            {card.pay} {card.payUnit && <span className="qb-u">{card.payUnit}</span>}
          </span>
        ) : (
          <span className="qb-hpay qb-none">pay not stated</span>
        )}
      </div>
      {card.applied || card.clippedDate ? (
        <span className="qb-clipcell">
          <LanePostmark vertical={card.vertical} press={!stampedAtMount} />
        </span>
      ) : (
        <button
          type="button"
          className="qb-clip"
          aria-label="Clip this quest"
          onClick={() => updateStatus.mutate({ id: app.id, data: { status: CLIP_STATUS } })}
        >
          Clip
        </button>
      )}
    </div>
  );
}

function useTotal(filters: Parameters<typeof useApplications>[0]): number | undefined {
  return useApplications({ ...filters, page: 1, page_size: 1 }).data?.total;
}

function HomePage() {
  const labels = useSourceLabels();

  /* the lede's totals: the same queries the board's All chip and pay-floor
     input count, page_size 1, never hardcoded */
  const boardTotal = useTotal(verticalParams('all'));
  const pay500Total = useTotal({ ...verticalParams('all'), salary_min: 500 });

  /* the flaps: rows provably posted in the last 24 hours, and quest rows
     whose taping or session date falls inside the next 7 days */
  const posted24 = useTotal({ ...verticalParams('all'), posted_within_days: 1 });
  const eventsWeek = useTotal({
    vertical: QUEST_VERTICALS,
    upcoming_only: true,
    event_within_days: 7,
  });

  /* newest rows: the row list, the bounty fallback, and the updated date */
  const newest = useApplications({
    ...verticalParams('all'),
    sort_by: 'date_found',
    sort_order: 'desc',
    page: 1,
    page_size: 24,
  });
  /* the bounty pool: rows with a provable post date in the last 3 days.
     One page of the 100 newest finds; the pick is deterministic over it. */
  const recent = useApplications({
    ...verticalParams('all'),
    posted_within_days: 3,
    sort_by: 'date_found',
    sort_order: 'desc',
    page: 1,
    page_size: 100,
  });

  /* the log strip counts, from real statuses */
  const applied = useTotal({ vertical: ALL_VERTICALS, status: 'applied' });
  const interviewing = useTotal({ vertical: ALL_VERTICALS, status: 'interviewing' });
  const offers = useTotal({ vertical: ALL_VERTICALS, status: 'offer' });

  const newestItems = newest.data?.items ?? [];
  const bounty = pickBounty(recent.data?.items ?? [], newestItems);
  const rows = pickNewRows(newestItems, bounty?.app ?? null);
  const tiles = logStripTiles({ applied, interviewing, offers });

  const updated = shortDate(newestItems[0]?.date_found);
  const today = shortDate(new Date().toISOString());
  const updatedLabel = updated === today ? 'today' : updated;

  return (
    <>
      <StampDefs />
      <div className="qb-mast">
        <div className="qb-hwrap qb-mast-inner">
          <h1 className="qb-lede">
            {boardTotal !== undefined && pay500Total !== undefined && (
              <>
                <span className="qb-num">{boardTotal}</span> quests on the board.{' '}
                <span className="qb-num">{pay500Total}</span> pay <span className="qb-num">$500</span>{' '}
                or more.
              </>
            )}
          </h1>
          {updatedLabel && (
            <p className="qb-msub">
              Updated {updatedLabel}. Every listing links straight to the source.
            </p>
          )}
          <p className="qb-msub">
            Never done any of this? Most quests here need nothing you don't already have.{' '}
            <Link to="/board" className="qb-textlink">
              Start here
            </Link>
          </p>
          <div className="qb-flaprow">
            {posted24 !== undefined && (
              <SplitFlap
                value={String(posted24)}
                caption="posted in the last 24 hours"
                srLabel={`${posted24} quests posted in the last 24 hours.`}
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
            <BountyCard app={bounty.app} labels={labels} />
          </section>
        )}

        <section className="qb-chapter qb-washed">
          <CredoLine text="Every date on this board is the true post date." />
          <h2 className="qb-ch-title">
            New on the board{' '}
            <span className="qb-aside">
              <Link to="/board" className="qb-textlink">
                See the full board
              </Link>
            </span>
          </h2>
          <div className="qb-hrows">
            {rows.map((app) => (
              <HomeRow key={app.id} app={app} labels={labels} />
            ))}
          </div>
          {newest.isError && (
            <p style={{ fontSize: 14.5, color: 'var(--soft)', margin: '16px 0 0' }}>
              The board could not reach the backend. Start it with make dev and reload.
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
