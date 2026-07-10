import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createRoute, redirect, useNavigate } from '@tanstack/react-router';
import { HugeiconsIcon } from '@hugeicons/react';
import { CoinsDollarIcon, Location01Icon, Search01Icon } from '@hugeicons/core-free-icons';
import { Route as appRoute } from './app';
import {
  Chip,
  LedgerRow,
  PlainButton,
  Poster,
  Sheet,
  StampDefs,
  TextLink,
} from '@questboard/ui';
import { useApplications, useUpdateStatus } from '@/hooks/use-applications';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { ExplainSheet } from '@/components/board/explain-sheet';
import { RestockLine } from '@/components/board/restock-line';
import {
  dismissNotice,
  hasBoardParams,
  noticeDismissed,
  presetKeysFrom,
  presetKeysTo,
  readSavedBoardState,
  saveBoardState,
  validateBoardSearch,
  type BoardParams,
} from '@/components/board/board-state';
import {
  CLIP_STATUS,
  parseAmount,
  toBoardCard,
  withinPayCeiling,
} from '@/utils/board-card';
import { checkedAgoLabel } from '@/features/board/freshness';
import { kindParams, type KindKey } from '@/features/board/kind-params';
import { KindRail } from '@/features/board/kind-rail';
import { toPoster } from '@/features/board/poster-model';
import { useBoardSummary } from '@/hooks/use-board-summary';
import type { ApplicationFilters, ApplicationResponse, RequirementMatch } from '@/types/application';
import '@/components/board/board.css';
import '@/features/board/board-felt.css';

/* Filter state lives in the URL (?v, ?q, ?from, ?to, ?p): a filtered board
   is a shareable address, back/forward walks chip changes, and the topbar
   search box submits into ?q=. The last state persists at
   questboard:board.v1; a bare /board redirects to it once, so Tuesday's
   board is already set up on Wednesday, and explicit params always win. */
export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/board',
  component: BoardPage,
  validateSearch: validateBoardSearch,
  beforeLoad: ({ search, cause }) => {
    /* only on the way IN: an in-route search change (cause 'stay') is the
       reader clearing chips, and re-applying saved state would snap the
       filters right back */
    if (cause !== 'enter') return;
    if (hasBoardParams(search)) return;
    const saved = readSavedBoardState();
    if (saved && hasBoardParams(saved)) {
      throw redirect({
        to: '/board',
        search: { v: saved.v, q: saved.q, from: saved.from, to: saved.to, p: saved.p },
        replace: true,
      });
    }
  },
});

const PAGE_SIZE = 24;

/* Preset chips. Each one maps 1:1 onto a real API filter param, so its
   count is the API's own total for that query, never a guess. Chips that
   share a group write the same param and stay mutually exclusive.
   careerOnly presets lean on scoring/company fields quest rows never have;
   career rows live under the skill kind, so they hide on the other kinds.
   noexp keeps only rows whose source stated a beginner-friendly signal. */
interface Preset {
  key: string;
  label: string;
  params: Partial<ApplicationFilters>;
  group?: string;
  careerOnly?: boolean;
}

const PRESETS: Preset[] = [
  { key: 'noexp', label: 'no experience needed', params: { first_quest_ok: true } },
  { key: 'remote', label: 'remote', params: { is_remote: true } },
  { key: 'fresh', label: 'new this week', params: { posted_within_days: 7 } },
  { key: 'strong', label: 'strong apply', params: { recommendation: 'STRONG_APPLY' }, careerOnly: true },
  { key: 'score50', label: 'scored 50 or better', params: { min_score: 50 }, careerOnly: true },
  { key: 'early', label: 'early startup', params: { company_type: 'Early Startup' }, group: 'company', careerOnly: true },
  { key: 'bigtech', label: 'big tech', params: { company_type: 'Big Tech' }, group: 'company', careerOnly: true },
];

const PRESET_KEYS = PRESETS.map((p) => p.key);

function presetParams(activeKeys: Set<string>): Partial<ApplicationFilters> {
  let merged: Partial<ApplicationFilters> = {};
  for (const preset of PRESETS) {
    if (activeKeys.has(preset.key)) merged = { ...merged, ...preset.params };
  }
  return merged;
}

function useDebounced(value: string, ms = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function verdict(strength: RequirementMatch['strength']): ReactNode {
  if (strength === 'strong') return <span style={{ color: 'var(--sage)' }}>in your resume</span>;
  if (strength === 'partial') return <span style={{ color: 'var(--mute)' }}>partial</span>;
  return <span style={{ color: 'var(--mute)' }}>not in your resume yet</span>;
}

function PresetChip({
  preset,
  active,
  countFilters,
  onToggle,
}: {
  preset: Preset;
  active: boolean;
  countFilters: ApplicationFilters;
  onToggle: () => void;
}) {
  /* page_size 1 keeps the payload tiny; the count is the query's true total */
  const { data } = useApplications(countFilters);
  return <Chip label={preset.label} count={data?.total} active={active} onClick={onToggle} />;
}

function HouseRules() {
  return (
    <aside className="qb-house">
      <h4>House rules</h4>
      <p>Every quest links to its source. Pay is only what the poster states, never a guess.</p>
      <p>No MLMs, no pay-to-start, nothing adult. The risky ones carry their catch in plain words.</p>
      <p className="qb-house-sig">If it's pinned here, it's real.</p>
    </aside>
  );
}

function BoardPosters({
  filters,
  payCeiling,
  labels,
  onOpenSheet,
  onExplain,
}: {
  filters: ApplicationFilters;
  payCeiling: number | null;
  labels: Record<string, string>;
  onOpenSheet: (app: ApplicationResponse) => void;
  onExplain: (app: ApplicationResponse) => void;
}) {
  const { data } = useApplications(filters);
  const updateStatus = useUpdateStatus();
  if (!data) return null;
  /* The API only takes the floor today, so the typed to-bound trims the
     loaded page client-side with the same keep-unknown-pay semantics. */
  const items = data.items.filter((app) => withinPayCeiling(app, payCeiling));
  return (
    <>
      {items.map((app) => {
        const poster = toPoster(app, resolveSourceLabel(app.source, labels));
        const { card } = poster;
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
            showExplain
            onExplain={() => onExplain(app)}
            onClip={() => updateStatus.mutate({ id: app.id, data: { status: CLIP_STATUS } })}
          />
        );
      })}
    </>
  );
}

function RequirementSheet({
  app,
  labels,
  onClose,
}: {
  app: ApplicationResponse | null;
  labels: Record<string, string>;
  onClose: () => void;
}) {
  const updateStatus = useUpdateStatus();
  /* the mutation's response is the server's own updated row, so a clip made
     inside the sheet flips the footer without waiting for a refetch */
  const effective =
    app && updateStatus.data && updateStatus.data.id === app.id ? updateStatus.data : app;
  const card = effective ? toBoardCard(effective, resolveSourceLabel(effective.source, labels)) : null;
  return (
    <Sheet
      open={app !== null}
      onClose={onClose}
      label="Requirements against your resume"
      title={card?.title}
      meta={card ? `${card.meta ? `${card.meta}, ` : ''}covers ${card.fit?.strong ?? 0} of ${card.fit?.total ?? 0} requirements` : undefined}
    >
      {effective && card?.report && (
        <>
          <div
            style={{
              border: '1px solid var(--hair)',
              borderBottomColor: 'var(--edge)',
              borderRadius: 10,
              background: 'var(--paper)',
              padding: '14px 18px',
              marginTop: 14,
              maxHeight: '46vh',
              overflowY: 'auto',
            }}
          >
            <div className="qb-fb-label">From the posting, read against your resume</div>
            {card.report.requirements.map((req, i) => (
              <LedgerRow key={i} title={req.requirement} pay={verdict(req.strength)} />
            ))}
          </div>
          <div className="qb-srow">
            {effective.job_url && <TextLink href={effective.job_url}>Apply at source</TextLink>}
            {card.applied ? (
              <span className="qb-applied-stamp">{card.applied}</span>
            ) : card.clippedDate ? (
              <span className="qb-applied-stamp" style={{ color: 'var(--sage)' }}>
                Clipped, {card.clippedDate}
              </span>
            ) : (
              <PlainButton
                onClick={() =>
                  updateStatus.mutate({ id: effective.id, data: { status: CLIP_STATUS } })
                }
              >
                Clip
              </PlainButton>
            )}
            <PlainButton className="qb-closebtn" onClick={onClose}>
              Done for now
            </PlainButton>
          </div>
        </>
      )}
    </Sheet>
  );
}

/* "Never done any of this?" One honest door: the no-experience preset,
   backed by the source-stated first_quest_ok flag. Dismissal is stored
   locally and never asked about again. */
function FirstRunNotice({ onStartHere }: { onStartHere: () => void }) {
  const [gone, setGone] = useState(() => noticeDismissed());
  if (gone) return null;
  return (
    <div className="qb-board-notice">
      <span>
        Never done any of this? Most quests here need nothing you don't already have.{' '}
        <button type="button" className="qb-textlink" style={{ fontSize: 14 }} onClick={onStartHere}>
          Start here
        </button>
      </span>
      <button
        type="button"
        className="qb-dismiss"
        onClick={() => {
          dismissNotice();
          setGone(true);
        }}
      >
        Dismiss
      </button>
    </div>
  );
}

function BoardPage() {
  const labels = useSourceLabels();
  const navigate = useNavigate();
  const params = Route.useSearch();
  const checkedAgo = checkedAgoLabel(useBoardSummary().data?.checked_at);

  /* the URL is the one truth for the kind tag and presets */
  const kindKey: KindKey = params.v ?? 'all';
  const activeKeys = useMemo(() => presetKeysFrom(params.p, PRESET_KEYS), [params.p]);

  /* text inputs buffer locally, debounce into the URL with replace so
     typing never spams history */
  const [searchRaw, setSearchRaw] = useState(params.q ?? '');
  const [placeRaw, setPlaceRaw] = useState(params.place ?? '');
  const [payFromRaw, setPayFromRaw] = useState(params.from ?? '');
  const [payToRaw, setPayToRaw] = useState(params.to ?? '');
  /* newest first by default: the API's score sort floats unscored rows to
     the top (desc nullsfirst), which reads as noise on a board */
  const [sortNewest, setSortNewest] = useState(() => readSavedBoardState()?.sort !== 'score');
  /* pages loaded, keyed to the filters that loaded them: any filter change
     starts back at one page without an effect */
  const [pageState, setPageState] = useState<{ key: string; pages: number }>({ key: '', pages: 1 });
  const [sheetApp, setSheetApp] = useState<ApplicationResponse | null>(null);
  const [explainApp, setExplainApp] = useState<ApplicationResponse | null>(null);

  const search = useDebounced(searchRaw.trim());
  const place = useDebounced(placeRaw.trim());
  const payFrom = useDebounced(payFromRaw.trim());
  const payTo = useDebounced(payToRaw.trim());
  const payFloor = parseAmount(payFrom);
  const payCeiling = parseAmount(payTo);

  /* what this page last wrote into the URL; anything else is history nav */
  const pushedRef = useRef<{ q?: string; place?: string; from?: string; to?: string }>({
    q: params.q,
    place: params.place,
    from: params.from,
    to: params.to,
  });

  /* debounced edits -> URL (replace) */
  useEffect(() => {
    const next = {
      q: search || undefined,
      place: place || undefined,
      from: payFrom || undefined,
      to: payTo || undefined,
    };
    const cur = pushedRef.current;
    if (cur.q === next.q && cur.place === next.place && cur.from === next.from && cur.to === next.to) return;
    pushedRef.current = next;
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => ({ ...prev, ...next }),
      replace: true,
    });
  }, [search, place, payFrom, payTo, navigate]);

  /* back/forward -> inputs: adopt a URL this page did not write */
  useEffect(() => {
    const cur = pushedRef.current;
    if (
      params.q === cur.q &&
      params.place === cur.place &&
      params.from === cur.from &&
      params.to === cur.to
    )
      return;
    pushedRef.current = { q: params.q, place: params.place, from: params.from, to: params.to };
    setSearchRaw(params.q ?? '');
    setPlaceRaw(params.place ?? '');
    setPayFromRaw(params.from ?? '');
    setPayToRaw(params.to ?? '');
  }, [params.q, params.place, params.from, params.to]);

  /* the whole state persists locally so the next bare /board reopens it */
  useEffect(() => {
    saveBoardState({
      v: params.v,
      q: params.q,
      from: params.from,
      to: params.to,
      p: params.p,
      sort: sortNewest ? undefined : 'score',
    });
  }, [params.v, params.q, params.from, params.to, params.p, sortNewest]);

  const baseFilters = useMemo<ApplicationFilters>(
    () => ({
      ...kindParams(kindKey),
      ...presetParams(activeKeys),
      search: search || undefined,
      location: place || undefined,
      salary_min: payFloor ?? undefined,
      sort_by: sortNewest ? 'date_found' : 'overall_score',
      sort_order: 'desc',
      page_size: PAGE_SIZE,
    }),
    [kindKey, activeKeys, search, place, payFloor, sortNewest],
  );

  const filtersKey = JSON.stringify(baseFilters);
  const pages = pageState.key === filtersKey ? pageState.pages : 1;

  const firstPage = useApplications({ ...baseFilters, page: 1 });
  const total = firstPage.data?.total;

  /* careerOnly presets lean on fields only career rows carry; career lives
     under the skill kind, so they hide everywhere else */
  const questScoped = kindKey !== 'all' && kindKey !== 'skill';
  const visiblePresets = PRESETS.filter((p) => !p.careerOnly || !questScoped);

  function selectKind(key: KindKey) {
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => {
        let keys = presetKeysFrom(prev.p, PRESET_KEYS);
        if (key !== 'all' && key !== 'skill') {
          /* a hidden careerOnly preset must not keep silently filtering the feed */
          keys = new Set([...keys].filter((k) => !PRESETS.find((p) => p.key === k)?.careerOnly));
        }
        return {
          ...prev,
          v: key === 'all' ? undefined : key,
          p: presetKeysTo(keys, PRESET_KEYS),
        };
      },
    });
  }

  function toggle(key: string) {
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => {
        const next = presetKeysFrom(prev.p, PRESET_KEYS);
        if (next.has(key)) {
          next.delete(key);
        } else {
          const preset = PRESETS.find((p) => p.key === key);
          if (preset?.group) {
            for (const other of PRESETS) {
              if (other.group === preset.group) next.delete(other.key);
            }
          }
          next.add(key);
        }
        return { ...prev, p: presetKeysTo(next, PRESET_KEYS) };
      },
    });
  }

  /* the notice's one door: switch the no-experience preset on */
  function startHere() {
    if (!activeKeys.has('noexp')) toggle('noexp');
  }

  /* count as if this chip were switched on alongside the current filters */
  function countFilters(preset: Preset): ApplicationFilters {
    const probe = new Set(activeKeys);
    if (preset.group) {
      for (const other of PRESETS) {
        if (other.group === preset.group) probe.delete(other.key);
      }
    }
    probe.add(preset.key);
    return {
      ...kindParams(kindKey),
      ...presetParams(probe),
      search: search || undefined,
      location: place || undefined,
      salary_min: payFloor ?? undefined,
      page: 1,
      page_size: 1,
    };
  }

  return (
    <>
      <StampDefs />
      <div className="qb-board-wrap">
        <div className="qb-board-head">
          <h1>The board</h1>
          <span className="qb-live">{total !== undefined ? `${total} live` : 'loading'}</span>
          <button type="button" className="qb-sort" onClick={() => setSortNewest((v) => !v)}>
            Sort: <b>{sortNewest ? 'newly found' : 'best score'}</b>
          </button>
        </div>

        <RestockLine />

        <KindRail selected={kindKey} onSelect={selectKind} />

        <div className="qb-preset-row">
          {visiblePresets.map((preset) => (
            <PresetChip
              key={preset.key}
              preset={preset}
              active={activeKeys.has(preset.key)}
              countFilters={countFilters(preset)}
              onToggle={() => toggle(preset.key)}
            />
          ))}
        </div>

        <div className="qb-tray" role="search">
          <label className="qb-tray-field qb-tray-grow">
            <HugeiconsIcon icon={Search01Icon} size={16} strokeWidth={1.7} />
            <input
              placeholder="Search the board"
              aria-label="Search the board"
              value={searchRaw}
              onChange={(e) => setSearchRaw(e.target.value)}
            />
          </label>
          <label className="qb-tray-field qb-tray-place">
            <HugeiconsIcon icon={Location01Icon} size={16} strokeWidth={1.7} />
            <input
              placeholder="your city or state"
              aria-label="Filter by place; remote quests always pass"
              value={placeRaw}
              onChange={(e) => setPlaceRaw(e.target.value)}
            />
          </label>
          <label className="qb-tray-field qb-tray-pay">
            <HugeiconsIcon icon={CoinsDollarIcon} size={16} strokeWidth={1.7} />
            <input
              inputMode="numeric"
              placeholder="pay from 150k"
              aria-label="Pay floor, a year"
              value={payFromRaw}
              onChange={(e) => setPayFromRaw(e.target.value)}
            />
            <span className="qb-tray-to">to</span>
            <input
              inputMode="numeric"
              placeholder="210k"
              aria-label="Pay ceiling, a year"
              value={payToRaw}
              onChange={(e) => setPayToRaw(e.target.value)}
            />
          </label>
        </div>
        <p className="qb-tray-note">
          Pay counts only what the posting states; no stated pay keeps a quest on the board.
          A place keeps remote and no-place quests too.
        </p>

        <FirstRunNotice onStartHere={startHere} />

        {firstPage.isError && (
          <p style={{ marginTop: 40, fontSize: 14.5, color: 'var(--soft)' }}>
            The board could not reach the backend. Start it with make dev and reload.
          </p>
        )}
        {firstPage.isLoading && (
          <p className="qb-num" style={{ marginTop: 40, fontSize: 13, color: 'var(--mute)' }}>
            loading the board
          </p>
        )}
        {total === 0 && (
          <p style={{ marginTop: 40, fontSize: 14.5, color: 'var(--soft)' }}>
            Nothing on the board matches. Clear a chip or the search.
          </p>
        )}

        {total !== undefined && total > 0 && (
          <div className="qb-felt">
            <div className="qb-wall">
              {Array.from({ length: pages }, (_, i) => (
                <BoardPosters
                  key={i + 1}
                  filters={{ ...baseFilters, page: i + 1 }}
                  payCeiling={payCeiling}
                  labels={labels}
                  onOpenSheet={setSheetApp}
                  onExplain={setExplainApp}
                />
              ))}
              <HouseRules />
            </div>
            {pages * PAGE_SIZE < total && (
              <div style={{ display: 'flex', justifyContent: 'center', marginTop: 6 }}>
                <button
                  type="button"
                  className="qb-textlink"
                  onClick={() => setPageState({ key: filtersKey, pages: pages + 1 })}
                >
                  more
                </button>
              </div>
            )}
          </div>
        )}

        <p className="qb-board-legend">
          Pull <b>take it</b> to go straight to the source. <b>The colour of the pin tells you the kind of quest.</b>{' '}
          Every date on this board is the true post date; postings with no verifiable date say nothing.
          {checkedAgo && <> Quests the sources stop listing come down on their own. <b>{checkedAgo}.</b></>}
        </p>
      </div>

      <RequirementSheet app={sheetApp} labels={labels} onClose={() => setSheetApp(null)} />
      <ExplainSheet app={explainApp} labels={labels} onClose={() => setExplainApp(null)} />
    </>
  );
}
