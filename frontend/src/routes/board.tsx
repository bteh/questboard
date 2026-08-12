import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createRoute, Link, redirect, useNavigate } from '@tanstack/react-router';
import { useQueries, useQuery } from '@tanstack/react-query';
import { HugeiconsIcon } from '@hugeicons/react';
import { Search01Icon } from '@hugeicons/core-free-icons';
import { Route as appRoute } from './app';
import {
  Chip,
  LedgerRow,
  PlainButton,
  Sheet,
  StampDefs,
  TextLink,
} from '@questboard/ui';
import { getApplications, getProfileWork } from '@/api/applications';
import { useApplications, useUpdateStatus } from '@/hooks/use-applications';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { ExplainSheet } from '@/components/board/explain-sheet';
import { RestockLine } from '@/components/board/restock-line';
import { QuestRestockButton } from '@/components/board/quest-restock';
import { boardEmptyState, boardFiltersActive } from '@/features/board/board-empty';
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
} from '@/utils/board-card';
import { checkedAgoLabel } from '@/features/board/freshness';
import {
  POSTED_OPTIONS,
  hiddenDatesClause,
  normalizePostedDays,
  foundWithinDays,
  postedWithinDays,
  type PostedDaysKey,
} from '@/features/board/posted-filter';
import { FacetChips } from '@/features/board/facet-chips';
import {
  isCareerKind,
  kindParams,
  sortByFor,
  workflowForKind,
  type KindKey,
  type Workflow,
} from '@/features/board/kind-params';
import type { BoardSummaryFilters, CareerRefreshReceipt } from '@/api/board';
import { KindRail } from '@/features/board/kind-rail';
import { LaneTabs } from '@/features/board/lane-tabs';
import { PlacePicker } from '@/features/board/place-picker';
import { JobsSetupStrip } from '@/features/board/jobs-callout';
import { showBankBonusBridge } from '@/features/board/bridge-line';
import { WorkToolbar } from '@/features/board/work-toolbar';
import { useSearchContext } from '@/contexts/search-context';
import { SourceCategoryChips } from '@/features/board/source-category-chips';
import {
  advanceWorkCutoff,
  countNewSince,
  cutoffAfterPull,
  newSinceLine,
  readWorkCutoff,
} from '@/features/board/new-since';
import { JobDetailSheet } from '@/features/board/job-detail-sheet';
import { newestFirst } from '@/features/board/poster-model';
import { PosterWall } from '@/features/board/poster-wall';
import { useBoardSummary } from '@/hooks/use-board-summary';
import { useAgentRunActive } from '@/hooks/use-agent-clients';
import { useOnboardingState } from '@/hooks/use-workspace';
import { kindSearchForLane } from '@/features/board/lane-filter-state';
import { workSortLabel } from '@/features/board/review-coverage';
import {
  receiptFromRunResult,
  refreshAwareSinceLine,
} from '@/features/board/refresh-receipt';
import type {
  ApplicationFilters,
  ApplicationResponse,
  ProfileWorkListResponse,
  RequirementMatch,
} from '@/types/application';
import '@/components/board/board.css';
import '@/features/board/board-felt.css';

/* Filter state lives in the URL (?v, ?q, ?from, ?to, ?p, ?src): a filtered
   board is a shareable address, back/forward walks chip changes, and the
   topbar search box submits into ?q=. The last state persists at
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
    /* a shared ?job link is about the one posting; redirecting to saved
       filters would drop it */
    if (search.job !== undefined) return;
    if (hasBoardParams(search)) return;
    const saved = readSavedBoardState();
    if (saved && hasBoardParams(saved)) {
      throw redirect({
        to: '/board',
        search: {
          v: saved.v, f: saved.f, q: saved.q, place: saved.place, near: saved.near,
          from: saved.from, to: saved.to, p: saved.p, days: saved.days, src: saved.src,
        },
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
  questOnly?: boolean;
}

const PRESETS: Preset[] = [
  {
    key: 'noexp',
    label: 'no experience needed',
    params: { first_quest_ok: true },
    questOnly: true,
  },
  { key: 'remote', label: 'remote', params: { is_remote: true }, questOnly: true },
  {
    key: 'founding',
    label: 'founding',
    params: { founding_only: true },
    careerOnly: true,
  },
  /* score_source narrows to AI-scored rows: the keyword fallback stamps
     STRONG_APPLY on a lenient scale, and those guesses must not pad this
     chip's count or ride its filter */
];

/* The 7-day posted shortcut writes ?days=7: the date select remains the one
   source of truth and the chip lights whenever that rolling window is active.
   Legacy ?p=fresh URLs fold into days=7 inside validateBoardSearch. */
const FRESH_CHIP: Preset = {
  key: 'fresh',
  label: 'posted last 7 days',
  params: { posted_within_days: 7 },
};

const PRESET_KEYS = PRESETS.map((p) => p.key);

/* Moving to another kind or lane: a facet belongs to its kind, the
   source-category chip belongs to the work lane, and a hidden careerOnly
   preset must not keep silently filtering the feed. */
function kindSearch(prev: BoardParams, key: KindKey): BoardParams {
  return kindSearchForLane(prev, key, PRESETS, PRESET_KEYS);
}

/* The lane switcher's targets. The active tab keeps its state (clicking it
   goes nowhere new); the other tab lands on its lane's root. */
function laneSearchFor(lane: Workflow) {
  return (prev: BoardParams): BoardParams =>
    workflowForKind(prev.v) === lane ? prev : kindSearch(prev, lane === 'work' ? 'work' : 'all');
}

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
  const { data: onboarding } = useOnboardingState();

  /* the URL is the one truth for the kind tag, presets, and the work
     lane's source-category chip */
  const kindKey: KindKey = params.v ?? 'all';
  const careerLane = isCareerKind(kindKey);
  const urlActiveKeys = useMemo(() => presetKeysFrom(params.p, PRESET_KEYS), [params.p]);
  /* Like the date select below, one-click Work filters update the query
     locally first. The URL remains durable history, but is no longer on the
     critical path between a click and the filtered result. */
  const [foundingOnly, setFoundingOnlyView] = useState(urlActiveKeys.has('founding'));
  const pushedFoundingRef = useRef(urlActiveKeys.has('founding'));
  const [sourceCategoryView, setSourceCategoryView] = useState<string | null>(params.src ?? null);
  const pushedSourceCategoryRef = useRef<string | null>(params.src ?? null);
  const activeKeys = useMemo(() => {
    const next = new Set(urlActiveKeys);
    if (careerLane && foundingOnly) next.add('founding');
    else next.delete('founding');
    return next;
  }, [urlActiveKeys, careerLane, foundingOnly]);
  const sourceCategory = careerLane ? sourceCategoryView : null;
  /* text inputs buffer locally, debounce into the URL with replace so
     typing never spams history */
  const [searchRaw, setSearchRaw] = useState(params.q ?? '');
  const [placeRaw, setPlaceRaw] = useState(params.place ?? '');
  const [nearOnly, setNearOnly] = useState(params.near === '1');
  const [payFromRaw, setPayFromRaw] = useState(params.from ?? '');
  const [payToRaw, setPayToRaw] = useState(params.to ?? '');
  /* Selects should feel like filters, not navigation. Apply the date choice
     to the query synchronously, then mirror it into the URL for history and
     persistence. Waiting for the router round-trip made New today appear to
     do nothing until some later action (usually Get new jobs) caused a
     rerender/refetch. */
  const [postedDays, setPostedDaysView] = useState<PostedDaysKey | undefined>(params.days);
  const pushedPostedDaysRef = useRef<PostedDaysKey | undefined>(params.days);
  const postedWithin = postedWithinDays(postedDays);
  const foundWithin = foundWithinDays(postedDays);
  /* newest first by default: the API's score sort floats unscored rows to
     the top (desc nullsfirst), which reads as noise on a board */
  const [sortNewest, setSortNewest] = useState(() => readSavedBoardState()?.sort !== 'score');
  /* has the reader clicked the sort this visit? Until they do, verdicts from
     the assistant's last run make fit order the work lane's default */
  const [sortTouched, setSortTouched] = useState(false);
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
  const payCurrency = onboarding?.preferences.compensation.currency?.trim().toUpperCase() || undefined;

  /* near me only is meaningless without a place, so it rides the place text */
  const nearParam = nearOnly && place ? '1' : undefined;

  /* what this page last wrote into the URL; anything else is history nav */
  const pushedRef = useRef<{ q?: string; place?: string; near?: string; from?: string; to?: string }>({
    q: params.q,
    place: params.place,
    near: params.near,
    from: params.from,
    to: params.to,
  });

  /* debounced edits -> URL (replace) */
  useEffect(() => {
    const next = {
      q: search || undefined,
      place: place || undefined,
      near: nearParam,
      from: payFrom || undefined,
      to: payTo || undefined,
    };
    const cur = pushedRef.current;
    if (
      cur.q === next.q &&
      cur.place === next.place &&
      cur.near === next.near &&
      cur.from === next.from &&
      cur.to === next.to
    )
      return;
    pushedRef.current = next;
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => ({ ...prev, ...next }),
      replace: true,
    });
  }, [search, place, nearParam, payFrom, payTo, navigate]);

  /* back/forward -> inputs: adopt a URL this page did not write */
  useEffect(() => {
    const cur = pushedRef.current;
    if (
      params.q === cur.q &&
      params.place === cur.place &&
      params.near === cur.near &&
      params.from === cur.from &&
      params.to === cur.to
    )
      return;
    pushedRef.current = {
      q: params.q, place: params.place, near: params.near, from: params.from, to: params.to,
    };
    setSearchRaw(params.q ?? '');
    setPlaceRaw(params.place ?? '');
    setNearOnly(params.near === '1');
    setPayFromRaw(params.from ?? '');
    setPayToRaw(params.to ?? '');
  }, [params.q, params.place, params.near, params.from, params.to]);

  /* Back/forward may change the URL without going through the select. Adopt
     that external value, while leaving our own local-first update alone. */
  useEffect(() => {
    if (params.days === pushedPostedDaysRef.current) return;
    pushedPostedDaysRef.current = params.days;
    setPostedDaysView(params.days);
  }, [params.days]);

  useEffect(() => {
    const fromUrl = urlActiveKeys.has('founding');
    if (fromUrl === pushedFoundingRef.current) return;
    pushedFoundingRef.current = fromUrl;
    setFoundingOnlyView(fromUrl);
  }, [urlActiveKeys]);

  useEffect(() => {
    const fromUrl = params.src ?? null;
    if (fromUrl === pushedSourceCategoryRef.current) return;
    pushedSourceCategoryRef.current = fromUrl;
    setSourceCategoryView(fromUrl);
  }, [params.src]);

  /* the whole state persists locally so the next bare /board reopens it */
  useEffect(() => {
    saveBoardState({
      v: params.v,
      f: params.f,
      q: params.q,
      place: params.place,
      near: params.near,
      from: params.from,
      to: params.to,
      p: params.p,
      days: params.days,
      src: params.src,
      sort: sortNewest ? undefined : 'score',
    });
  }, [params.v, params.f, params.q, params.place, params.near, params.from, params.to, params.p, params.days, params.src, sortNewest]);

  const baseFilters = useMemo<ApplicationFilters>(
    () => ({
      ...kindParams(kindKey),
      ...presetParams(activeKeys),
      facet: params.f,
      search: search || undefined,
      location: place || undefined,
      location_strict: nearParam ? true : undefined,
      ...(careerLane
        ? {
            salary_min: payFloor ?? undefined,
            salary_max: payCeiling ?? undefined,
            salary_currency: payFloor !== null || payCeiling !== null ? payCurrency : undefined,
          }
        : {}),
      posted_within_days: postedWithin,
      found_within_days: foundWithin,
      source_category: sourceCategory ?? undefined,
      /* quest rows have no rank_score, so only the work lane offers the
         best-score sort; quest lanes stay on the honest date sort */
      sort_by: sortByFor(kindKey, sortNewest),
      sort_order: 'desc',
      page_size: PAGE_SIZE,
      scope: 'board',
    }),
    [kindKey, careerLane, activeKeys, params.f, search, place, nearParam, payFloor, payCeiling, payCurrency, postedWithin, foundWithin, sortNewest, sourceCategory],
  );

  /* the rail's counts must describe THIS board: the same user filters ride
     the summary query (per-kind counts stay per-kind, so no vertical) */
  const summaryFilters = useMemo<BoardSummaryFilters>(
    () => ({
      // Founding is a Work-only title facet. The summary rail describes Side
      // quests and its endpoint intentionally has no founding vocabulary.
      ...(isCareerKind(kindKey) ? {} : presetParams(activeKeys)),
      search: search || undefined,
      location: place || undefined,
      location_strict: nearParam ? true : undefined,
      ...(careerLane
        ? {
            salary_min: payFloor ?? undefined,
            salary_max: payCeiling ?? undefined,
            salary_currency: payFloor !== null || payCeiling !== null ? payCurrency : undefined,
          }
        : {}),
      posted_within_days: postedWithin,
      found_within_days: foundWithin,
    }),
    [kindKey, careerLane, activeKeys, search, place, nearParam, payFloor, payCeiling, payCurrency, postedWithin, foundWithin],
  );
  const summary = useBoardSummary(summaryFilters).data;
  const checkedAgo = checkedAgoLabel(
    careerLane ? summary?.career_checked_at : summary?.side_quest_checked_at,
    new Date(),
    careerLane ? 'sources' : 'latest source',
  );

  const filtersKey = JSON.stringify(baseFilters);
  const pages = pageState.key === filtersKey ? pageState.pages : 1;
  /* one query per loaded page, on the same ['applications', filters] keys
     the rest of the app shares, flattened so the Jobs lane can group rows
     across pages */
  const pageQueries = useQueries({
    queries: Array.from({ length: pages }, (_, i) => ({
      queryKey: [careerLane ? 'profile-work' : 'applications', { ...baseFilters, page: i + 1 }],
      queryFn: () => careerLane
        ? getProfileWork({ ...baseFilters, page: i + 1 })
        : getApplications({ ...baseFilters, page: i + 1 }),
      refetchInterval: foundWithin ? 60_000 : false,
    })),
  });
  const firstPage = pageQueries[0];
  const total = firstPage.data?.total;
  const workMeta = careerLane
    ? firstPage.data as ProfileWorkListResponse | undefined
    : undefined;
  /* the pay ceiling is a server param now (salary_max in baseFilters), so
     the pages arrive already trimmed and the total matches what shows */
  const visibleItems = pageQueries.flatMap((q) => q.data?.items ?? []);
  /* Once the assistant has ranked, its fit order (from the API) wins: don't
     re-split by recency or claim an exact "new since" count, both of which
     assume newest-first. */
  const hasAgentVerdicts = careerLane && visibleItems.some((app) => app.agent_fit);
  /* fit order is the default the moment verdicts exist; an explicit sort
     click this visit wins either way */
  const fitOrder = hasAgentVerdicts && (sortTouched ? !sortNewest : true);
  /* what the sort control honestly shows: fit order reads as best score */
  const sortShowsBest = fitOrder || !sortNewest;
  const sortLabel = workSortLabel(sortShowsBest, workMeta?.unreviewed_count);
  /* the roles API keeps ranked rows first whatever sort it is asked for, so
     an explicit "newly found" pick with verdicts re-orders the loaded rows */
  const wallItems =
    careerLane && hasAgentVerdicts && !fitOrder ? newestFirst(visibleItems) : visibleItems;

  /* the work lane's filter status line compares what shows against the
     whole lane. The baseline count only fetches while a toolbar filter
     narrows; otherwise the filtered total already IS the lane total. */
  const workFiltersOn =
    careerLane &&
    Boolean(
      search || place || payFloor !== null || payCeiling !== null || postedDays ||
        activeKeys.has('founding'),
    );
  const workLaneBase = useMemo<ApplicationFilters>(
    () => ({
      ...kindParams(kindKey),
      facet: params.f,
      source_category: sourceCategory ?? undefined,
      page: 1,
      page_size: 1,
      scope: 'board',
    }),
    [kindKey, params.f, sourceCategory],
  );
  const workLaneTotalQuery = useQuery({
    queryKey: ['profile-work', workLaneBase],
    queryFn: () => getProfileWork(workLaneBase),
    enabled: workFiltersOn,
  });
  const workLaneTotal = workFiltersOn ? workLaneTotalQuery.data?.total : total;

  /* the quest lanes' honest clause needs a baseline: the same query without
     the posted window (count only), fetched only while the window is on.
     shown < baseline means the window hid rows, some of them for having no
     verifiable date, and the tray note says so. */
  const questBaselineFilters = useMemo<ApplicationFilters>(
    () => ({ ...baseFilters, posted_within_days: undefined, page: 1, page_size: 1 }),
    [baseFilters],
  );
  const questBaselineQuery = useQuery({
    queryKey: ['applications', questBaselineFilters],
    queryFn: () => getApplications(questBaselineFilters),
    enabled: !careerLane && postedWithin !== undefined,
  });
  const questHiddenNote = careerLane
    ? null
    : hiddenDatesClause({
        days: postedDays,
        shown: total,
        baseline: questBaselineQuery.data?.total,
      });

  /* careerOnly presets lean on fields only career rows carry (score,
     company type), and career rows only live in the Jobs lane now, so the
     presets show there and nowhere else */
  const visiblePresets = careerLane
    ? []
    : PRESETS.filter((p) => !p.careerOnly);

  /* the Jobs lane's last-visit cutoff: frozen at page load, advanced once
     after the lane's first successful render, so labels hold still. One
     deliberate exception below: a completed pull re-anchors it. */
  const [workCutoff, setWorkCutoff] = useState(() => readWorkCutoff());
  const cutoffAdvanced = useRef(false);
  const laneLoaded = firstPage.isSuccess;
  useEffect(() => {
    if (!careerLane || !laneLoaded || cutoffAdvanced.current) return;
    cutoffAdvanced.current = true;
    advanceWorkCutoff();
  }, [careerLane, laneLoaded]);

  /* A desktop app stays open for days, so a mount-time cutoff drifts into
     "new this week". Pressing Get new jobs is when the reader starts caring
     what changed: when the pull completes, "new" re-anchors at the pull's
     start, and the stored cutoff advances so the next visit agrees. */
  const {
    state: searchState,
    result: searchResult,
    error: searchError,
  } = useSearchContext();
  const agentRefreshRunning = useAgentRunActive();
  const pullStartedAt = useRef<string | null>(null);
  useEffect(() => {
    if (searchState === 'running' && pullStartedAt.current === null) {
      pullStartedAt.current = new Date().toISOString();
      return;
    }
    if (searchState === 'completed' && pullStartedAt.current !== null) {
      const startedAt = pullStartedAt.current;
      pullStartedAt.current = null;
      if (careerLane) {
        setWorkCutoff((prev) => cutoffAfterPull(prev, startedAt));
        advanceWorkCutoff();
      }
    }
    if (searchState === 'failed') pullStartedAt.current = null;
  }, [searchState, careerLane]);

  /* which empty board is this: the filters cut everything, or nothing has
     been fetched yet? The message must match the cause. */
  const visibleFiltersActive = boardFiltersActive({
    search,
    place,
    payFrom,
    payTo,
    facet: params.f,
    presetCount: activeKeys.size,
    sourceCategory,
    postedDays,
  });
  const emptyState = boardEmptyState(total, visibleFiltersActive);

  const newSince = careerLane
    ? countNewSince(visibleItems, workCutoff, {
        newestFirst: sortNewest && !hasAgentVerdicts,
        hasMore: total === undefined || pages * PAGE_SIZE < total,
      })
    : null;
  const normalSinceLine = newSince ? newSinceLine(newSince, workCutoff) : null;
  const liveRefreshReceipt: CareerRefreshReceipt | null =
    searchState === 'running' || agentRefreshRunning
      ? {
          run_id: '',
          status: 'running',
          started_at: null,
          completed_at: null,
          jobs_found: 0,
          new_jobs: 0,
          error: null,
          source_coverage: null,
        }
      : searchState === 'failed'
        ? {
            run_id: '',
            status: 'failed',
            started_at: null,
            completed_at: null,
            jobs_found: 0,
            new_jobs: 0,
            error: searchError,
            source_coverage: null,
          }
        : searchState === 'completed' && searchResult
          ? {
              run_id: searchResult.run_id,
              started_at: null,
              completed_at: null,
              ...receiptFromRunResult(searchResult),
            }
          : null;
  const effectiveRefreshReceipt = liveRefreshReceipt ?? summary?.career_refresh ?? null;
  const sinceLine = refreshAwareSinceLine(normalSinceLine, effectiveRefreshReceipt);

  function selectKind(key: KindKey) {
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => kindSearch(prev, key),
    });
  }

  /* one facet at a time; clicking the active one clears it */
  function toggleFacet(id: string) {
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => ({ ...prev, f: prev.f === id ? undefined : id }),
    });
  }

  /* the work lane's source-category chip rides the URL (?src=) and the
     saved board state, so a reload or nav keeps the selection */
  function selectSourceCategory(category: string | null) {
    setSourceCategoryView(category);
    pushedSourceCategoryRef.current = category;
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => ({ ...prev, src: category ?? undefined }),
    });
  }

  /* the posted window rides the URL (?days=) like every other filter */
  function setPostedDays(value: PostedDaysKey | undefined) {
    setPostedDaysView(value);
    pushedPostedDaysRef.current = value;
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => ({ ...prev, days: value }),
    });
  }

  function toggle(key: string) {
    if (key === 'founding') {
      const next = !activeKeys.has('founding');
      setFoundingOnlyView(next);
      pushedFoundingRef.current = next;
    }
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

  /* the detail sheet rides the URL (?job=), so refresh and share reopen it;
     the board stays mounted underneath, so closing never loses the scroll */
  function openDetail(app: ApplicationResponse) {
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => ({ ...prev, job: app.id }),
    });
  }
  function closeDetail() {
    void navigate({
      to: '/board',
      search: (prev: BoardParams) => ({ ...prev, job: undefined }),
      replace: true,
    });
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
      facet: params.f,
      search: search || undefined,
      location: place || undefined,
      location_strict: nearParam ? true : undefined,
      ...(careerLane
        ? {
            salary_min: payFloor ?? undefined,
            salary_max: payCeiling ?? undefined,
            salary_currency: payFloor !== null || payCeiling !== null ? payCurrency : undefined,
          }
        : {}),
      posted_within_days: postedWithin,
      /* the probed chip's own params win: the fresh chip counts its 7-day
         window even while the select holds a different one */
      ...preset.params,
      // The Fresh chip replaces the date select. While "new today" is
      // active, its first-seen constraint must not leak into the 7-day count.
      found_within_days: preset.key === 'fresh' ? undefined : foundWithin,
      page: 1,
      page_size: 1,
      scope: 'board',
    };
  }

  return (
    <>
      <StampDefs />
      <div className="qb-board-wrap">
        <div className="qb-board-head">
          <h1>The board</h1>
          <span className="qb-live">{total !== undefined ? `${total} live` : 'loading'}</span>
          {/* best score is honest only where rank_score exists (career
              rows), so the toggle lives on the work lane; quest lanes are
              always newest first and say so without a dead switch */}
          {careerLane ? (
            <button
              type="button"
              className="qb-sort"
              onClick={() => {
                setSortTouched(true);
                setSortNewest(sortShowsBest);
              }}
            >
              Matches your target roles · sort: <b>{sortLabel}</b>
            </button>
          ) : (
            <span className="qb-sort">newest first</span>
          )}
        </div>

        {/* the two workflows, named as the page's primary structure; the
            kind rail below belongs to Side quests, the Find work lane keeps
            its own toolbar */}
        <LaneTabs kindKey={kindKey} searchFor={laneSearchFor} />

        {/* the Jobs lane's toolbar owns its own run door and status line */}
        {!careerLane && <RestockLine />}

        {!careerLane && (
          <KindRail selected={kindKey} onSelect={selectKind} filters={summaryFilters} />
        )}

        {!careerLane && kindKey !== 'all' && (
          <FacetChips
            kind={kindKey}
            selected={params.f}
            countBase={baseFilters}
            onToggle={toggleFacet}
          />
        )}

        {!careerLane && (
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
            <PresetChip
              preset={FRESH_CHIP}
              active={postedDays === '7'}
              countFilters={countFilters(FRESH_CHIP)}
              onToggle={() => setPostedDays(postedDays === '7' ? undefined : '7')}
            />
          </div>
        )}

        {careerLane ? (
          <>
            <JobsSetupStrip
              profileConfigured={workMeta?.profile_configured}
              jurisdictionConfigured={workMeta?.jurisdiction_configured}
            />
            <WorkToolbar
              checkedAgo={checkedAgo}
              refreshReceipt={effectiveRefreshReceipt}
              shownCount={total}
              laneTotal={workLaneTotal}
              reviewedCount={workMeta?.reviewed_count}
              unreviewedCount={workMeta?.unreviewed_count}
              filtering={firstPage.isFetching && visibleFiltersActive}
              search={searchRaw}
              onSearch={setSearchRaw}
              place={placeRaw}
              onPlace={setPlaceRaw}
              nearOnly={nearOnly}
              onNearOnly={setNearOnly}
              payFrom={payFromRaw}
              onPayFrom={setPayFromRaw}
              payTo={payToRaw}
              onPayTo={setPayToRaw}
              postedDays={postedDays}
              onPostedDays={setPostedDays}
              foundingOnly={activeKeys.has('founding')}
              onFoundingOnly={() => toggle('founding')}
              sourceCategory={sourceCategory}
            />
            <SourceCategoryChips
              counts={workMeta?.source_categories}
              selected={sourceCategory}
              onSelect={selectSourceCategory}
              foundingOnly={activeKeys.has('founding')}
              onFoundingToggle={() => toggle('founding')}
            />
          </>
        ) : (
          <>
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
              <PlacePicker
                value={placeRaw}
                onChange={setPlaceRaw}
                ariaLabel="Filter by place; remote quests pass unless near me only is on"
                className="qb-tray-field qb-tray-place"
              />
              <label className="qb-tray-field qb-tray-posted">
                <span className="qb-tray-label">date</span>
                <select
                  aria-label="Filter by date"
                  value={postedDays ?? ''}
                  onChange={(e) => setPostedDays(normalizePostedDays(e.target.value))}
                >
                  {POSTED_OPTIONS.map((opt) => (
                    <option key={opt.value || 'any'} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="qb-tray-note">
              {placeRaw.trim() ? (
                <>
                  <label className="qb-nearme">
                    <input
                      type="checkbox"
                      checked={nearOnly}
                      onChange={(e) => setNearOnly(e.target.checked)}
                    />
                    near me only
                  </label>
                  {nearOnly
                    ? ' Showing only quests in that place. Remote and no-place quests are hidden.'
                    : ' A place keeps remote and no-place quests too. Tick near me only to hide them.'}
                </>
              ) : (
                'Pay counts only what the posting states. Quests with no stated pay stay on the board. A place keeps remote and no-place quests too.'
              )}
              {/* the posted window's confession, one quiet sentence, only
                  while the window is on and actually hid rows */}
              {questHiddenNote &&
                ` ${questHiddenNote.charAt(0).toUpperCase()}${questHiddenNote.slice(1)}.`}
            </p>
            <FirstRunNotice onStartHere={startHere} />
          </>
        )}

        {/* the bridge only where it belongs: the work lane (a new paycheck)
            and the house lane (the bonuses themselves); the link only where
            it goes somewhere else */}
        {showBankBonusBridge(kindKey) && (
          <p className="qb-jobs-bridge">
            Turn a new paycheck into a{' '}
            {kindKey === 'house' ? (
              'bank bonus'
            ) : (
              <button type="button" className="qb-textlink" onClick={() => selectKind('house')}>
                bank bonus
              </button>
            )}
            .
          </p>
        )}

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
        {emptyState === 'filtered-empty' && (
          <p style={{ marginTop: 40, fontSize: 14.5, color: 'var(--soft)' }}>
            Nothing on the board matches these filters. They are already applied—clear a filter
            or choose another value.
          </p>
        )}
        {/* nothing fetched, nothing set: the door is a restock, not a chip.
            The career lane keeps its own empty state below. */}
        {emptyState === 'truly-empty' && !careerLane && (
          <div className="qb-board-empty" role="status">
            <p className="qb-board-empty-lead">The board is empty right now.</p>
            <p>No quests have come in yet. One check fills it from the live sources.</p>
            <div style={{ marginTop: 14 }}>
              <QuestRestockButton big />
            </div>
            <p style={{ marginTop: 14, fontSize: 13.5, color: 'var(--mute)' }}>
              After a job instead?{' '}
              <button
                type="button"
                className="qb-textlink"
                style={{ fontSize: 'inherit' }}
                onClick={() => selectKind('work')}
              >
                The work lane
              </button>{' '}
              runs on its own rules.
            </p>
          </div>
        )}

        {careerLane && sinceLine && (
          <p className="qb-sinceline">
            {sinceLine}
            {sortShowsBest && (newSince?.count ?? 0) > 0 && (
              <>
                {' '}
                <button
                  type="button"
                  className="qb-textlink"
                  style={{ fontSize: 'inherit' }}
                  onClick={() => {
                    setSortTouched(true);
                    setSortNewest(true);
                  }}
                >
                  show new first
                </button>
              </>
            )}
          </p>
        )}

        {total !== undefined && total > 0 && (
          <div className="qb-felt">
            <PosterWall
              items={wallItems}
              labels={labels}
              cutoff={careerLane ? workCutoff : undefined}
              grouped={careerLane && sortNewest && !hasAgentVerdicts}
              fitGrouped={fitOrder}
              onOpenSheet={setSheetApp}
              onExplain={setExplainApp}
              onOpenDetail={openDetail}
            />
            <HouseRules />
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

        {total === 0 && careerLane && emptyState === 'truly-empty' && (
          <div className="qb-board-empty" role="status">
            <p className="qb-board-empty-lead">No jobs on your board for these roles yet.</p>
            <p>
              Click <b>“Get new jobs”</b> above to pull fresh postings. The pull takes about a
              minute.
            </p>
          </div>
        )}

        {/* one line, then a native disclosure for the rest: the legend must
            never read as a third paragraph of competing instructions */}
        <div className="qb-board-legend">
          <p>
            Pull <b>take it</b> to go straight to the source.
          </p>
          <details className="qb-legend-more">
            <summary>How the board works</summary>
            <p>The colour of the pin shows the kind of quest.</p>
            <p>Every date is the true post date. Postings with no verifiable date say nothing.</p>
            <p>Quests the sources stop listing come down on their own.</p>
            {checkedAgo && (
              <p>
                <Link to="/health" className="qb-legend-link" title="Source health">
                  <b>{checkedAgo}.</b>
                </Link>
              </p>
            )}
          </details>
        </div>
      </div>

      <RequirementSheet app={sheetApp} labels={labels} onClose={() => setSheetApp(null)} />
      <ExplainSheet app={explainApp} labels={labels} onClose={() => setExplainApp(null)} />
      <JobDetailSheet jobId={params.job ?? null} labels={labels} onClose={closeDetail} />
    </>
  );
}
