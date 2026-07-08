import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import { createRoute, Link } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import {
  Chip,
  LedgerRow,
  PlainButton,
  QuestCard,
  Sheet,
  StampDefs,
  TextLink,
} from '@questboard/ui';
import { useApplications, useUpdateStatus } from '@/hooks/use-applications';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import {
  CLIP_STATUS,
  parseAmount,
  toBoardCard,
  withinPayCeiling,
} from '@/utils/board-card';
import type { ApplicationFilters, ApplicationResponse, RequirementMatch } from '@/types/application';

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/board',
  component: BoardPage,
});

const PAGE_SIZE = 24;

/* Preset chips. Each one maps 1:1 onto a real API filter param, so its
   count is the API's own total for that query, never a guess. Chips that
   share a group write the same param and stay mutually exclusive. */
interface Preset {
  key: string;
  label: string;
  params: Partial<ApplicationFilters>;
  group?: string;
}

const PRESETS: Preset[] = [
  { key: 'remote', label: 'remote', params: { is_remote: true } },
  { key: 'strong', label: 'strong apply', params: { recommendation: 'STRONG_APPLY' } },
  { key: 'score50', label: 'scored 50 or better', params: { min_score: 50 } },
  { key: 'early', label: 'early startup', params: { company_type: 'Early Startup' }, group: 'company' },
  { key: 'bigtech', label: 'big tech', params: { company_type: 'Big Tech' }, group: 'company' },
];

function presetParams(activeKeys: Set<string>): Partial<ApplicationFilters> {
  let merged: Partial<ApplicationFilters> = {};
  for (const preset of PRESETS) {
    if (activeKeys.has(preset.key)) merged = { ...merged, ...preset.params };
  }
  return merged;
}

const inputStyle: CSSProperties = {
  border: '1px solid var(--hair)',
  background: 'var(--paper)',
  borderRadius: 4,
  padding: '6px 12px',
  fontFamily: 'inherit',
  fontSize: 13.5,
  color: 'var(--ink)',
};

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

function BoardCards({
  filters,
  payCeiling,
  labels,
  onOpenSheet,
}: {
  filters: ApplicationFilters;
  payCeiling: number | null;
  labels: Record<string, string>;
  onOpenSheet: (app: ApplicationResponse) => void;
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
            vertical="career"
            title={card.title}
            href={card.href}
            meta={card.meta}
            needs={needs}
            pay={card.pay}
            payUnit={card.payUnit}
            applied={card.applied}
            clippedDate={card.clippedDate}
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

function BoardPage() {
  const labels = useSourceLabels();
  const [activeKeys, setActiveKeys] = useState<Set<string>>(new Set());
  const [searchRaw, setSearchRaw] = useState('');
  const [payFromRaw, setPayFromRaw] = useState('');
  const [payToRaw, setPayToRaw] = useState('');
  /* newest first by default: the API's score sort floats unscored rows to
     the top (desc nullsfirst), which reads as noise on a board */
  const [sortNewest, setSortNewest] = useState(true);
  /* pages loaded, keyed to the filters that loaded them: any filter change
     starts back at one page without an effect */
  const [pageState, setPageState] = useState<{ key: string; pages: number }>({ key: '', pages: 1 });
  const [sheetApp, setSheetApp] = useState<ApplicationResponse | null>(null);

  const search = useDebounced(searchRaw.trim());
  const payFloor = parseAmount(useDebounced(payFromRaw));
  const payCeiling = parseAmount(useDebounced(payToRaw));

  const baseFilters = useMemo<ApplicationFilters>(
    () => ({
      ...presetParams(activeKeys),
      search: search || undefined,
      salary_min: payFloor ?? undefined,
      sort_by: sortNewest ? 'date_found' : 'overall_score',
      sort_order: 'desc',
      page_size: PAGE_SIZE,
    }),
    [activeKeys, search, payFloor, sortNewest],
  );

  const filtersKey = JSON.stringify(baseFilters);
  const pages = pageState.key === filtersKey ? pageState.pages : 1;

  const firstPage = useApplications({ ...baseFilters, page: 1 });
  const total = firstPage.data?.total;

  function toggle(key: string) {
    setActiveKeys((prev) => {
      const next = new Set(prev);
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
      return next;
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
      ...presetParams(probe),
      search: search || undefined,
      salary_min: payFloor ?? undefined,
      page: 1,
      page_size: 1,
    };
  }

  return (
    <div className="qb-page" style={{ position: 'fixed', inset: 0, zIndex: 40, overflowY: 'auto' }}>
      <StampDefs />
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '0 44px 96px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, padding: '52px 0 26px' }}>
          <h1
            style={{
              fontFamily: 'var(--serif)',
              fontVariationSettings: "'opsz' 80",
              fontWeight: 560,
              fontSize: 26,
              letterSpacing: '-.01em',
              margin: 0,
            }}
          >
            The board
          </h1>
          <span className="qb-num" style={{ fontSize: 13, color: 'var(--mute)' }}>
            {total !== undefined ? `${total} live` : 'loading'}
          </span>
          <button
            type="button"
            onClick={() => setSortNewest((v) => !v)}
            style={{
              marginLeft: 'auto',
              fontSize: 14,
              color: 'var(--soft)',
              background: 'none',
              border: 0,
              fontFamily: 'inherit',
              cursor: 'pointer',
            }}
          >
            Sort:{' '}
            <b style={{ fontWeight: 500, color: 'var(--ink)' }}>
              {sortNewest ? 'newly found' : 'best score'}
            </b>
          </button>
          <Link
            to="/applications"
            search={{ run: undefined, scope: undefined }}
            className="qb-textlink"
            style={{ fontSize: 14 }}
          >
            Back to the app
          </Link>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <Chip vertical="career" label="Career" active count={total} />
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 12 }}>
          {PRESETS.map((preset) => (
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
            style={{ ...inputStyle, width: 240 }}
            placeholder="Search the board"
            aria-label="Search the board"
            value={searchRaw}
            onChange={(e) => setSearchRaw(e.target.value)}
          />
          <input
            style={{ ...inputStyle, width: 110 }}
            inputMode="numeric"
            placeholder="pay from $150k"
            aria-label="Pay floor, a year"
            value={payFromRaw}
            onChange={(e) => setPayFromRaw(e.target.value)}
          />
          <input
            style={{ ...inputStyle, width: 110 }}
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
    </div>
  );
}
