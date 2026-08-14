/* The Jobs lane's top block, in reading order. The actions row is one filled
   button. When the local assistant is ready it reads the resume, pulls, and
   ranks; otherwise it does the plain pull. Either way the receipt beside it
   says in plain words what the click will do, and one status line under it
   reports on whichever run is live. The filter tray sits demoted below: four
   fields that only narrow rows already on the board, with no button, so it
   cannot read as a search form. Only the top button touches the network,
   through the same pipeline the Restock page runs. The line under the
   filters states only what the data backs. Filter changes read the already
   stored board immediately; the filled button alone contacts external job
   sources. */

import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Link } from '@tanstack/react-router';
import { Loader2 } from 'lucide-react';
import { HugeiconsIcon } from '@hugeicons/react';
import { CoinsDollarIcon, Search01Icon } from '@hugeicons/core-free-icons';
import { SageButton } from '@questboard/ui';
import { useSearchContext } from '@/contexts/search-context';
import { restockProgress } from '@/components/board/restock-logic';
import { PlacePicker } from '@/features/board/place-picker';
import {
  POSTED_OPTIONS,
  hiddenDatesClause,
  normalizePostedDays,
  postedChipLabel,
  type PostedDaysKey,
} from '@/features/board/posted-filter';
import { payScopeNote } from '@/features/board/pay-scope';
import { AssistantSteps } from '@/features/board/assistant-steps.tsx';
import { SourceScoreboard } from '@/features/board/source-scoreboard.tsx';
import { useRunWorkSearch } from '@/features/board/use-run-work-search';
import { useAssistantReady } from '@/features/board/use-assistant-ready';
import { useRunAssistant } from '@/features/board/use-run-assistant';
import { reviewCoverageText } from '@/features/board/review-coverage';
import { useAgentProgress } from '@/hooks/use-agent-clients';
import { consumeFirstRunPending } from '@/components/onboarding/first-run';
import { useOnboardingState } from '@/hooks/use-workspace';
import { formatStatedPay, parseAmount } from '@/utils/board-card';
import type { CareerRefreshReceipt } from '@/api/board';
import {
  receiptFromRunResult,
  refreshReceiptCopy,
} from '@/features/board/refresh-receipt';
import {
  filterPlaceholder,
  filterTrayCaption,
  filterStatusText,
  primaryRunKind,
  pullReceipt,
} from '@/features/board/work-toolbar-logic';


interface WorkToolbarProps {
  /** the board summary's honest "sources checked Xh ago", or null */
  checkedAgo: string | null;
  /** newest durable Find Work attempt, including its source receipt */
  refreshReceipt?: CareerRefreshReceipt | null;
  /** rows the current toolbar filters keep: the filtered query's total */
  shownCount?: number;
  /** every job on the lane before the toolbar filters bite */
  laneTotal?: number;
  /** current assistant judgments across this filtered lane */
  reviewedCount?: number;
  /** jobs whose prior judgment is absent or stale */
  unreviewedCount?: number;
  /** a changed view filter is being applied to the stored board */
  filtering?: boolean;
  search: string;
  onSearch: (value: string) => void;
  place: string;
  onPlace: (value: string) => void;
  nearOnly: boolean;
  onNearOnly: (value: boolean) => void;
  payFrom: string;
  onPayFrom: (value: string) => void;
  /** the ceiling has no input here, but a set ?to= keeps trimming and shows
      as a removable chip */
  payTo: string;
  onPayTo: (value: string) => void;
  /** the posted window (?days): narrows the VIEW only; the saved
      max_days_old in Settings stays the PULL window and is untouched */
  postedDays: PostedDaysKey | undefined;
  onPostedDays: (value: PostedDaysKey | undefined) => void;
  /** Named founding roles plus source-stated first functional hires. */
  foundingOnly: boolean;
  onFoundingOnly: () => void;
}

interface FilterChip {
  key: string;
  label: string;
  clear: () => void;
}

/* The pull's own report, under the actions row it belongs to: a running
   clock while sources answer, the failure with its retry door, and the
   completed tally. Idle renders nothing; the filter line below carries the
   board's counts. Stays mounted so the completion toast can fire even when
   the run ends off-screen. */
function RunStatusLine({ persistedReceipt }: { persistedReceipt?: CareerRefreshReceipt | null }) {
  const { state, messages, progress, result, error } = useSearchContext();

  // A running clock so the wait shows life, plus a toast on the running->done
  // transition so you know it finished even if you'd tabbed away.
  const [elapsed, setElapsed] = useState(0);
  const prevState = useRef(state);
  useEffect(() => {
    if (state !== 'running') return;
    const id = setInterval(() => setElapsed((seconds) => seconds + 1), 1000);
    return () => clearInterval(id);
  }, [state]);
  useEffect(() => {
    if (prevState.current === 'running' && state === 'completed') {
      if (result) {
        const copy = refreshReceiptCopy(receiptFromRunResult(result));
        if (copy.tone === 'warn') toast.warning(copy.text);
        else toast.success(copy.text);
      }
    }
    prevState.current = state;
  }, [state, result]);

  if (state === 'running') {
    const src = restockProgress(messages);
    const pct = src
      ? Math.round((src.done / src.total) * 100)
      : progress && progress.percent > 0
        ? Math.min(100, Math.round(progress.percent))
        : null;
    const text = src
      ? `Checking ${src.total} job sites · ${src.done} reported`
      : progress?.stage_label
        ? progress.stage_label
        : 'Checking the sources';
    const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
    return (
      <div className="qb-runblock" role="status">
        <p className="qb-workline">
          <span className="qb-workline-track" aria-hidden="true">
            <span
              className={pct === null ? 'qb-workline-fill qb-indet' : 'qb-workline-fill'}
              style={pct === null ? undefined : { width: `${pct}%` }}
            />
          </span>
          {text} · <span className="qb-num">{clock}</span>. Keep browsing while it runs.
        </p>
        <SourceScoreboard messages={messages} />
      </div>
    );
  }

  if (state === 'failed') {
    const copy = refreshReceiptCopy({
      status: 'failed',
      jobs_found: 0,
      new_jobs: 0,
      error,
      source_coverage: null,
    });
    return (
      <p className="qb-workline qb-receipt" data-tone="bad" role="status">
        {copy.text} Click <b>“Get new jobs”</b> to try again.
      </p>
    );
  }

  if (state === 'completed' && result) {
    const copy = refreshReceiptCopy(receiptFromRunResult(result));
    return (
      <p className="qb-workline qb-receipt" data-tone={copy.tone} role="status">
        {copy.text}
      </p>
    );
  }

  if (state === 'idle' && persistedReceipt) {
    const copy = refreshReceiptCopy(persistedReceipt);
    return (
      <p className="qb-workline qb-receipt" data-tone={copy.tone} role="status">
        {copy.text}
      </p>
    );
  }

  return null;
}

/* The assistant run's own report, in the same slot as the pull's line. The
   phase comes from the MCP tool calls the run has actually made, polled from
   the app. It used to be a stopwatch dressed as progress: past 100 seconds it
   read "Ranking against your experience" whether or not ranking had started,
   and on one run it claimed that at 2:36 with set_work_fit never called.
   Only one of the two lines mounts at a time. */
function AssistantRunLine() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const { data } = useAgentProgress(true);
  const steps = data?.steps ?? [];
  const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
  return (
    <div className="qb-runblock" role="status">
      <p className="qb-workline">
        <Loader2 className="h-4 w-4 animate-spin text-brand" aria-hidden="true" />
        {data?.phase ?? 'Starting up'} · <span className="qb-num">{clock}</span>. Keep browsing
        while it runs.
      </p>
      <AssistantSteps steps={steps} />
    </div>
  );
}

export function WorkToolbar({
  checkedAgo,
  refreshReceipt,
  shownCount,
  laneTotal,
  reviewedCount,
  unreviewedCount,
  filtering = false,
  search,
  onSearch,
  place,
  onPlace,
  nearOnly,
  onNearOnly,
  payFrom,
  onPayFrom,
  payTo,
  onPayTo,
  postedDays,
  onPostedDays,
  foundingOnly,
  onFoundingOnly,
}: WorkToolbarProps) {
  const { runId: searchRunId } = useSearchContext();
  const { run, ready, running } = useRunWorkSearch();
  const { ready: assistantReady, isDesktop, loading: assistantLoading } = useAssistantReady();
  const assistant = useRunAssistant();
  const kind = primaryRunKind(assistantReady);
  const [lastRun, setLastRun] = useState<'assistant' | 'pull' | null>(null);

  // One button, two runs. The assistant path (pull + rank) wins when ready;
  // the plain pull is the fallback. Disable while either is in flight, and
  // while assistant readiness is still loading so a click can't fire the plain
  // pull a beat before we learn the assistant is connected.
  const pending = assistant.isPending || running;
  const startPrimary = () => {
    if (pending) return;
    if (kind === 'assistant') {
      setLastRun('assistant');
      assistant.start();
      return;
    }
    setLastRun('pull');
    run();
  };
  const primaryLabel = assistant.isPending
    ? 'Finding & ranking…'
    : running
      ? 'Getting jobs…'
      : 'Get new jobs';

  /* First-run hand-off: onboarding marks a flag and routes here, so the new
     user's first pull fires on its own. The flag is read (and cleared) once,
     into a ref, so it can never fire twice; the pull then fires the moment
     the saved search has loaded. */
  const firstRunChecked = useRef(false);
  const firstRunPending = useRef(false);
  const firstRunFired = useRef(false);
  useEffect(() => {
    if (!firstRunChecked.current) {
      firstRunChecked.current = true;
      firstRunPending.current = consumeFirstRunPending();
    }
    if (firstRunFired.current || !firstRunPending.current || !ready) return;
    firstRunFired.current = true;
    run();
  }, [ready, run]);

  const { data: onboarding } = useOnboardingState();
  const prefs = onboarding?.preferences;
  const payCurrency = prefs?.compensation.currency?.trim().toUpperCase() || undefined;
  const savedRoles = onboarding ? (prefs?.roles ?? []) : undefined;
  const noteText = pullReceipt(onboarding ? prefs : undefined, assistantReady);
  const noteLink = savedRoles && savedRoles.length === 0 ? 'Set roles' : 'Edit search';
  const coverageText = reviewCoverageText(reviewedCount, unreviewedCount);

  const payFloor = parseAmount(payFrom.trim());
  const payCeiling = parseAmount(payTo.trim());
  const chips: FilterChip[] = [];
  if (search.trim()) {
    chips.push({ key: 'q', label: `"${search.trim()}"`, clear: () => onSearch('') });
  }
  if (place.trim()) {
    chips.push({ key: 'place', label: place.trim(), clear: () => onPlace('') });
  }
  if (payFloor !== null) {
    chips.push({
      key: 'from',
      label: `${formatStatedPay(payFloor, null, payCurrency)} incl. unstated/unlike currency`,
      clear: () => onPayFrom(''),
    });
  }
  if (payCeiling !== null) {
    chips.push({
      key: 'to',
      label: formatStatedPay(null, payCeiling, payCurrency),
      clear: () => onPayTo(''),
    });
  }
  if (postedDays) {
    chips.push({
      key: 'days',
      label: postedChipLabel(postedDays),
      clear: () => onPostedDays(undefined),
    });
  }
  if (foundingOnly) {
    chips.push({
      key: 'founding',
      label: 'founding / first hire',
      clear: onFoundingOnly,
    });
  }

  return (
    <div className="qb-worktool">
      <div className="qb-workactions">
        <SageButton
          onClick={startPrimary}
          disabled={pending || assistantLoading || (kind === 'pull' && !ready)}
        >
          {primaryLabel}
        </SageButton>
        <span className="qb-workactions-note" title={savedRoles?.join(', ') || undefined}>
          {noteText}{' '}
          <Link to="/settings" search={{ tab: 'restock' }} className="qb-textlink">
            {noteLink}
          </Link>
          {isDesktop && !assistantReady && (
            <>
              {' · '}
              <Link to="/settings" search={{ tab: 'assistant' }} className="qb-textlink">
                Connect your assistant to rank
              </Link>
            </>
          )}
        </span>
      </div>
      {/* The assistant run has no SSE line of its own. Its inline progress
          clears after completion and the refreshed ranking is the result.
          Only a plain pull owns RunStatusLine, so its stale "N new" cannot
          reappear under a rank. */}
      {lastRun === 'assistant' && assistant.isPending ? (
        <AssistantRunLine />
      ) : (
        <RunStatusLine
          key={searchRunId ?? refreshReceipt?.run_id ?? 'no-refresh'}
          persistedReceipt={refreshReceipt}
        />
      )}
      <p className="qb-tray-caption" aria-live="polite">
        {filterTrayCaption(filtering)}
        {coverageText ? ` · ${coverageText}` : ''}
      </p>
      <div className="qb-tray" role="search">
        <label className="qb-tray-field qb-tray-grow">
          <HugeiconsIcon icon={Search01Icon} size={16} strokeWidth={1.7} />
          <input
            placeholder={filterPlaceholder(shownCount)}
            aria-label="Filter these jobs"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
          />
        </label>
        <PlacePicker
          value={place}
          onChange={onPlace}
          ariaLabel="Filter by place; remote jobs pass unless near me only is on"
          className="qb-tray-field qb-tray-place"
        />
        <label className="qb-tray-field qb-tray-minpay">
          <HugeiconsIcon icon={CoinsDollarIcon} size={16} strokeWidth={1.7} />
          <span className="qb-tray-label">
            min listed pay{payCurrency ? ` (${payCurrency})` : ''}
          </span>
          <input
            inputMode="numeric"
            /* "any", never a number. A sample amount here reads as a filter
               that is switched on, and sat next to the receipt's real saved
               floor as a second, contradicting figure. */
            placeholder="any"
            aria-label={`Minimum listed pay a year${payCurrency ? ` in ${payCurrency}` : ''}`}
            value={payFrom}
            onChange={(e) => onPayFrom(e.target.value)}
          />
        </label>
        <label className="qb-tray-field qb-tray-posted">
          <span className="qb-tray-label">date</span>
          <select
            aria-label="Filter by date"
            value={postedDays ?? ''}
            onChange={(e) => onPostedDays(normalizePostedDays(e.target.value))}
          >
            {POSTED_OPTIONS.map((opt) => (
              <option key={opt.value || 'any'} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {(chips.length > 0 || place.trim()) && (
        <div className="qb-workchips">
          {chips.map((chip) => (
            <button
              type="button"
              key={chip.key}
              className="qb-pchip"
              onClick={chip.clear}
              aria-label={`Remove filter: ${chip.label}`}
            >
              {chip.label}
              <span className="qb-workchip-x" aria-hidden="true">
                ×
              </span>
            </button>
          ))}
          {place.trim() && (
            <label className="qb-nearme">
              <input
                type="checkbox"
                checked={nearOnly}
                onChange={(e) => onNearOnly(e.target.checked)}
              />
              near me only
            </label>
          )}
        </div>
      )}
      <p className="qb-workline">
        {filterStatusText({
          shown: shownCount,
          laneTotal,
          filtered: chips.length > 0,
          checkedAgo,
          hiddenNote: hiddenDatesClause({
            days: postedDays,
            shown: shownCount,
            baseline: laneTotal,
          }),
          scopeNote: payScopeNote({
            savedFloor: prefs?.compensation?.min_base,
            typedFloor: payFloor,
          }),
        })}
      </p>
    </div>
  );
}
