// @vitest-environment jsdom
/* Real case (Oct 8 2026): for entry IT work, contract-to-hire through Robert
   Half, TEKsystems, Insight Global or Apex is a common way back in, and the
   pull dropped every agency. The box is off by default, as before. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { StaffingToggle } from './staffing-toggle';

// jsdom has no PointerEvent and the base-ui checkbox builds one on click.
if (typeof window.PointerEvent === 'undefined') {
  (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = MouseEvent;
}

afterEach(cleanup);

describe('StaffingToggle', () => {
  it('is off while agencies are excluded, with the plain copy', () => {
    render(<StaffingToggle excludeStaffingAgencies onChange={() => {}} />);
    const box = screen.getByRole('checkbox', { name: 'Include staffing agencies' });
    expect(box.getAttribute('aria-checked')).toBe('false');
    expect(screen.getByText('Staffing agencies. Often contract-to-hire. A common way back into IT.')).toBeTruthy();
  });

  it('turning it on stops excluding agencies', () => {
    const onChange = vi.fn();
    render(<StaffingToggle excludeStaffingAgencies onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include staffing agencies' }));
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it('turning it off excludes agencies again', () => {
    const onChange = vi.fn();
    render(<StaffingToggle excludeStaffingAgencies={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include staffing agencies' }));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});
