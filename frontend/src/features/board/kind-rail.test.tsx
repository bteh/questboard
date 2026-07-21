// @vitest-environment jsdom
/* The rail's supply-honesty rule hides quest kinds with nothing live, but
   the Jobs lane is a workflow door, not a shelf: it must stay reachable at
   zero rows, or a new user can never find Find Work at all. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

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

vi.mock('@/hooks/use-board-summary', () => ({
  useBoardSummary: () => ({
    data: { total: 0, new_today: 0, checked_at: null, kinds },
  }),
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
  count: 0,
  new_today: 0,
};

describe('the kind rail jobs door', () => {
  it('keeps the jobs section on the rail when zero career rows are live', () => {
    kinds = [think, work];
    const onSelect = vi.fn();
    render(<KindRail selected="all" onSelect={onSelect} />);

    expect(screen.getByText('Looking for a job?')).toBeTruthy();
    fireEvent.click(screen.getByText('Find work'));
    expect(onSelect).toHaveBeenCalledWith('work');
  });

  it('keeps the jobs section even when the summary carries no career row', () => {
    kinds = [think];
    render(<KindRail selected="all" onSelect={() => {}} />);

    expect(screen.getByText('Looking for a job?')).toBeTruthy();
    expect(screen.getByText('Find work')).toBeTruthy();
  });

  it('still hides quest kinds with nothing live', () => {
    kinds = [{ ...think, count: 0 }, work];
    render(<KindRail selected="all" onSelect={() => {}} />);

    expect(screen.queryByText('Tell them what you think')).toBeNull();
  });
});
