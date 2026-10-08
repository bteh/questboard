// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ApplicationResponse } from '@/types/application';

vi.mock('@questboard/ui', () => ({ KindStamp: () => null }));
vi.mock('@/hooks/use-scrapers', () => ({
  resolveSourceLabel: (source: string, labels: Record<string, string>) => labels[source] ?? source,
}));

import { QuestList, questRowModel } from './quest-list';

afterEach(cleanup);

function app(overrides: Partial<ApplicationResponse> = {}): ApplicationResponse {
  return {
    id: 7,
    job_title: 'Background actor, one day',
    company: '',
    location: 'Los Angeles, CA',
    job_url: 'https://example.com/q',
    source: 'castingsite',
    description: '',
    is_remote: false,
    work_type: '',
    salary_min: 200,
    salary_max: 200,
    salary_currency: '',
    salary_period: 'daily',
    overall_score: null,
    recommendation: '',
    status: 'found',
    vertical: 'perform',
    first_quest_ok: false,
    date_posted: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    date_confidence: 'exact',
    ...overrides,
  } as ApplicationResponse;
}

describe('the Side Quests list', () => {
  it('shows one row per quest: title, kind, place, stated pay, posted', () => {
    const row = questRowModel(app(), 'Casting Site');
    expect(row).toMatchObject({
      title: 'Background actor, one day',
      kind: 'perform',
      kindLabel: 'Perform & entertain',
      source: 'Casting Site',
      place: 'Los Angeles, CA',
      pay: '$200',
      payUnit: 'a day',
      posted: '2 days ago',
    });
  });

  it('never invents pay or a date', () => {
    const row = questRowModel(
      app({ salary_min: null, salary_max: null, date_posted: null, date_confidence: 'missing' }),
    );
    expect(row.pay).toBeNull();
    expect(row.posted).toBe('');
  });

  it('labels remote quests by their stated scope', () => {
    expect(questRowModel(app({ is_remote: true, location: 'Remote, US' })).place).toBe(
      'remote (US)',
    );
  });

  it('opens the detail sheet when a row is clicked', () => {
    const onOpenDetail = vi.fn();
    const quest = app();
    render(
      <QuestList
        items={[quest, app({ id: 8, job_title: 'Dog walk in Silver Lake', vertical: 'lookafter', salary_min: null, salary_max: null })]}
        labels={{ castingsite: 'Casting Site' }}
        onOpenDetail={onOpenDetail}
      />,
    );
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText('not stated')).toBeTruthy();
    fireEvent.click(screen.getByText('Background actor, one day'));
    expect(onOpenDetail).toHaveBeenCalledWith(quest);
  });
});
