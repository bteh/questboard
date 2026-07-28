import { describe, expect, it } from 'vitest';

import { stepLines, type AssistantStep } from '@/features/board/assistant-steps';

const step = (tool: string, count = 1): AssistantStep => ({ tool, at: '2026-07-27T23:00:00Z', count });

describe('stepLines', () => {
  it('names each checkpoint in plain words', () => {
    const lines = stepLines([step('read_resume_for_matching'), step('refresh_work')]);
    expect(lines.map((l) => l.label)).toEqual(['Read your resume', 'Started the source pull']);
  });

  it('marks everything but the last step done', () => {
    const lines = stepLines([step('read_resume_for_matching'), step('search_work')]);
    expect(lines.map((l) => l.done)).toEqual([true, false]);
  });

  it('shows how long the run has been waiting on the sources', () => {
    // The run polls get_refresh_status every ~10s; six polls is a minute of
    // waiting, and saying so is the difference between slow and stuck.
    const lines = stepLines([step('refresh_work'), step('get_refresh_status', 6)]);
    expect(lines[1]).toMatchObject({ label: 'Waiting on the sources', repeat: 6 });
  });

  it('does not label a single call as a repeat', () => {
    expect(stepLines([step('search_work')])[0].repeat).toBe(0);
  });

  it('hides tools that say nothing about progress', () => {
    const lines = stepLines([step('server_info'), step('search_work'), step('get_opportunity')]);
    expect(lines.map((l) => l.label)).toEqual(['Pulled the shortlist']);
  });

  it('marks the last VISIBLE step as current, not the last raw one', () => {
    const lines = stepLines([step('search_work'), step('get_opportunity')]);
    expect(lines).toHaveLength(1);
    expect(lines[0].done).toBe(false);
  });

  it('falls back to readable words for a tool it has no phrase for', () => {
    expect(stepLines([step('set_opportunity_status')])[0].label).toBe('set opportunity status');
  });

  it('is empty before the run reports anything', () => {
    expect(stepLines([])).toEqual([]);
  });
});
