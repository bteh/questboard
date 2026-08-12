import {
  createManualPlace,
  normalizePlaceList,
} from '@/lib/profile-preferences';
import type { WorkspacePreferences } from '@/types/workspace';

/** Persist the one-question first run into the same preferences Work reads.
 *
 * The board URL remains a useful initial view, but it is not the discovery
 * contract. Saving a structured place here prevents "Get new jobs" from
 * silently falling back to a remote/US search after the user chose a city.
 */
export function firstRunPreferences(
  current: WorkspacePreferences,
  place: string,
  includeRemote: boolean,
): WorkspacePreferences {
  const chosen = place.trim();
  const preferredPlaces = chosen
    ? normalizePlaceList([createManualPlace(chosen)])
    : [];

  return {
    ...current,
    preferred_places: preferredPlaces,
    workplace_preference: preferredPlaces.length === 0
      ? 'remote_only'
      : includeRemote
        ? 'remote_friendly'
        : 'location_only',
  };
}
