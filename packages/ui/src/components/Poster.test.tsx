/* The poster's corner clip stamp. Unclipped: a Clip button. Clipped with no
   log destination: the same dead stamp as always. Clipped with onOpenLog:
   the stamp names where the row went and opens the log. Applied always wins
   and stays plain. */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Poster } from './Poster';

const base = {
  kind: 'work',
  title: 'Data Engineer',
  giver: 'Acme',
  bring: 'a resume',
};

describe('Poster clip stamp', () => {
  it('shows a Clip button that fires onClip', () => {
    const onClip = vi.fn();
    render(<Poster {...base} onClip={onClip} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clip' }));
    expect(onClip).toHaveBeenCalledOnce();
  });

  it('renders the plain clipped stamp when no log destination is given', () => {
    render(<Poster {...base} clippedDate="Jul 6" />);
    const stamp = screen.getByText('Clipped, Jul 6');
    expect(stamp.tagName).toBe('SPAN');
    expect(screen.queryByText(/in your log/)).toBeNull();
  });

  it('makes the clipped stamp a door to the log when onOpenLog is given', () => {
    const onOpenLog = vi.fn();
    render(<Poster {...base} clippedDate="Jul 6" onOpenLog={onOpenLog} />);
    const stamp = screen.getByRole('button', {
      name: 'Clipped, Jul 6 · in your log',
    });
    fireEvent.click(stamp);
    expect(onOpenLog).toHaveBeenCalledOnce();
  });

  it('keeps the applied stamp plain even with a log destination', () => {
    render(<Poster {...base} applied="Applied, Jun 30" onOpenLog={() => {}} />);
    const stamp = screen.getByText('Applied, Jun 30');
    expect(stamp.tagName).toBe('SPAN');
    expect(screen.queryByText(/in your log/)).toBeNull();
  });
});

describe('Poster application effort', () => {
  it('shows the compact effort and criteria treatment for a Side Quest', () => {
    const { container } = render(
      <Poster
        {...base}
        kind="scholarship"
        bringLabel="criteria"
        effort={{
          level: 'involved',
          label: 'More involved',
          time: 'usually 45+ min or multiple steps',
          typical: true,
        }}
      />,
    );
    expect(screen.getByLabelText(/Application effort: More involved/)).toBeTruthy();
    expect(screen.getByText('criteria')).toBeTruthy();
    expect(screen.getByText(/typical/)).toBeTruthy();
    expect(container.querySelectorAll('.qb-p-effort-marks .is-filled')).toHaveLength(3);
  });

  it('leaves career posters unchanged when effort is absent', () => {
    render(<Poster {...base} />);
    expect(screen.queryByText('effort')).toBeNull();
    expect(screen.getByText('bring')).toBeTruthy();
  });
});
