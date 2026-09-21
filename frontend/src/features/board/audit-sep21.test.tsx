// @vitest-environment jsdom
/* Sep 21 2026 audit (five-persona council + data): the level chip row read
   as more source chips and its counts did not reach the total because the
   249 individual-contributor rows had no chip; "Your assistant ranked 24
   jobs: 24 strong" said nothing when one tier covered everything; and the
   card showed the posting's excerpt instead of the assistant's own reason. */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { LevelChips } from './level-chips';
import { fitDigest, posterModelFor, type FitWall } from './poster-model';
import { SourceCategoryChips } from './source-category-chips';

afterEach(cleanup);

describe('chip rows', () => {
  it('names each row so level chips are not read as sources', () => {
    render(
      <>
        <SourceCategoryChips counts={{ remote: 82 }} selected={null} onSelect={() => {}} foundingOnly={false} onFoundingToggle={() => {}} />
        <LevelChips counts={{ ic: 249, lead: 68, manager: 233 }} selected={null} onSelect={() => {}} />
      </>,
    );
    expect(screen.getByText(/^source$/i)).toBeTruthy();
    expect(screen.getByText(/^level$/i)).toBeTruthy();
  });

  it('puts an Individual contributor chip first so the ladder reads upward and sums to the total', () => {
    render(<LevelChips counts={{ manager: 233, ic: 249, lead: 68 }} selected={null} onSelect={() => {}} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent?.replace(/\s+/g, ' ').trim());
    expect(labels).toEqual(['Individual contributor 249', 'Lead 68', 'Manager 233']);
  });
});

describe('fit digest', () => {
  const wall = (counts: Record<string, number>): FitWall<{ id: number }> => ({
    groups: Object.entries(counts).map(([verdict, n]) => ({
      verdict: verdict as 'strong' | 'good' | 'reach',
      label: verdict,
      items: Array.from({ length: n }, (_, i) => ({ id: i })),
    })),
    skips: [],
  } as unknown as FitWall<{ id: number }>);

  it('keeps the mixed summary when tiers differ', () => {
    expect(fitDigest(wall({ strong: 6, good: 4, reach: 2 }))).toBe('Your assistant ranked 12 jobs: 6 strong, 4 good, 2 reach.');
  });

  it('says plainly when one tier covers everything, and how to get a real ranking', () => {
    expect(fitDigest(wall({ strong: 24 }))).toBe('All 24 came back strong. Ask your assistant to re-rank strictly.');
  });
});

describe('poster card copy', () => {
  const app = {
    id: 1,
    job_title: 'Data Engineering Manager',
    company: 'Capital Group',
    location: 'Los Angeles, CA',
    description: 'I can be myself at work. You are more than a job title. We want you to feel comfortable doing your best work here.',
    agent_fit: { verdict: 'strong', rank: 1, why: 'Leads a 7-person data platform team on Snowflake and dbt, which matches the posting requirements.' },
  } as unknown as Parameters<typeof posterModelFor>[0];

  it('shows the assistant\'s own reason in place of the posting excerpt when there is one', () => {
    const model = posterModelFor(app);
    expect(model.desc).toBe('Leads a 7-person data platform team on Snowflake and dbt, which matches the posting requirements.');
  });

  it('falls back to the posting excerpt without a verdict', () => {
    const model = posterModelFor({ ...app, agent_fit: null } as unknown as Parameters<typeof posterModelFor>[0]);
    expect(model.desc).toContain('I can be myself at work');
  });
});
