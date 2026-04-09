import { useState } from 'react';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { useLocationSuggestions } from '@/hooks/use-workspace';
import {
  createManualPlace,
  normalizeLocationInput,
  normalizePlaceList,
  placeLabel,
  suggestionToPlace,
  type WorkplacePreference,
} from '@/lib/profile-preferences';
import type { PlaceSelection } from '@/types/workspace';
import { cn } from '@/lib/utils';

interface SimpleLocationInputProps {
  preferredPlaces: PlaceSelection[];
  onPreferredPlacesChange: (places: PlaceSelection[]) => void;
  workplacePreference: WorkplacePreference;
  onWorkplacePreferenceChange: (value: WorkplacePreference) => void;
  className?: string;
}

/**
 * Onboarding-only location control. Strips down the full SearchAreaSection
 * (3 workplace tiles + summary card + chip dropdowns) into the smallest
 * useful control: a city input + an "Include remote jobs" checkbox.
 *
 * The full SearchAreaSection is still used in Settings where power users
 * want explicit control over remote-only vs location-only modes.
 *
 * Mapping to the underlying preference enum:
 * - includeRemote=true,  hasPlaces=true   → remote_friendly
 * - includeRemote=true,  hasPlaces=false  → remote_only
 * - includeRemote=false, hasPlaces=true   → location_only
 * - includeRemote=false, hasPlaces=false  → forced to remote_only with a hint
 */
export function SimpleLocationInput({
  preferredPlaces,
  onPreferredPlacesChange,
  workplacePreference,
  onWorkplacePreferenceChange,
  className,
}: SimpleLocationInputProps) {
  const [draft, setDraft] = useState('');
  const normalizedDraft = normalizeLocationInput(draft);
  const includeRemote = workplacePreference !== 'location_only';

  const { data: remoteSuggestions } = useLocationSuggestions(draft, draft.trim().length >= 2);
  const suggestions = remoteSuggestions ?? [];

  const setIncludeRemote = (next: boolean) => {
    if (next) {
      // Turning remote ON: if user has places, prefer remote_friendly; else
      // remote_only.
      onWorkplacePreferenceChange(preferredPlaces.length > 0 ? 'remote_friendly' : 'remote_only');
    } else {
      // Turning remote OFF: must have places, otherwise we have nothing to
      // search. Snap to location_only and let the helper text nudge them.
      onWorkplacePreferenceChange('location_only');
    }
  };

  const addPlace = (place: PlaceSelection) => {
    const next = normalizePlaceList([...preferredPlaces, place]);
    onPreferredPlacesChange(next);
    setDraft('');
    // If the user adds a place while in remote_only mode, gently shift them
    // to remote_friendly so the place actually does something.
    if (workplacePreference === 'remote_only') {
      onWorkplacePreferenceChange('remote_friendly');
    }
  };

  const addManual = () => {
    if (!normalizedDraft) return;
    addPlace(createManualPlace(normalizedDraft));
  };

  const removePlace = (label: string) => {
    const next = preferredPlaces.filter((item) => item.label !== label);
    onPreferredPlacesChange(next);
    if (next.length === 0 && workplacePreference === 'location_only') {
      // Don't strand the user with zero places and no remote — flip back.
      onWorkplacePreferenceChange('remote_only');
    }
  };

  const noPlacesAndRemoteOff = preferredPlaces.length === 0 && !includeRemote;

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-text-primary">Locations</label>
        <span className="text-xs text-text-muted">Optional if remote is on</span>
      </div>

      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              addManual();
            }
          }}
          placeholder="Add a city, state, or region"
          className="h-9"
        />
        <Button
          type="button"
          variant="outline"
          className="h-9 shrink-0"
          onClick={addManual}
          disabled={!draft.trim()}
        >
          Add
        </Button>
      </div>

      {draft.trim() && suggestions.length > 0 && (
        <div className="rounded-lg border border-border-default bg-bg-card p-1.5">
          {suggestions.slice(0, 4).map((suggestion) => (
            <button
              key={suggestion.label}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => addPlace(suggestionToPlace(suggestion))}
              className="flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-bg-subtle"
            >
              <span className="truncate text-text-secondary">{suggestion.label}</span>
              {suggestion.subtitle && (
                <span className="truncate text-[11px] text-text-muted">{suggestion.subtitle}</span>
              )}
            </button>
          ))}
        </div>
      )}

      {preferredPlaces.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {preferredPlaces.map((item) => (
            <span
              key={item.label}
              className="inline-flex items-center gap-1 rounded-full border border-border-default bg-bg-card px-2.5 py-1 text-xs text-text-secondary"
            >
              {placeLabel(item)}
              <button
                type="button"
                onClick={() => removePlace(item.label)}
                className="text-text-muted transition-colors hover:text-text-primary"
                aria-label={`Remove ${item.label}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-border-default bg-bg-subtle/40 px-3 py-2.5">
        <Checkbox
          checked={includeRemote}
          onCheckedChange={(checked) => setIncludeRemote(checked === true)}
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-text-primary">Include remote jobs</p>
          <p className="text-[11px] text-text-muted">
            {includeRemote
              ? preferredPlaces.length > 0
                ? 'Remote anywhere, plus on-site and hybrid in the places above.'
                : 'Searching fully remote roles only.'
              : 'On-site and hybrid in the places above only.'}
          </p>
        </div>
      </label>

      {noPlacesAndRemoteOff && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          Add a city or turn remote back on — there's nothing to search yet.
        </p>
      )}
    </div>
  );
}
