import { Compass, Globe, MapPin } from 'lucide-react';

import { LocationListInput } from '@/components/shared/location-list-input';
import { WorkplacePreferenceSelector } from '@/components/shared/workplace-preference-selector';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import {
  getSearchAreaSummary,
  type SearchAreaContext,
} from '@/lib/search-area';
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

const TONE_CLASSES: Record<ReturnType<typeof getSearchAreaSummary>['tone'], string> = {
  brand: 'border-brand/20 bg-brand-light/20 text-brand',
  sky: 'border-sky-200 bg-sky-50/70 text-sky-800 dark:border-sky-900/50 dark:bg-sky-950/30 dark:text-sky-200',
  emerald: 'border-emerald-200 bg-emerald-50/70 text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-200',
  amber: 'border-amber-200 bg-amber-50/70 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200',
};

const TONE_ICON: Record<ReturnType<typeof getSearchAreaSummary>['tone'], typeof Globe> = {
  brand: Compass,
  sky: Globe,
  emerald: Globe,
  amber: MapPin,
};

export function SearchAreaSection({
  preferredPlaces,
  onPreferredPlacesChange,
  workplacePreference,
  onWorkplacePreferenceChange,
  context,
  className,
}: SearchAreaSectionProps) {
  const summary = getSearchAreaSummary(workplacePreference, preferredPlaces, context);
  const SummaryIcon = TONE_ICON[summary.tone];

  return (
    <div className={cn('space-y-4', className)}>
      <div className="space-y-2">
        <Label className="text-sm font-medium">Search area</Label>
        <WorkplacePreferenceSelector
          value={workplacePreference}
          onChange={onWorkplacePreferenceChange}
        />
      </div>

      <div className={cn('rounded-xl border px-4 py-3', TONE_CLASSES[summary.tone])}>
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/50 dark:bg-black/10">
            <SummaryIcon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium">{summary.title}</p>
            <p className="mt-1 text-xs leading-relaxed opacity-90">{summary.description}</p>
            <p className="mt-2 text-[11px] opacity-70">{summary.contextNote}</p>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-sm font-medium">{summary.locationLabel}</Label>
        <LocationListInput
          value={preferredPlaces}
          onChange={onPreferredPlacesChange}
          emptyText={summary.emptyText}
          helperText={summary.locationHelperText}
        />
      </div>

      {summary.missingLocations && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => onWorkplacePreferenceChange('remote_friendly')}>
            Use Remote + selected places
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => onWorkplacePreferenceChange('remote_only')}>
            Use Remote only
          </Button>
        </div>
      )}
    </div>
  );
}
