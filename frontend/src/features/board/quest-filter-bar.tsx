/* The Side Quests filter bar, in Find Work's order: what, where, pay, date.
   Every field narrows quests already on the board. */

import { HugeiconsIcon } from '@hugeicons/react';
import { Search01Icon } from '@hugeicons/core-free-icons';
import { PlacePicker } from '@/features/board/place-picker';
import {
  POSTED_OPTIONS,
  normalizePostedDays,
  type PostedDaysKey,
} from '@/features/board/posted-filter';
import { questPlaceNote } from '@/features/board/quest-filter-logic';

export interface QuestFilterBarProps {
  search: string;
  onSearch: (value: string) => void;
  place: string;
  onPlace: (value: string) => void;
  withRemote: boolean;
  onWithRemote: (value: boolean) => void;
  paidOnly: boolean;
  onPaidOnly: (value: boolean) => void;
  postedDays: PostedDaysKey | undefined;
  onPostedDays: (value: PostedDaysKey | undefined) => void;
  /** the posted window's note when it hid undated quests, or null */
  hiddenNote?: string | null;
}

export function QuestFilterBar({
  search,
  onSearch,
  place,
  onPlace,
  withRemote,
  onWithRemote,
  paidOnly,
  onPaidOnly,
  postedDays,
  onPostedDays,
  hiddenNote,
}: QuestFilterBarProps) {
  const placeSet = Boolean(place.trim());
  return (
    <div className="qb-questbar">
      <div className="qb-tray" role="search">
        <label className="qb-tray-field qb-tray-grow">
          <HugeiconsIcon icon={Search01Icon} size={16} strokeWidth={1.7} />
          <input
            placeholder="acting, dog sitting, focus group"
            aria-label="Search side quests"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
          />
        </label>
        <PlacePicker
          value={place}
          onChange={onPlace}
          ariaLabel="Filter by place"
          className="qb-tray-field qb-tray-place"
        />
        <label className="qb-tray-field qb-tray-posted">
          <span className="qb-tray-label">pay</span>
          <select
            aria-label="Filter by pay"
            value={paidOnly ? 'stated' : ''}
            onChange={(e) => onPaidOnly(e.target.value === 'stated')}
          >
            <option value="">any</option>
            <option value="stated">pay stated</option>
          </select>
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
      <div className="qb-questbar-line">
        {placeSet && (
          <button
            type="button"
            className={withRemote ? 'qb-pchip qb-active' : 'qb-pchip'}
            aria-pressed={withRemote}
            onClick={() => onWithRemote(!withRemote)}
          >
            + remote
          </button>
        )}
        <p className="qb-tray-note">
          {questPlaceNote(place, withRemote)}
          {hiddenNote && ` ${hiddenNote.charAt(0).toUpperCase()}${hiddenNote.slice(1)}.`}
        </p>
      </div>
    </div>
  );
}
