import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Chip } from './Chip';

describe('Chip', () => {
  it('renders the label with a live count', () => {
    const { container } = render(<Chip label="no experience needed" count={9} />);
    expect(screen.getByRole('button')).toHaveTextContent('no experience needed');
    expect(container.querySelector('.qb-n')!.textContent).toBe('9');
  });

  it('carries active and dim states', () => {
    const { container } = render(<Chip label="under 2 hours" count={2} active dim />);
    const btn = container.querySelector('button')!;
    expect(btn.classList.contains('qb-active')).toBe(true);
    expect(btn.classList.contains('qb-dim')).toBe(true);
  });

  it('renders the vertical grammar with a stamp and hue class', () => {
    const { container } = render(<Chip label="On camera" vertical="camera" active />);
    const btn = container.querySelector('button')!;
    expect(btn.classList.contains('qb-chip')).toBe(true);
    expect(btn.classList.contains('qb-c-clay')).toBe(true);
    expect(btn.querySelector('use')!.getAttribute('href')).toBe('#qb-stamp-camera');
  });

  it('fires onClick', () => {
    const onClick = vi.fn();
    render(<Chip label="remote" count={7} onClick={onClick} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
