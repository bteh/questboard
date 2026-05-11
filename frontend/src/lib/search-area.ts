import type { PlaceSelection } from '@/types/workspace';

import {
  isRemoteLocation,
  placeLabel,
  type WorkplacePreference,
} from '@/lib/profile-preferences';

export type SearchAreaContext = 'settings' | 'search' | 'onboarding';

export interface SearchAreaSummary {
  effectiveWorkplacePreference: WorkplacePreference;
  usesRemoteFallback: boolean;
  missingLocations: boolean;
  places: PlaceSelection[];
  placesSummary: string;
  shortLabel: string;
}

export function meaningfulPlaces(places: PlaceSelection[]): PlaceSelection[] {
  return places.filter((place) => {
    const label = placeLabel(place).trim();
    return Boolean(label) && !isRemoteLocation(label);
  });
}

export function summarizePlaces(places: PlaceSelection[], limit = 2): string {
  const labels = meaningfulPlaces(places).map((place) => place.label);
  if (labels.length === 0) return '';
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.slice(0, limit).join(', ')} +${labels.length - limit} more`;
}

export function resolveEffectiveWorkplacePreference(
  workplacePreference: WorkplacePreference,
  places: PlaceSelection[],
): WorkplacePreference {
  if (workplacePreference === 'remote_friendly' && meaningfulPlaces(places).length === 0) {
    return 'remote_only';
  }
  return workplacePreference;
}

const SHORT_LABEL: Record<WorkplacePreference, string> = {
  remote_friendly: 'Remote + places',
  remote_only: 'Remote only',
  location_only: 'Places only',
};

export function getSearchAreaSummary(
  workplacePreference: WorkplacePreference,
  places: PlaceSelection[],
): SearchAreaSummary {
  const selectedPlaces = meaningfulPlaces(places);
  const placesSummary = summarizePlaces(selectedPlaces);
  const usesRemoteFallback = workplacePreference === 'remote_friendly' && selectedPlaces.length === 0;
  const effectiveWorkplacePreference = resolveEffectiveWorkplacePreference(workplacePreference, selectedPlaces);
  const missingLocations = workplacePreference === 'location_only' && selectedPlaces.length === 0;
  return {
    effectiveWorkplacePreference,
    usesRemoteFallback,
    missingLocations,
    places: selectedPlaces,
    placesSummary,
    shortLabel: SHORT_LABEL[effectiveWorkplacePreference],
  };
}
