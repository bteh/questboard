import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QuestCard } from './QuestCard';

const base = {
  vertical: 'study' as const,
  title: 'Snack product testing',
  meta: 'FocusGroups.org, posted today, Chicago',
  needs: 'Needs: screener only, ages 21 to 45',
  pay: '$125',
  payUnit: 'max',
};

describe('QuestCard', () => {
  it('renders band, title, meta, needs, and pay', () => {
    render(<QuestCard {...base} />);
    expect(screen.getByText('Paid studies')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Snack product testing' })).toBeInTheDocument();
    expect(screen.getByText('FocusGroups.org, posted today, Chicago')).toBeInTheDocument();
    expect(screen.getByText('Needs: screener only, ages 21 to 45')).toBeInTheDocument();
    expect(screen.getByText('$125')).toBeInTheDocument();
    expect(screen.getByText('max')).toBeInTheDocument();
  });

  it('shows a Clip button that fires onClip', () => {
    const onClip = vi.fn();
    render(<QuestCard {...base} onClip={onClip} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clip this quest' }));
    expect(onClip).toHaveBeenCalledOnce();
  });

  it('shows the applied stamp instead of a Clip button', () => {
    render(<QuestCard {...base} applied="Applied, Jun 30" />);
    expect(screen.getByText('Applied, Jun 30')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Clip this quest' })).toBeNull();
  });

  it('shows the clipped stamp when a clip date is set', () => {
    render(<QuestCard {...base} clippedDate="Jul 6" />);
    expect(screen.getByText('Clipped, Jul 6')).toBeInTheDocument();
  });

  it('presses the stamp in when clipped after mount', () => {
    const { rerender, container } = render(<QuestCard {...base} />);
    rerender(<QuestCard {...base} clippedDate="Jul 7" />);
    const stamp = container.querySelector('.qb-applied-stamp')!;
    expect(stamp.classList.contains('qb-pressin')).toBe(true);
  });

  it('renders the party roster and a make-a-party button', () => {
    const onMakeParty = vi.fn();
    render(
      <QuestCard
        {...base}
        vertical="party"
        party={{ total: 4, seated: ['S', 'D'] }}
        onMakeParty={onMakeParty}
      />,
    );
    expect(screen.getByText('party of 4, 2 in')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'make a party' }));
    expect(onMakeParty).toHaveBeenCalledOnce();
  });

  it('shows the explain button when asked', () => {
    const onExplain = vi.fn();
    render(<QuestCard {...base} showExplain onExplain={onExplain} />);
    fireEvent.click(screen.getByRole('button', { name: 'Explain this' }));
    expect(onExplain).toHaveBeenCalledOnce();
  });
});
