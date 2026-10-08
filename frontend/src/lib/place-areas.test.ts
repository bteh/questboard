import { describe, expect, it } from 'vitest';
import {
  createManualPlace,
  getLocationSuggestions,
  normalizeLocationInput,
  normalizePlaceList,
} from './profile-preferences';

describe('named areas in Find Work places', () => {
  it('keeps the area label intact through normalization', () => {
    expect(normalizeLocationInput('San Gabriel Valley (626)')).toBe('San Gabriel Valley (626)');
    expect(normalizeLocationInput('626')).toBe('San Gabriel Valley (626)');
    expect(normalizeLocationInput('north oc')).toBe('North Orange County');
  });

  it('saves an area as a US place with no state, so it never widens to all of CA', () => {
    const place = createManualPlace('SGV');
    expect(place.label).toBe('San Gabriel Valley (626)');
    expect(place.region).toBe('');
    expect(place.country_code).toBe('US');
  });

  it('round-trips a multi-place list with an area and a city', () => {
    const saved = normalizePlaceList(['San Gabriel Valley (626)', 'North Orange County', 'Arcadia, CA']);
    expect(saved.map((p) => p.label)).toEqual([
      'San Gabriel Valley (626)',
      'North Orange County',
      'Arcadia, CA',
    ]);
    expect(normalizePlaceList(saved).map((p) => p.label)).toEqual(saved.map((p) => p.label));
  });

  it('suggests the area from its aliases', () => {
    expect(getLocationSuggestions('626').map((s) => s.label)).toContain('San Gabriel Valley (626)');
    expect(getLocationSuggestions('fullerton').map((s) => s.label)).toContain('North Orange County');
  });
});
