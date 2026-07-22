// @vitest-environment jsdom
/* The rail's supply-honesty rule hides quest kinds with nothing live. The
   career kind never shows on the rail at all: Find work is the board's
   other workflow, reached by the lane switcher above the rail, so a jobs
   door here would be a second, redundant entrance. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

afterEach(cleanup);

vi.mock('@questboard/ui', () => ({ KindStamp: () => null }));

let kinds: {
  id: string;
  label: string;
  sub: string;
  hue: string;
  order: number;
  count: number;
  new_today: number;
}[] = [];

const summaryCalls: unknown[] = [];

vi.mock('@/hooks/use-board-summary', () => ({
  useBoardSummary: (filters?: unknown) => {
    summaryCalls.push(filters);
    return { data: { total: 0, new_today: 0, checked_at: null, kinds } };
  },
}));

import { KindRail } from './kind-rail';

const think = {
  id: 'think',
  label: 'Tell them what you think',
  sub: 'focus groups, user tests, mock juries',
  hue: '#8A6A1F',
  order: 1,
  count: 12,
  new_today: 0,
};
const work = {
  id: 'work',
  label: 'Find work',
  sub: 'jobs, full-time, contract',
  hue: '#3D4756',
  order: 14,
  count: 7,
  new_today: 0,
};

describe('the kind rail', () => {
  it('shows stocked quest kinds and selects one on click', () => {
    kinds = [think];
    const onSelect = vi.fn();
    render(<KindRail selected="all" onSelect={onSelect} />);

    fireEvent.click(screen.getByText('Tell them what you think'));
    expect(onSelect).toHaveBeenCalledWith('think');
  });

  it('hides quest kinds with nothing live', () => {
    kinds = [{ ...think, count: 0 }];
    render(<KindRail selected="all" onSelect={() => {}} />);

    expect(screen.queryByText('Tell them what you think')).toBeNull();
  });

  it('keeps career rows off the rail even when they are live', () => {
    kinds = [think, work];
    render(<KindRail selected="all" onSelect={() => {}} />);

    expect(screen.queryByText('Looking for a job?')).toBeNull();
    expect(screen.queryByText('Find work')).toBeNull();
  });

  it('counts All quests as side quests only', () => {
    kinds = [think, work];
    render(<KindRail selected="all" onSelect={() => {}} />);

    // 12 from think; work's 7 career rows stay out of the quest count
    const top = document.querySelector('.qb-rail-top') as HTMLElement;
    expect(within(top).getByText('12')).toBeTruthy();
    expect(screen.queryByText('19')).toBeNull();
  });

  it('threads the board filters into the summary so counts match the list', () => {
    kinds = [think];
    const filters = { search: 'seat', location: 'Chicago', salary_max: 90000 };
    render(<KindRail selected="all" onSelect={() => {}} filters={filters} />);

    expect(summaryCalls.at(-1)).toEqual(filters);
  });
});
