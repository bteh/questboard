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
  title: string;
  description: string;
  contextNote: string;
  locationLabel: string;
  locationHelperText: string;
  emptyText: string;
  shortLabel: string;
  tone: 'brand' | 'sky' | 'emerald' | 'amber';
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

export function getSearchAreaSummary(
  workplacePreference: WorkplacePreference,
  places: PlaceSelection[],
  context: SearchAreaContext,
): SearchAreaSummary {
  const selectedPlaces = meaningfulPlaces(places);
  const placesSummary = summarizePlaces(selectedPlaces);
  const usesRemoteFallback = workplacePreference === 'remote_friendly' && selectedPlaces.length === 0;
  const effectiveWorkplacePreference = resolveEffectiveWorkplacePreference(workplacePreference, selectedPlaces);
  const missingLocations = workplacePreference === 'location_only' && selectedPlaces.length === 0;
  const contextNote = context === 'search'
    ? 'This only changes the current run. Your saved defaults stay untouched.'
    : context === 'onboarding'
      ? 'You can change this later in Settings or override it per search.'
      : 'These become your default search area everywhere in Launchboard.';

  if (missingLocations) {
    return {
      effectiveWorkplacePreference,
      usesRemoteFallback,
      missingLocations,
      places: selectedPlaces,
      placesSummary,
      title: 'Add at least one place',
      description: 'Selected places only needs a city, metro, state, or country before Launchboard can search.',
      contextNote,
      locationLabel: 'Places to search',
      locationHelperText: 'Required in this mode. Add a city, metro, state, or country.',
      emptyText: 'No places added yet.',
      shortLabel: 'Selected places only',
      tone: 'amber',
    };
  }

  if (workplacePreference === 'location_only') {
    return {
      effectiveWorkplacePreference,
      usesRemoteFallback,
      missingLocations,
      places: selectedPlaces,
      placesSummary,
      title: 'Only selected places',
      description: `Launchboard will keep hybrid and on-site jobs in ${placesSummary}. Remote jobs are excluded.`,
      contextNote,
      locationLabel: 'Places to search',
      locationHelperText: 'Add more places if you want more local markets included.',
      emptyText: 'No places added yet.',
      shortLabel: 'Selected places only',
      tone: 'brand',
    };
  }

  if (workplacePreference === 'remote_only') {
    return {
      effectiveWorkplacePreference,
      usesRemoteFallback,
      missingLocations,
      places: selectedPlaces,
      placesSummary,
      title: 'Remote only',
      description: selectedPlaces.length > 0
        ? `Only fully remote jobs will be kept. ${placesSummary} stays saved for later, but won't affect this mode.`
        : 'Only fully remote jobs will be kept. You do not need to add a city for this mode.',
      contextNote,
      locationLabel: selectedPlaces.length > 0 ? 'Saved places for later' : 'Saved places (optional)',
      locationHelperText: 'Optional here. Add places only if you may switch back to local results later.',
      emptyText: 'No places saved. Optional in remote-only mode.',
      shortLabel: 'Remote only',
      tone: 'emerald',
    };
  }

  if (usesRemoteFallback) {
    return {
      effectiveWorkplacePreference,
      usesRemoteFallback,
      missingLocations,
      places: selectedPlaces,
      placesSummary,
      title: 'Remote jobs everywhere for now',
      description: 'Because no places are selected, Launchboard will keep remote jobs everywhere. Add places if you also want nearby hybrid or on-site roles.',
      contextNote,
      locationLabel: 'Add places if you want local results too',
      locationHelperText: 'Optional in this mode. Add places only if you want nearby hybrid or on-site jobs too.',
      emptyText: 'No places added yet. Remote jobs will still work.',
      shortLabel: 'Remote everywhere',
      tone: 'sky',
    };
  }

  return {
    effectiveWorkplacePreference,
    usesRemoteFallback,
    missingLocations,
    places: selectedPlaces,
    placesSummary,
    title: 'Remote everywhere + selected places',
    description: `Launchboard will keep remote jobs everywhere plus hybrid and on-site jobs in ${placesSummary}.`,
    contextNote,
    locationLabel: 'Selected places',
    locationHelperText: 'Add places if you want more local markets included. Remote jobs still stay eligible everywhere.',
    emptyText: 'No places added yet.',
    shortLabel: 'Remote + selected places',
    tone: 'sky',
  };
}
