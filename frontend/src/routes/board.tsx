import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createRoute, redirect, useNavigate } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import {
  Chip,
  LedgerRow,
  PlainButton,
  QuestCard,
  Sheet,
  StampDefs,
  TextLink,
  verticals,
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
import { VERTICAL_KEYS, verticalParams, type VerticalKey } from '@/utils/board-verticals';
import type { ApplicationFilters, ApplicationResponse, RequirementMatch } from '@/types/application';
import '@/components/board/board.css';

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
   careerOnly presets lean on scoring/company fields quest rows never have,
   so they hide when a single quest vertical is selected. noexp keeps only
   rows whose source stated a beginner-friendly signal; career rows carry
   no such signal, so they drop rather than get guessed in. */
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

function VerticalChip({
  verticalKey,
  active,
  onSelect,
}: {
  verticalKey: VerticalKey;
  active: boolean;
  onSelect: () => void;
}) {
  /* the count is the whole vertical's live total, independent of presets:
     the chip says what is behind the door, not what the filters keep */
  const { data } = useApplications({ ...verticalParams(verticalKey), page: 1, page_size: 1 });
  return (
    <Chip
      vertical={verticalKey === 'all' ? 'all' : verticalKey}
      label={verticalKey === 'all' ? 'All' : verticals[verticalKey].label}
      count={data?.total}
      active={active}
      onClick={onSelect}
    />
  );
}

function BoardCards({
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
        const card = toBoardCard(app, resolveSourceLabel(app.source, labels));
        const needs =
          card.fit && card.fit.missing > 0 ? (
            <>
              {card.needs}{' '}
              <button
                type="button"
                className="qb-textlink"
                style={{ fontSize: 13 }}
                onClick={() => onOpenSheet(app)}
              >
                see the {card.fit.missing} missing
              </button>
            </>
          ) : (
            card.needs
          );
        return (
          <QuestCard
            key={app.id}
            vertical={card.vertical}
            title={card.title}
            href={card.href}
            meta={card.meta}
            needs={needs}
            firstQuest={card.firstQuest}
            pay={card.pay}
            payUnit={card.payUnit}
            applied={card.applied}
            clippedDate={card.clippedDate}
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

  /* the URL is the one truth for chips and presets */
  const verticalKey: VerticalKey = params.v ?? 'all';
  const activeKeys = useMemo(() => presetKeysFrom(params.p, PRESET_KEYS), [params.p]);

  /* text inputs buffer locally, debounce into the URL with replace so
     typing never spams history */
  const [searchRaw, setSearchRaw] = useState(params.q ?? '');
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
  const payFrom = useDebounced(payFromRaw.trim());
  const payTo = useDebounced(payToRaw.trim());
  const payFloor = parseAmount(payFrom);
  const payCeiling = parseAmount(payTo);

  /* what this page last wrote into the URL; anything else is history nav */
  const pushedRef = useRef<{ q?: string; from?: string; to?: string }>({
    q: params.q,
    from: params.from,
    to: params.to,
  });

  /* debounced edits -> URL (replace) */
  useEffect(() => {
    const next = { q: search || undefined, from: payFrom || undefined, to: payTo || undefined };
    const cur = pushedRef.current;
    if (cur.q === next.q && cur.from === next.from && cur.to === next.to) return;
    pushedRef.current = next;
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => ({ ...prev, ...next }),
      replace: true,
    });
  }, [search, payFrom, payTo, navigate]);

  /* back/forward -> inputs: adopt a URL this page did not write */
  useEffect(() => {
    const cur = pushedRef.current;
    if (params.q === cur.q && params.from === cur.from && params.to === cur.to) return;
    pushedRef.current = { q: params.q, from: params.from, to: params.to };
    setSearchRaw(params.q ?? '');
    setPayFromRaw(params.from ?? '');
    setPayToRaw(params.to ?? '');
  }, [params.q, params.from, params.to]);

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
      ...verticalParams(verticalKey),
      ...presetParams(activeKeys),
      search: search || undefined,
      salary_min: payFloor ?? undefined,
      sort_by: sortNewest ? 'date_found' : 'overall_score',
      sort_order: 'desc',
      page_size: PAGE_SIZE,
    }),
    [verticalKey, activeKeys, search, payFloor, sortNewest],
  );

  const filtersKey = JSON.stringify(baseFilters);
  const pages = pageState.key === filtersKey ? pageState.pages : 1;

  const firstPage = useApplications({ ...baseFilters, page: 1 });
  const total = firstPage.data?.total;

  const questScoped = verticalKey !== 'all' && verticalKey !== 'career';
  const visiblePresets = PRESETS.filter((p) => !p.careerOnly || !questScoped);

  function selectVertical(key: VerticalKey) {
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => {
        let keys = presetKeysFrom(prev.p, PRESET_KEYS);
        if (key !== 'all' && key !== 'career') {
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
      ...verticalParams(verticalKey),
      ...presetParams(probe),
      search: search || undefined,
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

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          {VERTICAL_KEYS.map((key) => (
            <VerticalChip
              key={key}
              verticalKey={key}
              active={verticalKey === key}
              onSelect={() => selectVertical(key)}
            />
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 12 }}>
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

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 12 }}>
          <input
            className="qb-board-filter qb-board-search"
            placeholder="Search the board"
            aria-label="Search the board"
            value={searchRaw}
            onChange={(e) => setSearchRaw(e.target.value)}
          />
          <input
            className="qb-board-filter qb-board-pay"
            inputMode="numeric"
            placeholder="pay from $150k"
            aria-label="Pay floor, a year"
            value={payFromRaw}
            onChange={(e) => setPayFromRaw(e.target.value)}
          />
          <input
            className="qb-board-filter qb-board-pay"
            inputMode="numeric"
            placeholder="to $210k"
            aria-label="Pay ceiling, a year"
            value={payToRaw}
            onChange={(e) => setPayToRaw(e.target.value)}
          />
          <span style={{ fontSize: 12.5, color: 'var(--mute)' }}>
            Only counts pay the posting states; jobs with no stated pay stay on the board.
          </span>
        </div>

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

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: 16,
            marginTop: 22,
          }}
        >
          {Array.from({ length: pages }, (_, i) => (
            <BoardCards
              key={i + 1}
              filters={{ ...baseFilters, page: i + 1 }}
              payCeiling={payCeiling}
              labels={labels}
              onOpenSheet={setSheetApp}
              onExplain={setExplainApp}
            />
          ))}
        </div>

        {total !== undefined && pages * PAGE_SIZE < total && (
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 28 }}>
            <button
              type="button"
              className="qb-textlink"
              onClick={() => setPageState({ key: filtersKey, pages: pages + 1 })}
            >
              more
            </button>
          </div>
        )}

        <p style={{ padding: '40px 0 64px', fontSize: 13, color: 'var(--mute)', margin: 0 }}>
          Every date on this board is the true post date; postings with no verifiable date say nothing.
        </p>
      </div>

      <RequirementSheet app={sheetApp} labels={labels} onClose={() => setSheetApp(null)} />
      <ExplainSheet app={explainApp} labels={labels} onClose={() => setExplainApp(null)} />
    </>
  );
}
