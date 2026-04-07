import type { PlaceSelection } from '@/types/workspace';

import {
  type WorkplacePreference,
} from '@/lib/profile-preferences';
import {
  meaningfulPlaces,
  resolveEffectiveWorkplacePreference,
} from '@/lib/search-area';

export interface SearchReadinessInput {
  roles: string[];
  keywords: string[];
  locations: PlaceSelection[];
  workplacePreference: WorkplacePreference;
  allowResumeFallback?: boolean;
}

export interface SearchReadinessResult {
  usesRemoteFallback: boolean;
  hasRunnableLocations: boolean;
  missingLocations: boolean;
  missingSearchTerms: boolean;
  canStart: boolean;
  effectiveWorkplacePreference: WorkplacePreference;
}

export function deriveWorkplacePreferenceFromPlaces(locations: PlaceSelection[]): WorkplacePreference {
  // AI suggestions should default to the flexible mode: remote jobs everywhere,
  // plus local jobs once the user confirms their places.
  void locations;
  return 'remote_friendly';
}

export function getSearchReadiness({
  roles,
  keywords,
  locations,
  workplacePreference,
  allowResumeFallback = false,
}: SearchReadinessInput): SearchReadinessResult {
  const selectedPlaces = meaningfulPlaces(locations);
  const missingSearchTerms = roles.length === 0 && keywords.length === 0 && !allowResumeFallback;
  const hasRunnableLocations = workplacePreference !== 'location_only' || selectedPlaces.length > 0;
  const missingLocations = !hasRunnableLocations;
  const usesRemoteFallback = workplacePreference === 'remote_friendly' && selectedPlaces.length === 0;
  const effectiveWorkplacePreference = resolveEffectiveWorkplacePreference(workplacePreference, locations);

  return {
    usesRemoteFallback,
    hasRunnableLocations,
    missingLocations,
    missingSearchTerms,
    canStart: !missingSearchTerms && !missingLocations,
    effectiveWorkplacePreference,
  };
}
