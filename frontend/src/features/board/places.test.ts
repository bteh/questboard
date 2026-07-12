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

  it('caps the list', () => {
    expect(filterPlaces('a', 4).length).toBeLessThanOrEqual(4);
  });
});
