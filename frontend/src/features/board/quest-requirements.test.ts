import { describe, expect, it } from 'vitest';
import type { ApplicationResponse } from '@/types/application';
import { effortMarks, requirementsForQuest } from './quest-requirements';

function app(vertical: string, quest?: Record<string, unknown>): ApplicationResponse {
  return { vertical, quest } as ApplicationResponse;
}

describe('Side Quest requirements', () => {
  it('never adds application effort to Find Work', () => {
    expect(requirementsForQuest(app('career'), 'work', 'a resume')).toBeNull();
  });

  it('covers every Side Quest kind with a clearly typical estimate', () => {
    const kinds = [
      'think', 'lookafter', 'house', 'scholarship', 'skill', 'perform', 'audience',
      'body', 'odd', 'deliver', 'flip', 'speak', 'pitch', 'party',
    ];
    for (const kind of kinds) {
      const result = requirementsForQuest(app(kind), kind, 'what the posting states');
      expect(result?.effort.basis, kind).toBe('typical');
      expect(result?.effort.note, kind).toBeTruthy();
      expect(result?.criteria).toEqual({
        items: ['what the posting states'],
        basis: 'typical',
      });
    }
  });

  it('uses listed effort and structured criteria when the row provides them', () => {
    const result = requirementsForQuest(
      app('scholarship', {
        application_effort: 'quick',
        application_effort_note: ' Phase one needs only a short form. ',
        criteria: [' Current senior ', '', 42, '3.0 GPA'],
      }),
      'scholarship',
      'typical scholarship documents',
    )!;
    expect(result.effort).toMatchObject({
      level: 'quick',
      note: 'Phase one needs only a short form.',
      basis: 'listed',
    });
    expect(result.criteria).toEqual({ items: ['Current senior', '3.0 GPA'], basis: 'listed' });
  });

  it('uses a row-specific bring line as listed criteria on older rows', () => {
    const result = requirementsForQuest(
      app('study', { bring: 'honest screener answers' }),
      'think',
      'the usual profile',
    )!;
    expect(result.criteria).toEqual({ items: ['honest screener answers'], basis: 'listed' });
    expect(result.effort.basis).toBe('typical');
  });

  it('ignores invalid effort values instead of presenting them as fact', () => {
    const result = requirementsForQuest(
      app('scholarship', { application_effort: 'easy' }),
      'scholarship',
      'documents',
    )!;
    expect(result.effort.level).toBe('involved');
    expect(result.effort.basis).toBe('typical');
  });

  it('maps effort levels to one, two, or three marks', () => {
    expect(effortMarks('quick')).toBe(1);
    expect(effortMarks('some_prep')).toBe(2);
    expect(effortMarks('involved')).toBe(3);
  });
});
