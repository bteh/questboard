import { LocationListInput } from '@/components/shared/location-list-input';
import { WorkplacePreferenceSelector } from '@/components/shared/workplace-preference-selector';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import {
  getSearchAreaSummary,
  type SearchAreaContext,
} from '@/lib/search-area';
// Context kept on props for call-site clarity; impl does not branch on it.
import type { PlaceSelection } from '@/types/workspace';
import type { WorkplacePreference } from '@/lib/profile-preferences';

interface SearchAreaSectionProps {
  preferredPlaces: PlaceSelection[];
  onPreferredPlacesChange: (places: PlaceSelection[]) => void;
  workplacePreference: WorkplacePreference;
  onWorkplacePreferenceChange: (value: WorkplacePreference) => void;
  context: SearchAreaContext;
  className?: string;
}

export function SearchAreaSection({
  preferredPlaces,
  onPreferredPlacesChange,
  workplacePreference,
  onWorkplacePreferenceChange,
  context,
  className,
}: SearchAreaSectionProps) {
  void context;
  const summary = getSearchAreaSummary(workplacePreference, preferredPlaces);
  const showPlaces = workplacePreference !== 'remote_only';

  return (
    <div className={cn('space-y-3', className)}>
      <div className="space-y-1.5">
        <Label className="text-sm font-medium">Search area</Label>
        <WorkplacePreferenceSelector
          value={workplacePreference}
          onChange={onWorkplacePreferenceChange}
        />
      </div>

      {showPlaces && (
        <LocationListInput
          value={preferredPlaces}
          onChange={onPreferredPlacesChange}
          emptyText=""
          helperText=""
        />
      )}

      {summary.missingLocations && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="text-amber-700 dark:text-amber-300">Add a place to continue, or:</span>
          <button type="button" className="text-brand underline-offset-2 hover:underline" onClick={() => onWorkplacePreferenceChange('remote_only')}>
            switch to Remote only
          </button>
        </div>
      )}
    </div>
  );
}
