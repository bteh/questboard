// @vitest-environment jsdom
/* Real case (Sep 17 2026): the Find work board held 61 lead-level and 211
   manager-level postings, newest first, 24 per page. The person read a few
   pages and concluded there were no lead roles. A level chip row with
   counts makes the split visible and narrows to it, like the source chips. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { LevelChips } from './level-chips';

afterEach(cleanup);

describe('LevelChips', () => {
  it('renders nothing until level counts exist', () => {
    const { container } = render(<LevelChips counts={undefined} selected={null} onSelect={() => {}} />);
    expect(container.querySelector('button')).toBeNull();
  });

  it('shows one chip per level with its count, lead first', () => {
    render(<LevelChips counts={{ manager: 211, lead: 61 }} selected={null} onSelect={() => {}} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons.map((b) => b.textContent?.replace(/\s+/g, ' ').trim())).toEqual(['Lead 61', 'Manager 211']);
  });

  it('selects a level, and clicking it again clears the selection', () => {
    const onSelect = vi.fn();
    render(<LevelChips counts={{ lead: 61, manager: 211 }} selected="lead" onSelect={onSelect} />);
    const lead = screen.getByRole('button', { name: /lead 61/i });
    expect(lead.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(lead);
    expect(onSelect).toHaveBeenCalledWith(null);
    fireEvent.click(screen.getByRole('button', { name: /manager 211/i }));
    expect(onSelect).toHaveBeenCalledWith('manager');
  });

  it('labels director-level, VP and chief plainly', () => {
    render(<LevelChips counts={{ director: 9, vp: 2, chief: 1 }} selected={null} onSelect={() => {}} />);
    expect(screen.getByRole('button', { name: /director 9/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /vp 2/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /chief 1/i })).toBeTruthy();
  });
});
