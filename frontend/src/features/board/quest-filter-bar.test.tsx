// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/features/board/place-picker', () => ({
  PlacePicker: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <input aria-label="place" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

import { QuestFilterBar, type QuestFilterBarProps } from './quest-filter-bar';
import { QuestViewBar } from './quest-view-toggle';

afterEach(cleanup);

function renderBar(overrides: Partial<QuestFilterBarProps> = {}) {
  const props: QuestFilterBarProps = {
    search: '',
    onSearch: vi.fn(),
    place: '',
    onPlace: vi.fn(),
    withRemote: false,
    onWithRemote: vi.fn(),
    paidOnly: false,
    onPaidOnly: vi.fn(),
    postedDays: undefined,
    onPostedDays: vi.fn(),
    ...overrides,
  };
  render(<QuestFilterBar {...props} />);
  return props;
}

describe('the Side Quests filter bar', () => {
  it('hides + remote until a place is set', () => {
    renderBar();
    expect(screen.queryByText('+ remote')).toBeNull();
  });

  it('shows + remote with a place and turns it on', () => {
    const props = renderBar({ place: 'Los Angeles' });
    const chip = screen.getByText('+ remote');
    expect(chip.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText(/Only quests in Los Angeles/)).toBeTruthy();
    fireEvent.click(chip);
    expect(props.onWithRemote).toHaveBeenCalledWith(true);
  });

  it('switches the pay filter to stated pay', () => {
    const props = renderBar();
    fireEvent.change(screen.getByLabelText('Filter by pay'), { target: { value: 'stated' } });
    expect(props.onPaidOnly).toHaveBeenCalledWith(true);
  });

  it('passes search text through', () => {
    const props = renderBar();
    fireEvent.change(screen.getByLabelText('Search side quests'), { target: { value: 'acting' } });
    expect(props.onSearch).toHaveBeenCalledWith('acting');
  });
});

describe('the list | wall switch', () => {
  it('marks the current view and reports the other pick', () => {
    const onView = vi.fn();
    render(<QuestViewBar view="list" onView={onView} shown={24} total={1681} />);
    expect(screen.getByText('list').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('24 of 1,681')).toBeTruthy();
    fireEvent.click(screen.getByText('wall'));
    expect(onView).toHaveBeenCalledWith('wall');
  });
});
