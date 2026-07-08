import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { createRoute } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import {
  Chip,
  LedgerRow,
  PlainButton,
  PostmarkStamp,
  QuestCard,
  SageButton,
  Sheet,
  SplitFlap,
  Stamp,
  StampDefs,
  TextLink,
  verticals,
  type QuestCardProps,
  type Vertical,
} from '@questboard/ui';

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/design',
  component: DesignPage,
});

const TODAY = 'Jul 7';

/* rows borrowed from the reference mock (packages/ui/reference/quest-board-mock.html) */
const QUESTS: Array<{ id: string } & Omit<QuestCardProps, 'onClip' | 'onMakeParty' | 'onExplain'>> = [
  {
    id: 'extras',
    vertical: 'camera',
    title: 'Background actors, major streaming series',
    meta: 'Casting Networks, posted today, Los Angeles',
    needs: 'Needs: photos and basics, no experience',
    pay: '$231',
    payUnit: '/8 hr',
    firstQuest: true,
  },
  {
    id: 'linear',
    vertical: 'career',
    title: 'Data Engineer, Linear',
    meta: 'Ashby, posted today, remote in the US',
    needs: 'Needs: resume, covers 7 of 9 requirements',
    pay: '$170–210k',
    payUnit: 'base',
    showExplain: true,
  },
  {
    id: 'edu',
    vertical: 'study',
    title: 'Education technology focus group',
    meta: 'FocusGroups.org, posted 2d ago, Manhattan',
    needs: 'Needs: screener about 15 min, teachers preferred',
    pay: '$450',
    payUnit: 'max',
    clippedDate: 'Jul 6',
  },
  {
    id: 'vercel',
    vertical: 'career',
    title: 'Staff Data Engineer, Vercel',
    meta: 'Greenhouse, posted 5d ago, remote in the US',
    needs: 'Needs: resume, covers 8 of 9 requirements',
    pay: '$190–240k',
    payUnit: 'base',
    applied: 'Applied, Jun 30',
  },
  {
    id: 'bank',
    vertical: 'camera',
    title: 'Commercial, regional bank spot',
    meta: 'Casting Networks, posted 3d ago, Chicago',
    needs: 'Needs: self-tape, speaking role',
    bar: 'prep',
    pay: '$1,500',
    payUnit: 'flat',
  },
  {
    id: 'sprite',
    vertical: 'party',
    title: 'Get cast with your real friend group, Sprite ad',
    meta: 'Project Casting, closes Jul 12, Miami',
    needs: 'Needs: 3 to 6 real friends, ages 18 to 35, one group photo, same shoot day',
    pay: '$1,000',
    payUnit: '/day each',
    party: { total: 4, seated: ['S', 'D'] },
  },
  {
    id: 'weightloss',
    vertical: 'party',
    title: 'Put $99 each on the line, team weight-loss pot',
    meta: 'healthywage.com, rolling, anywhere',
    needs: 'Needs: exactly 5 people, a scale, verified weigh-ins, 3 months',
    pay: '$99',
    payUnit: 'stake, each',
    party: { total: 5, seated: ['Y', 'S', 'D', 'M', 'J'], date: 'Sat Jul 18' },
  },
  {
    id: 'portfolio',
    vertical: 'lens',
    title: 'Post a free portfolio shoot ad, book two sessions',
    meta: 'The r/photography recipe, rolling, anywhere',
    needs: 'Needs: any camera, one ad on Craigslist or a local subreddit, a weekend',
    pay: '$0',
    payUnit: 'a portfolio, not cash',
    firstQuest: true,
  },
];

const EXPLAIN = {
  title: 'Data Engineer, Linear',
  meta: 'Ashby, posted today, remote in the US',
  plain:
    'Pays $170 to 210k base, remote in the US. Asks for five years of data pipelines, dbt, Snowflake, and Python. Posted today.',
  full:
    'A small team rebuilding their warehouse, so they want someone who has owned pipelines end to end. dbt shows up in every requirement. Your resume covers 7 of the 9 asks; the two it does not show are dbt and on-call ownership. If you have done either, say so in your first two lines.',
};

const sectionTitle: CSSProperties = {
  fontFamily: 'var(--serif)',
  fontVariationSettings: "'opsz' 80",
  fontWeight: 560,
  fontSize: 26,
  letterSpacing: '-.01em',
  margin: 0,
};

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section style={{ marginTop: 64 }}>
      <h2 style={sectionTitle}>{title}</h2>
      {note && <p style={{ fontSize: 14, color: 'var(--mute)', margin: '4px 0 0' }}>{note}</p>}
      <div style={{ marginTop: 20 }}>{children}</div>
    </section>
  );
}

function StampStrip() {
  const order: Vertical[] = ['career', 'camera', 'study', 'lens', 'party', 'personal'];
  return (
    <div style={{ display: 'flex', gap: 56, flexWrap: 'wrap' }}>
      {order.map((v) => (
        <div key={v} style={{ textAlign: 'center', fontSize: 13, fontWeight: 500, color: verticals[v].hue }}>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Stamp vertical={v} size={44} />
          </div>
          <div style={{ marginTop: 8 }}>{verticals[v].label}</div>
        </div>
      ))}
    </div>
  );
}

function ChipsDemo() {
  const [activeVertical, setActiveVertical] = useState<Vertical | 'all'>('all');
  const [presets, setPresets] = useState<Record<string, boolean>>({ quiet: true });
  const toggle = (key: string) => setPresets((p) => ({ ...p, [key]: !p[key] }));
  const chipOrder: Array<Vertical | 'all'> = ['all', 'career', 'camera', 'study', 'lens', 'party'];
  return (
    <>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        {chipOrder.map((v) => (
          <Chip
            key={v}
            label={v === 'all' ? 'All' : verticals[v].label}
            vertical={v}
            active={activeVertical === v}
            onClick={() => setActiveVertical(v)}
          />
        ))}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Chip label="no experience needed" count={9} active={Boolean(presets.noexp)} onClick={() => toggle('noexp')} />
        <Chip label="no camera, no calls" count={3} active={Boolean(presets.quiet)} onClick={() => toggle('quiet')} />
        <Chip label="remote" count={7} active={Boolean(presets.remote)} onClick={() => toggle('remote')} />
        <Chip label="$500 or more" count={7} active={Boolean(presets.pay500)} onClick={() => toggle('pay500')} />
        <Chip label="under 2 hours" count={2} dim active={Boolean(presets.short)} onClick={() => toggle('short')} />
      </div>
    </>
  );
}

function ExplainSheetBody({ stage, pct, onStart, onLater }: {
  stage: 'ask' | 'notnow' | 'progress' | 'done';
  pct: number;
  onStart: () => void;
  onLater: () => void;
}) {
  return (
    <>
      <div className="qb-note">
        <div className="qb-xhead">In plain words</div>
        <div className={stage === 'done' ? 'qb-xswap' : undefined}>
          {stage === 'done' ? EXPLAIN.full : EXPLAIN.plain}
        </div>
        <div className="qb-xmethod">
          {stage === 'done' ? 'Read against the posting and your resume.' : "Pulled from the posting's own words."}
        </div>
      </div>
      <div className="qb-xconsent">
        {stage === 'ask' && (
          <>
            <div className="qb-xc-title">First time only.</div>
            <div className="qb-xc-body">
              Your computer can do this work itself, so it's free and nothing you type leaves it. One download
              first, about <span className="qb-num">1.1 GB</span>, the size of a movie.
            </div>
            <div className="qb-xc-row">
              <SageButton onClick={onStart}>Start the download</SageButton>
              <PlainButton onClick={onLater}>Not now</PlainButton>
            </div>
            <div className="qb-xc-foot">Remove it any time in Settings.</div>
          </>
        )}
        {stage === 'notnow' && (
          <div className="qb-xc-foot" style={{ marginTop: 0 }}>
            The full read is in Settings whenever you want it.
          </div>
        )}
        {stage === 'progress' && (
          <div className="qb-xc-body">
            On its way, <span className="qb-num">{pct}%</span>. Keep browsing, it finishes on its own.
          </div>
        )}
        {stage === 'done' && (
          <div className="qb-xc-foot" style={{ marginTop: 0 }}>
            Done. Full reads from here on. It never downloads again.
          </div>
        )}
      </div>
    </>
  );
}

function DesignPage() {
  const [clipped, setClipped] = useState<Record<string, string>>({});
  const [partyOpen, setPartyOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [explainOpen, setExplainOpen] = useState(false);
  const [xStage, setXStage] = useState<'ask' | 'notnow' | 'progress' | 'done'>('ask');
  const [pct, setPct] = useState(4);
  const [pressKey, setPressKey] = useState(0);

  useEffect(() => {
    if (xStage !== 'progress') return;
    let p = 4;
    const iv = window.setInterval(() => {
      p += 8;
      if (p >= 100) {
        window.clearInterval(iv);
        setXStage('done');
      } else {
        setPct(p);
      }
    }, 220);
    return () => window.clearInterval(iv);
  }, [xStage]);

  const partyNote =
    'found us a thing: get cast with your real friend group, sprite ad. pays $1,000 /day each. needs 4 people, pick a day. you in?';

  function copyNote() {
    if (navigator.clipboard) void navigator.clipboard.writeText(partyNote);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <div
      className="qb-page"
      style={{ position: 'fixed', inset: 0, zIndex: 40, overflowY: 'auto' }}
    >
      <StampDefs />
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '52px 44px 96px' }}>
        <h1
          style={{
            fontFamily: 'var(--serif)',
            fontVariationSettings: "'opsz' 144",
            fontWeight: 560,
            fontSize: 44,
            lineHeight: 1.08,
            letterSpacing: '-.015em',
            margin: 0,
          }}
        >
          The trade paper, in parts.
        </h1>
        <p style={{ fontSize: 16, color: 'var(--soft)', margin: '12px 0 0' }}>
          Every component of the design system, on one page, with board data.
        </p>

        <div className="qb-flaprow" style={{ marginTop: 30 }}>
          <SplitFlap
            value="41"
            caption="quests on the board right now"
            srLabel="41 quests on the board right now, 9 pay $500 or more."
          />
          <SplitFlap value="9" caption="pay $500 or more" />
        </div>

        <Section title="Stamps" note="One hand-drawn postal stamp per vertical, single-weight line.">
          <StampStrip />
        </Section>

        <Section title="Chips" note="Vertical chips above, preset chips with live counts below.">
          <ChipsDemo />
        </Section>

        <Section title="Quest cards" note="Clip one to see the postmark press in.">
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: 16,
            }}
          >
            {QUESTS.map((q) => (
              <QuestCard
                key={q.id}
                {...q}
                clippedDate={clipped[q.id] ?? q.clippedDate}
                onClip={() => setClipped((c) => ({ ...c, [q.id]: TODAY }))}
                onMakeParty={() => setPartyOpen(true)}
                onExplain={() => setExplainOpen(true)}
              />
            ))}
          </div>
        </Section>

        <Section title="Ledger rows" note="The from-the-board grammar.">
          <div
            style={{
              border: '1px solid var(--hair)',
              borderBottomColor: 'var(--edge)',
              borderRadius: 10,
              background: 'var(--paper)',
              padding: '18px 22px',
              maxWidth: 560,
            }}
          >
            <div className="qb-fb-label">From the board</div>
            <LedgerRow title="Snack product testing" tag="paid studies" pay="$125" payUnit="max" />
            <LedgerRow title="UGC creator for a skincare brand" tag="on camera" pay="$150–200" payUnit="/video" />
            <LedgerRow title="Marketing Coordinator, Later" tag="career" pay="$58–70k" payUnit="base" />
          </div>
        </Section>

        <Section title="Sheets" note="Escape or a scrim click closes either one.">
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <SageButton onClick={() => setPartyOpen(true)}>Make a party</SageButton>
            <SageButton onClick={() => setExplainOpen(true)}>Explain this quest</SageButton>
          </div>
        </Section>

        <Section title="Postmark press" note="The stamp that lands when a quest is clipped.">
          <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
            <PostmarkStamp key={`career-${pressKey}`} vertical="career" press={pressKey > 0} />
            <PostmarkStamp key={`camera-${pressKey}`} vertical="camera" press={pressKey > 0} />
            <PostmarkStamp key={`study-${pressKey}`} vertical="study" press={pressKey > 0} />
            <PostmarkStamp key={`lens-${pressKey}`} vertical="lens" press={pressKey > 0} />
            <PostmarkStamp key={`party-${pressKey}`} vertical="party" press={pressKey > 0} />
            <TextLink onClick={() => setPressKey((k) => k + 1)}>Press again</TextLink>
          </div>
        </Section>

        <Section title="Buttons and links">
          <div style={{ display: 'flex', gap: 20, alignItems: 'center', flexWrap: 'wrap' }}>
            <SageButton>Keep a copy</SageButton>
            <SageButton big>Open the board</SageButton>
            <PlainButton>Not now</PlainButton>
            <TextLink href="#">Apply at source</TextLink>
            <TextLink onClick={() => {}}>First quest guide</TextLink>
          </div>
        </Section>
      </div>

      <Sheet
        open={partyOpen}
        onClose={() => setPartyOpen(false)}
        label="Make a party"
        title="Make a party"
        meta="Get cast with your real friend group, Sprite ad. $1,000 /day each."
      >
        <p className="qb-hint">Copy the note into your group chat. When someone says they're in, mark their seat.</p>
        <div className="qb-note">{partyNote}</div>
        <div className="qb-srow">
          <SageButton onClick={copyNote}>{copied ? 'Copied' : 'Copy the note'}</SageButton>
          <span className="qb-waiting">Waiting on 2 more.</span>
          <PlainButton className="qb-closebtn" onClick={() => setPartyOpen(false)}>
            Done for now
          </PlainButton>
        </div>
      </Sheet>

      <Sheet
        open={explainOpen}
        onClose={() => setExplainOpen(false)}
        label="Explain this quest"
        title={EXPLAIN.title}
        meta={EXPLAIN.meta}
      >
        <ExplainSheetBody
          stage={xStage}
          pct={pct}
          onStart={() => {
            setPct(4);
            setXStage('progress');
          }}
          onLater={() => setXStage('notnow')}
        />
        <div className="qb-srow">
          <TextLink href="#">Apply at source</TextLink>
          <PlainButton className="qb-closebtn" onClick={() => setExplainOpen(false)}>
            Done for now
          </PlainButton>
        </div>
      </Sheet>
    </div>
  );
}
