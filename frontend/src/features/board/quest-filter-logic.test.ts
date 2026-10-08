import { describe, expect, it } from 'vitest';
import { questFilterParams, questPlaceNote } from './quest-filter-logic';

describe('Side Quests place and pay params', () => {
  /* Owner in Los Angeles, Oct 2026: place="Los Angeles" returned 7,214
     quests, mostly remote user tests; near-only gave the 1,681 local ones. */
  it('makes a place near-only by default', () => {
    expect(questFilterParams({ place: 'Los Angeles', withRemote: false, paidOnly: false })).toEqual({
      location: 'Los Angeles',
      location_strict: true,
      pay_stated: undefined,
    });
  });

  it('adds remote quests back with + remote', () => {
    expect(
      questFilterParams({ place: 'Los Angeles', withRemote: true, paidOnly: false }).location_strict,
    ).toBeUndefined();
  });

  it('sends nothing for a blank place', () => {
    expect(questFilterParams({ place: '  ', withRemote: false, paidOnly: false })).toEqual({
      location: undefined,
      location_strict: undefined,
      pay_stated: undefined,
    });
  });

  it('asks for stated pay only when the pay filter is on', () => {
    expect(questFilterParams({ place: '', withRemote: false, paidOnly: true }).pay_stated).toBe(true);
  });

  it('says what the place does in plain words', () => {
    expect(questPlaceNote('Los Angeles', false)).toBe(
      'Only quests in Los Angeles. Add remote to see online ones too.',
    );
    expect(questPlaceNote('Los Angeles', true)).toBe(
      'Los Angeles plus remote and no-place quests.',
    );
    expect(questPlaceNote('', false)).toMatch(/^Pick a place/);
  });

  it('never uses an em dash in its copy', () => {
    for (const note of [
      questPlaceNote('Los Angeles', false),
      questPlaceNote('Los Angeles', true),
      questPlaceNote('', false),
    ]) {
      expect(note).not.toContain(String.fromCharCode(0x2014));
    }
  });
});
