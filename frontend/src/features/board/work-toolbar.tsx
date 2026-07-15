/* The Jobs lane's one toolbar: search, place, minimum listed pay, the
   active filter chips, and the Run search button. Typing keeps filtering
   the cached list instantly, exactly like the shared tray; only the button
   touches the network, through the same pipeline the Restock page runs.
   The status line under it states only what the data backs. */

import { Link } from '@tanstack/react-router';
import { HugeiconsIcon } from '@hugeicons/react';
import { CoinsDollarIcon, Search01Icon } from '@hugeicons/core-free-icons';
import { SageButton } from '@questboard/ui';
import { useApplications } from '@/hooks/use-applications';
import { useSearchContext } from '@/contexts/search-context';
import { restockProgress } from '@/components/board/restock-logic';
import { kindParams, type KindKey } from '@/features/board/kind-params';
import { PlacePicker } from '@/features/board/place-picker';
import { useRunWorkSearch } from '@/features/board/use-run-work-search';
import { formatStatedPay, parseAmount } from '@/utils/board-card';

interface WorkToolbarProps {
  kindKey: KindKey;
  /** the board summary's honest "sources checked Xh ago", or null */
  checkedAgo: string | null;
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

function StatusLine({ kindKey, checkedAgo }: { kindKey: KindKey; checkedAgo: string | null }) {
  const { state, messages, progress, result, error } = useSearchContext();
  /* the lane's whole cache, apart from whatever filters are typed in */
  const { data } = useApplications({ ...kindParams(kindKey), page: 1, page_size: 1, scope: 'board' });
  const cached = data ? `${data.total} jobs cached` : null;
  const cachedLine = [cached, checkedAgo].filter(Boolean).join(', ');

  if (state === 'running') {
    const src = restockProgress(messages);
    const pct = src
      ? Math.round((src.done / src.total) * 100)
      : progress && progress.percent > 0
        ? Math.min(100, Math.round(progress.percent))
        : null;
    const text = src
      ? `Checking the sources, ${src.done} of ${src.total} in.`
      : progress?.stage_label
        ? `${progress.stage_label}.`
        : 'Checking the sources.';
    return (
      <p className="qb-workline" role="status">
        <span className="qb-workline-track" aria-hidden="true">
          <span
            className={pct === null ? 'qb-workline-fill qb-indet' : 'qb-workline-fill'}
            style={pct === null ? undefined : { width: `${pct}%` }}
          />
        </span>
        {text} Results stay usable while it runs.
      </p>
    );
  }

  if (state === 'failed') {
    return (
      <p className="qb-workline" role="status">
        The run failed{error ? `: ${error}` : ''}.{' '}
        <Link to="/restock" className="qb-textlink" style={{ fontSize: 'inherit' }}>
          see the log
        </Link>
      </p>
    );
  }

  if (state === 'completed' && result) {
    const timeouts = messages.filter((m) => TIMED_OUT_RE.test(m)).length;
    return (
      <p className="qb-workline" role="status">
        Run done, {result.jobs_found} found
        {timeouts > 0 ? `, ${timeouts} source${timeouts === 1 ? '' : 's'} timed out` : ''}.
        {cachedLine ? ` ${cachedLine}.` : ''}
      </p>
    );
  }

  return <p className="qb-workline">{cachedLine || ' '}</p>;
}

export function WorkToolbar({
  kindKey,
  checkedAgo,
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
      <div className="qb-tray" role="search">
        <label className="qb-tray-field qb-tray-grow">
          <HugeiconsIcon icon={Search01Icon} size={16} strokeWidth={1.7} />
          <input
            placeholder="Search the cached jobs"
            aria-label="Search the cached jobs"
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
        <div className="qb-tray-run">
          <SageButton onClick={run} disabled={!ready}>
            {running ? 'Running' : 'Run search'}
          </SageButton>
        </div>
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
      <StatusLine kindKey={kindKey} checkedAgo={checkedAgo} />
    </div>
  );
}
