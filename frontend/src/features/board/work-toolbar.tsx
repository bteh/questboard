/* The Jobs lane's top block, in reading order. The actions row is one filled
   button. When the local assistant is ready it reads the resume, pulls, and
   ranks; otherwise it does the plain pull. Either way the receipt beside it
   says in plain words what the click will do, and one status line under it
   reports on whichever run is live. The filter tray sits demoted below: four
   fields that only narrow rows already on the board, with no button, so it
   cannot read as a search form. Only the top button touches the network,
   through the same pipeline the Restock page runs. The line under the
   filters states only what the data backs. */

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
import { useAgentProgress } from '@/hooks/use-agent-clients';
import { consumeFirstRunPending } from '@/components/onboarding/first-run';
import { useOnboardingState } from '@/hooks/use-workspace';
import { formatStatedPay, parseAmount } from '@/utils/board-card';


interface WorkToolbarProps {
  /** the board summary's honest "sources checked Xh ago", or null */
  checkedAgo: string | null;
  /** rows the current toolbar filters keep: the filtered query's total */
  shownCount?: number;
  /** every job on the lane before the toolbar filters bite */
  laneTotal?: number;
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
  /** which source chip is open, if any. A chip browses past the saved search,
      so the saved pay floor stops applying and the status line says so. */
  sourceCategory?: string | null;
}

interface FilterChip {
  key: string;
  label: string;
  clear: () => void;
}

const TIMED_OUT_RE = /^\s+.+: timed out$/;

const WORKPLACE_WORDS: Record<string, string> = {
  remote_friendly: 'remote friendly',
  remote_only: 'remote only',
  location_only: 'on location',
};

/* Which run the one button fires: the assistant (pull plus ranking) when it's
   ready, the plain pull otherwise. Pinned in work-toolbar.test.ts. */
export function primaryRunKind(assistantReady: boolean): 'assistant' | 'pull' {
  return assistantReady ? 'assistant' : 'pull';
}

/* The full receipt of the saved search the button will run: roles, place,
   remote stance, and pay floor on one line, so nobody has to open
   Settings to learn what the click does. When the assistant is ready the lead
   says it ranks too. Undefined means still loading. */
export function pullReceipt(
  prefs:
    | {
        roles: string[];
        preferred_places: { label: string }[];
        workplace_preference: string;
        compensation: { min_base: number | null };
      }
    | undefined,
  assistantReady = false,
): string {
  if (prefs === undefined) return 'Pulls fresh postings for your target roles.';
  if (!prefs.roles.length) return 'No target roles saved yet.';
  const roles =
    prefs.roles.length === 1
      ? prefs.roles[0]
      : `${prefs.roles[0]} and ${prefs.roles.length - 1} more role${prefs.roles.length > 2 ? 's' : ''}`;
  const lead = assistantReady
    ? `Pulls fresh postings and ranks them for ${roles}`
    : `Pulls fresh postings for ${roles}`;
  const parts = [lead];
  if (prefs.preferred_places.length > 0) parts.push(prefs.preferred_places[0].label);
  const stance = WORKPLACE_WORDS[prefs.workplace_preference];
  if (stance) parts.push(stance);
  const floor = prefs.compensation?.min_base;
  if (floor) parts.push(`$${Math.round(floor / 1000)}K+ base`);
  return `${parts.join(' · ')}.`;
}

/* The placeholder names the box's real job: it narrows rows already on the
   board, and the count keeps that concrete. Under two rows, or while the
   total is loading, the words stand alone. */
export function filterPlaceholder(count: number | undefined): string {
  return count !== undefined && count > 1 ? `Filter these ${count} jobs` : 'Filter these jobs';
}

/* The line under the filters, in plain words: what shows against the whole
   lane while a filter narrows, the bare total otherwise, with the honest
   freshness phrase. Never claims a lane smaller than what shows. The
   hiddenNote is the posted filter's confession (rows without a verifiable
   date are dropped); it rides the end of the line when set. */
export function filterStatusText({
  shown,
  laneTotal,
  filtered,
  checkedAgo,
  hiddenNote,
  scopeNote,
}: {
  shown: number | undefined;
  laneTotal: number | undefined;
  filtered: boolean;
  checkedAgo: string | null;
  hiddenNote?: string | null;
  scopeNote?: string | null;
}): string {
  if (shown === undefined) return checkedAgo ?? '';
  const jobs = (n: number) => `${n} job${n === 1 ? '' : 's'}`;
  const lead = filtered
    ? laneTotal !== undefined && laneTotal >= shown
      ? `Showing ${shown} of ${jobs(laneTotal)}`
      : `Showing ${jobs(shown)}`
    : jobs(shown);
  // The scope note rides next to the counts because it explains them.
  return [lead, checkedAgo, scopeNote, hiddenNote].filter(Boolean).join(' · ');
}

/* The pull's own report, under the actions row it belongs to: a running
   clock while sources answer, the failure with its retry door, and the
   completed tally. Idle renders nothing; the filter line below carries the
   board's counts. Stays mounted so the completion toast can fire even when
   the run ends off-screen. */
function RunStatusLine() {
  const { state, messages, progress, result, error } = useSearchContext();

  // A running clock so the wait shows life, plus a toast on the running->done
  // transition so you know it finished even if you'd tabbed away.
  const [elapsed, setElapsed] = useState(0);
  const prevState = useRef(state);
  useEffect(() => {
    if (state !== 'running') {
      setElapsed(0);
      return;
    }
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [state]);
  useEffect(() => {
    if (prevState.current === 'running' && state === 'completed') {
      const n = result?.new_jobs ?? 0;
      toast.success(n > 0 ? `Board updated · ${n} new job${n === 1 ? '' : 's'}` : 'Board checked · nothing new this time');
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
    return (
      <p className="qb-workline" role="status">
        That didn’t finish{error ? `: ${error}` : ''}. Click <b>“Get new jobs”</b> to try again.
      </p>
    );
  }

  if (state === 'completed' && result) {
    const timeouts = messages.filter((m) => TIMED_OUT_RE.test(m)).length;
    const n = result.new_jobs ?? 0;
    const lead = n > 0 ? `Board updated · ${n} new` : 'Board checked · nothing new';
    return (
      <p className="qb-workline" role="status">
        {lead} ({result.jobs_found} scanned)
        {timeouts > 0 ? ` · ${timeouts} source${timeouts === 1 ? '' : 's'} timed out` : ''}.
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
  shownCount,
  laneTotal,
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
  sourceCategory = null,
}: WorkToolbarProps) {
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
  const savedRoles = onboarding ? (prefs?.roles ?? []) : undefined;
  const noteText = pullReceipt(onboarding ? prefs : undefined, assistantReady);
  const noteLink = savedRoles && savedRoles.length === 0 ? 'Set roles' : 'Edit search';

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
      label: `${formatStatedPay(payFloor, null)} incl. unstated pay`,
      clear: () => onPayFrom(''),
    });
  }
  if (payCeiling !== null) {
    chips.push({
      key: 'to',
      label: formatStatedPay(null, payCeiling),
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
      {/* The assistant run has no SSE line of its own, so after it finishes the
          toast is the report and the inline line clears. Only a plain pull owns
          RunStatusLine, so its stale "N new" can't reappear under a rank. */}
      {lastRun === 'assistant' ? (
        assistant.isPending ? (
          <AssistantRunLine />
        ) : null
      ) : (
        <RunStatusLine />
      )}
      <p className="qb-tray-caption">Narrow what's on the board</p>
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
          <span className="qb-tray-label">min listed pay</span>
          <input
            inputMode="numeric"
            /* "any", never a number. A sample amount here reads as a filter
               that is switched on, and sat next to the receipt's real saved
               floor as a second, contradicting figure. */
            placeholder="any"
            aria-label="Minimum listed pay, a year"
            value={payFrom}
            onChange={(e) => onPayFrom(e.target.value)}
          />
        </label>
        <label className="qb-tray-field qb-tray-posted">
          <span className="qb-tray-label">posted</span>
          <select
            aria-label="Posted within"
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
            browsingCategory: Boolean(sourceCategory),
            savedFloor: prefs?.compensation?.min_base,
            typedFloor: payFloor,
          }),
        })}
      </p>
    </div>
  );
}
