/* The Jobs lane's top block, in reading order. The actions row leads with
   the one filled "Get new jobs" button and says in plain words what it
   pulls (saved target roles, editable in Settings); the assistant's ranking
   door sits on the same row, and the run status line reports on the pull.
   The filter tray sits demoted below: three fields that only narrow rows
   already on the board, with no button, so it cannot read as a search form.
   Only "Get new jobs" touches the network, through the same pipeline the
   Restock page runs. The line under the filters states only what the data
   backs. */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { Link } from '@tanstack/react-router';
import { HugeiconsIcon } from '@hugeicons/react';
import { CoinsDollarIcon, Search01Icon } from '@hugeicons/core-free-icons';
import { SageButton } from '@questboard/ui';
import { useSearchContext } from '@/contexts/search-context';
import { restockProgress } from '@/components/board/restock-logic';
import { PlacePicker } from '@/features/board/place-picker';
import { useRunWorkSearch } from '@/features/board/use-run-work-search';
import { useOnboardingState } from '@/hooks/use-workspace';
import { formatStatedPay, parseAmount } from '@/utils/board-card';

interface WorkToolbarProps {
  /** the board summary's honest "sources checked Xh ago", or null */
  checkedAgo: string | null;
  /** rows the current toolbar filters keep: the filtered query's total */
  shownCount?: number;
  /** every job on the lane before the toolbar filters bite */
  laneTotal?: number;
  /** the assistant's ranking door, rendered inside the actions row */
  assistantSlot?: ReactNode;
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
}

interface FilterChip {
  key: string;
  label: string;
  clear: () => void;
}

const TIMED_OUT_RE = /^\s+.+: timed out$/;

/* The pull note names the actual saved roles the run will use, so the user
   can verify them at the point of use instead of trusting a vague phrase.
   Undefined means still loading; the generic phrase holds until then. */
export function pullNote(roles: string[] | undefined): { text: string; linkLabel: string } {
  if (roles === undefined) {
    return { text: 'Pulls fresh postings for your target roles.', linkLabel: 'Edit roles' };
  }
  if (roles.length === 0) {
    return { text: 'No target roles saved yet.', linkLabel: 'Set roles' };
  }
  if (roles.length === 1) {
    return { text: `Pulls fresh postings for ${roles[0]}.`, linkLabel: 'Edit roles' };
  }
  return {
    text: `Pulls fresh postings for ${roles[0]} and ${roles.length - 1} more roles.`,
    linkLabel: 'Edit roles',
  };
}

/* The placeholder names the box's real job: it narrows rows already on the
   board, and the count keeps that concrete. Under two rows, or while the
   total is loading, the words stand alone. */
export function filterPlaceholder(count: number | undefined): string {
  return count !== undefined && count > 1 ? `Filter these ${count} jobs` : 'Filter these jobs';
}

/* The line under the filters, in plain words: what shows against the whole
   lane while a filter narrows, the bare total otherwise, with the honest
   freshness phrase. Never claims a lane smaller than what shows. */
export function filterStatusText({
  shown,
  laneTotal,
  filtered,
  checkedAgo,
}: {
  shown: number | undefined;
  laneTotal: number | undefined;
  filtered: boolean;
  checkedAgo: string | null;
}): string {
  if (shown === undefined) return checkedAgo ?? '';
  const jobs = (n: number) => `${n} job${n === 1 ? '' : 's'}`;
  const lead = filtered
    ? laneTotal !== undefined && laneTotal >= shown
      ? `Showing ${shown} of ${jobs(laneTotal)}`
      : `Showing ${jobs(shown)}`
    : jobs(shown);
  return checkedAgo ? `${lead} · ${checkedAgo}` : lead;
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
      <p className="qb-workline" role="status">
        <span className="qb-workline-track" aria-hidden="true">
          <span
            className={pct === null ? 'qb-workline-fill qb-indet' : 'qb-workline-fill'}
            style={pct === null ? undefined : { width: `${pct}%` }}
          />
        </span>
        {text} · <span className="qb-num">{clock}</span>. Keep browsing while it runs.
      </p>
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

export function WorkToolbar({
  checkedAgo,
  shownCount,
  laneTotal,
  assistantSlot,
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
}: WorkToolbarProps) {
  const { run, ready, running } = useRunWorkSearch();
  const { data: onboarding } = useOnboardingState();
  const savedRoles = onboarding ? (onboarding.preferences?.roles ?? []) : undefined;
  const note = pullNote(savedRoles);

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

  return (
    <div className="qb-worktool">
      <div className="qb-workactions">
        <SageButton onClick={run} disabled={!ready}>
          {running ? 'Getting jobs…' : 'Get new jobs'}
        </SageButton>
        <span className="qb-workactions-note" title={savedRoles?.join(', ') || undefined}>
          {note.text}{' '}
          <Link to="/settings" search={{ tab: 'restock' }} className="qb-textlink">
            {note.linkLabel}
          </Link>
        </span>
        {assistantSlot}
      </div>
      <RunStatusLine />
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
            placeholder="150k"
            aria-label="Minimum listed pay, a year"
            value={payFrom}
            onChange={(e) => onPayFrom(e.target.value)}
          />
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
        })}
      </p>
    </div>
  );
}
