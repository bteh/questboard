import { describe, expect, it } from 'vitest';
import { filterPlaces } from './places';

describe('the board place suggestions', () => {
  it('returns nothing for an empty query', () => {
    expect(filterPlaces('')).toEqual([]);
    expect(filterPlaces('   ')).toEqual([]);
  });

  it('suggests a state by name and passes the state name as the value', () => {
    const hit = filterPlaces('illin').find((o) => o.value === 'Illinois');
    expect(hit?.sub).toBe('state');
  });

  it('finds a state by its abbreviation', () => {
    const values = filterPlaces('tx').map((o) => o.value);
    expect(values).toContain('Texas');
  });

  it('suggests a city and passes the bare city as the value (clean substring)', () => {
    const hit = filterPlaces('chic').find((o) => o.label === 'Chicago, IL');
    expect(hit?.value).toBe('Chicago');
  });

  it('finds a city by a nickname alias', () => {
    const labels = filterPlaces('nyc').map((o) => o.label);
    expect(labels).toContain('New York, NY');
  });

  it('offers the San Gabriel Valley as an area by its 626 and SGV aliases', () => {
    for (const q of ['626', 'sgv', 'san gabriel valley']) {
      const hit = filterPlaces(q).find((o) => o.value === 'San Gabriel Valley (626)');
      expect(hit?.sub).toBe('area');
    }
  });

  it('offers North Orange County from "north oc" and "fullerton"', () => {
    expect(filterPlaces('north oc').map((o) => o.value)).toContain('North Orange County');
    expect(filterPlaces('fullerton').map((o) => o.value)).toContain('North Orange County');
  });

  it('suggests a single area city with CA so the backend guard applies', () => {
    expect(filterPlaces('arcad').map((o) => o.value)).toContain('Arcadia, CA');
    expect(filterPlaces('fullerton').map((o) => o.value)).toContain('Fullerton, CA');
    expect(filterPlaces('orange').map((o) => o.value)).toContain('Orange, CA');
  });

  it('caps the list', () => {
    expect(filterPlaces('a', 4).length).toBeLessThanOrEqual(4);
  });
});
