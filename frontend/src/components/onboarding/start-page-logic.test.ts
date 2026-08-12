import { describe, expect, it } from 'vitest';

import { buildDefaultWorkspacePreferences } from '@/lib/profile-preferences';
import { firstRunPreferences } from './start-page-logic';

describe('firstRunPreferences', () => {
  it('saves a known international city as structured discovery intent', () => {
    const next = firstRunPreferences(
      buildDefaultWorkspacePreferences(),
      'London, United Kingdom',
      true,
    );

    expect(next.workplace_preference).toBe('remote_friendly');
    expect(next.preferred_places).toEqual([
      expect.objectContaining({
        label: 'London, United Kingdom',
        kind: 'city',
        country: 'United Kingdom',
      }),
    ]);
  });

  it('makes a chosen place location-only when remote is off', () => {
    const next = firstRunPreferences(
      buildDefaultWorkspacePreferences(),
      'Chicago, IL',
      false,
    );

    expect(next.workplace_preference).toBe('location_only');
    expect(next.preferred_places[0]).toEqual(
      expect.objectContaining({ label: 'Chicago, IL', country: 'United States' }),
    );
  });

  it('turns a skipped place into an explicit remote-only preference', () => {
    const current = buildDefaultWorkspacePreferences();
    current.preferred_places = [
      {
        label: 'Los Angeles, CA',
        kind: 'city',
        match_scope: 'city',
        city: 'Los Angeles',
        region: 'California',
        country: 'United States',
        country_code: '',
        lat: null,
        lon: null,
        provider: 'local',
        provider_id: 'Los Angeles, CA',
      },
    ];

    const next = firstRunPreferences(current, '', true);

    expect(next.preferred_places).toEqual([]);
    expect(next.workplace_preference).toBe('remote_only');
  });
});
