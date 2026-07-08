import { useEffect } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Chip, QuestCard, SageButton, SplitFlap, Stamp, StampDefs, verticals } from '@questboard/ui';
import { useApplications, useUpdateStatus } from '@/hooks/use-applications';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { CLIP_STATUS, shortDate, toBoardCard } from '@/utils/board-card';
import { verticalParams } from '@/utils/board-verticals';
import { hasEntered } from '@/lib/entry';
import { handleEnter, pickLandingCards, pickTrustCard } from './landing-logic';
import type { ApplicationFilters, ApplicationResponse } from '@/types/application';
import './landing.css';

/* The front page, ported from packages/ui/reference/quest-board-mock.html
   (#landing). A faithful port, not a redesign: every section of the mock,
   with the mock's hardcoded numbers replaced by the same live page_size=1
   queries the board chips run. Nothing here invents a count. */

function BrandMark() {
  return (
    <div className="qb-land-brand">
      <span className="qb-land-tile">
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="4" cy="12" r="1.5" fill="#fff" />
          <path d="M5.2 10.8 10.8 5.2" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" />
          <path d="M7.4 5H11V8.6" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <b>Questboard</b>
    </div>
  );
}

/* The engraved horizon, verbatim from the mock: the masthead's closing edge
   the three pinned cards sit on. */
function Horizon() {
  return (
    <svg
      className="qb-land-horizon"
      viewBox="0 0 1440 210"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
    >
      <g stroke="currentColor" fill="none" strokeWidth="1.7" opacity=".32" strokeLinecap="round">
        <path d="M1010 96 a52 52 0 0 1 86 -5" />
        <path d="M1000 74 l-18 -10 M1016 49 l-13 -15 M1041 33 l-7 -18 M1071 27 l0 -20 M1101 31 l7 -18 M1128 46 l13 -14 M1147 69 l18 -9" />
      </g>
      <path
        d="M-10 118 C 170 84, 380 100, 560 116 S 900 142, 1140 108 S 1360 82, 1450 100 L 1450 220 L -10 220 Z"
        fill="var(--ground)"
      />
      <path
        d="M-10 118 C 170 84, 380 100, 560 116 S 900 142, 1140 108 S 1360 82, 1450 100"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        opacity=".26"
        strokeLinecap="round"
      />
      <g stroke="currentColor" strokeWidth="1" opacity=".14" strokeLinecap="round">
        <path d="M210 104 l-13 10 M266 102 l-13 10 M322 104 l-13 10 M1190 112 l-13 10 M1246 106 l-13 10 M1302 100 l-13 10" />
      </g>
      <path
        d="M-10 164 C 240 140, 500 158, 740 166 S 1160 168, 1450 146 L 1450 220 L -10 220 Z"
        fill="var(--ground)"
      />
      <path
        d="M-10 164 C 240 140, 500 158, 740 166 S 1160 168, 1450 146"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        opacity=".36"
        strokeLinecap="round"
      />
      <g stroke="currentColor" strokeWidth="1" opacity=".17" strokeLinecap="round">
        <path d="M110 158 l-14 11 M172 155 l-14 11 M234 154 l-14 11 M780 176 l-14 11 M842 176 l-14 11 M1240 156 l-14 11 M1302 152 l-14 11" />
      </g>
      <g
        stroke="currentColor"
        fill="none"
        strokeWidth="1.7"
        opacity=".42"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M356 156 V 126 M356 130 h20 l6 5 -6 5 h-20 z" />
      </g>
      <g stroke="currentColor" fill="none" strokeWidth="1.5" opacity=".26" strokeLinecap="round">
        <path d="M760 46 q8 -9 16 0 q8 -9 16 0" />
        <path d="M824 28 q6 -7 12 0 q6 -7 12 0" />
      </g>
    </svg>
  );
}

/* One real board card in the trade-paper grammar; Clip writes through the
   real status mutation, exactly as it does on the board. */
function LandingCard({
  app,
  labels,
  clippedStyle = false,
}: {
  app: ApplicationResponse;
  labels: Record<string, string>;
  clippedStyle?: boolean;
}) {
  const updateStatus = useUpdateStatus();
  const card = toBoardCard(app, resolveSourceLabel(app.source, labels));
  return (
    <QuestCard
      vertical={card.vertical}
      title={card.title}
      href={card.href}
      meta={card.meta}
      needs={card.needs}
      firstQuest={card.firstQuest}
      pay={card.pay}
      payUnit={card.payUnit}
      applied={card.applied}
      clippedDate={
        clippedStyle
          ? (card.clippedDate ?? shortDate(new Date().toISOString()) ?? 'today')
          : card.clippedDate
      }
      onClip={() => updateStatus.mutate({ id: app.id, data: { status: CLIP_STATUS } })}
    />
  );
}

/* A preset-grammar chip whose count is the query's true total. */
function DemoChip({ label, filters }: { label: string; filters: Partial<ApplicationFilters> }) {
  const { data } = useApplications({ ...filters, page: 1, page_size: 1 });
  return <Chip label={label} count={data?.total} dim={data !== undefined && data.total < 3} />;
}

const STRIP_VERTICALS = ['career', 'camera', 'study', 'lens', 'party'] as const;

export function LandingPage() {
  const navigate = useNavigate();
  const labels = useSourceLabels();
  const entered = hasEntered();

  useEffect(() => {
    document.title = 'Questboard, one board for every side quest';
  }, []);

  /* the same totals the board's All chip and pay-floor input count */
  const boardTotal = useApplications({ ...verticalParams('all'), page: 1, page_size: 1 }).data
    ?.total;
  const pay500Total = useApplications({
    ...verticalParams('all'),
    salary_min: 500,
    page: 1,
    page_size: 1,
  }).data?.total;

  /* one board page of the newest rows: enough spread for mixed verticals */
  const newest = useApplications({
    ...verticalParams('all'),
    sort_by: 'date_found',
    sort_order: 'desc',
    page: 1,
    page_size: 24,
  });
  const items = newest.data?.items ?? [];
  const pinned = pickLandingCards(items);
  const trustApp = pickTrustCard(items, pinned);

  const enter = () => handleEnter(navigate);
  const ctaLabel = entered ? 'Back to the board' : 'Open the board';

  return (
    <div className="qb-page qb-landing">
      <StampDefs />

      <div className="qb-land-hero">
        <div className="qb-lwrap">
          <BrandMark />
          <h1>One board for every side quest.</h1>
          <p className="qb-lsub">
            Real quests from real sources, with pay shown when the source states it.
          </p>
          <div className="qb-land-cta">
            <SageButton big onClick={enter}>
              {ctaLabel}
            </SageButton>
            <span className="qb-lnote">Free. Your log lives in your browser.</span>
          </div>
          <div className="qb-flaprow">
            {boardTotal !== undefined && (
              <SplitFlap
                value={String(boardTotal)}
                caption="quests on the board right now"
                srLabel={`${boardTotal} quests on the board right now.`}
              />
            )}
            {pay500Total !== undefined && (
              <SplitFlap
                value={String(pay500Total)}
                caption="pay $500 or more"
                srLabel={`${pay500Total} pay $500 or more.`}
              />
            )}
          </div>
        </div>
        <Horizon />
      </div>

      <div className="qb-lwrap qb-land-cards">
        <div className="qb-cardgrid">
          {pinned.map((app) => (
            <LandingCard key={app.id} app={app} labels={labels} />
          ))}
        </div>
      </div>

      <div className="qb-lwrap">
        <p className="qb-lstatement">Every listing links straight to the source.</p>

        <div className="qb-lgrid">
          <div className="qb-lblock">
            <div className="qb-visual">
              {trustApp && <LandingCard app={trustApp} labels={labels} clippedStyle />}
            </div>
            <h3>The true post date.</h3>
            <p>Reposts and probably-filled listings get flagged before you waste an evening.</p>
          </div>

          <div className="qb-lblock">
            <div className="qb-visual">
              <div className="qb-ledger-demo">
                <div className="qb-done-label">Done</div>
                <div className="qb-dline">
                  <span className="qb-dd">Jul 3</span>
                  <span className="qb-dt">Prolific study batch paid out.</span>
                  <span className="qb-dn">$45. Took 13 days.</span>
                </div>
                <div className="qb-dline">
                  <span className="qb-dd">Jun 28</span>
                  <span className="qb-dt">Did a paid snack focus group.</span>
                  <span className="qb-dn">$125.</span>
                </div>
                <div className="qb-dline">
                  <span className="qb-dd">Mar 4</span>
                  <span className="qb-dt">Ran the 10k.</span>
                  <span className="qb-dn">Helped by your sister.</span>
                </div>
                <div className="qb-ledger-total">
                  Paid out in <span className="qb-num">2026</span> so far:{' '}
                  <span className="qb-num">$170</span>. Counting only what landed.
                </div>
              </div>
            </div>
            <h3>The log is the proof.</h3>
            <p>A dated ledger of what you did and what it paid. Nothing turns red, nothing resets.</p>
          </div>

          <div className="qb-lblock">
            <div className="qb-visual">
              <div className="qb-chips-demo">
                <DemoChip label="remote" filters={{ ...verticalParams('all'), is_remote: true }} />
                <DemoChip
                  label="$500 or more"
                  filters={{ ...verticalParams('all'), salary_min: 500 }}
                />
                <DemoChip label="career" filters={verticalParams('career')} />
                <DemoChip label="on camera" filters={verticalParams('camera')} />
                <DemoChip label="paid studies" filters={verticalParams('study')} />
              </div>
            </div>
            <h3>Filters that count.</h3>
            <p>Every chip shows how many quests are behind it, live.</p>
          </div>

          <div className="qb-lblock">
            <div className="qb-visual">
              <div className="qb-ai-demo">
                <div className="qb-ai-src">A 400-word posting, boiled down:</div>
                <div className="qb-xhead">In plain words</div>
                <div className="qb-ai-out">
                  They want a friendly voice on the phone, weekday evenings,{' '}
                  <span className="qb-num">$19</span> an hour. Lead your note with your two years at
                  a front desk.
                </div>
                <div className="qb-ai-hedge">Full reads on most laptops, quick reads everywhere.</div>
                <div className="qb-price">
                  Search pass, <span className="qb-num">$29</span> once. Offer pass,{' '}
                  <span className="qb-num">$99</span> once. Everything else is free.
                </div>
              </div>
            </div>
            <h3>Free AI, no monthly bill.</h3>
            <p>Your computer does the work. That's how free stays free.</p>
          </div>
        </div>
      </div>

      <div className="qb-stampstrip">
        {STRIP_VERTICALS.map((v) => (
          <div key={v} className="qb-st" style={{ color: verticals[v].hue }}>
            <Stamp vertical={v} size={44} inheritColor />
            {verticals[v].label}
          </div>
        ))}
      </div>

      <div className="qb-lwrap qb-land-foot">
        <span className="qb-t">
          The board restocks daily. Every listing links straight to the source.
        </span>
        <SageButton big onClick={enter}>
          {ctaLabel}
        </SageButton>
      </div>
    </div>
  );
}
