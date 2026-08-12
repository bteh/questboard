import { describe, expect, it } from 'vitest';
import { kindSearchForLane } from './lane-filter-state';

const presets = [
  { key: 'remote', questOnly: true },
  { key: 'noexp', questOnly: true },
  { key: 'founding', careerOnly: true },
];
const keys = presets.map((preset) => preset.key);

describe('kindSearchForLane', () => {
  it('clears hidden quest and pay filters when entering Work', () => {
    expect(kindSearchForLane(
      { v: 'all', p: 'remote,noexp', from: '150k', to: '220k' },
      'work',
      presets,
      keys,
    )).toMatchObject({ v: 'work', p: undefined, from: undefined, to: undefined });
  });

  it('clears hidden career filters when entering Side quests', () => {
    expect(kindSearchForLane(
      { v: 'work', p: 'founding', src: 'crypto', from: '150k' },
      'all',
      presets,
      keys,
    )).toEqual(expect.objectContaining({
      v: undefined,
      p: undefined,
      src: undefined,
      from: undefined,
    }));
  });

  it('keeps quest filters while moving between quest kinds', () => {
    expect(kindSearchForLane(
      { v: 'study', p: 'remote', q: 'research' },
      'scholarship',
      presets,
      keys,
    )).toEqual(expect.objectContaining({ p: 'remote', q: 'research' }));
  });
});
