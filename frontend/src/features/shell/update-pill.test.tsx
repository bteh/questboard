// @vitest-environment jsdom
/* The topbar pill after a restart that failed to install: it must say the
   app still works and offer a retry, not sit there saying "Restart". */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import type { UpdateState } from '@/lib/updater-logic';

const hook = {
  state: { kind: 'idle' } as UpdateState,
  restart: vi.fn(),
};
vi.mock('@/hooks/use-app-update', () => ({ useAppUpdate: () => hook }));

import { UpdatePill } from './update-pill';

afterEach(() => {
  cleanup();
  hook.state = { kind: 'idle' };
  hook.restart.mockReset();
});

describe('UpdatePill', () => {
  it('offers Restart once an update is ready', () => {
    hook.state = { kind: 'ready', version: '0.2.6' };
    render(<UpdatePill />);
    const button = screen.getByRole('button', { name: /version 0\.2\.6 is ready\. restart/i });
    fireEvent.click(button);
    expect(hook.restart).toHaveBeenCalledTimes(1);
  });

  it('reads "Update ready" with a bold Restart in the accent style', () => {
    hook.state = { kind: 'ready', version: '0.2.6' };
    render(<UpdatePill />);
    const button = screen.getByRole('button');
    expect(button.textContent).toBe('Update ready Restart');
    expect(button.querySelector('b')?.textContent).toBe('Restart');
    expect(button.className).toContain('qb-update-pill-ready');
    expect(button.getAttribute('title')).toMatch(/0\.2\.6/);
  });

  it('keeps the failed-install retry in the quiet style', () => {
    hook.state = { kind: 'install_failed', version: '0.2.6' };
    render(<UpdatePill />);
    expect(screen.getByRole('button').className).not.toContain('qb-update-pill-ready');
  });

  it('shows nothing when there is no update', () => {
    hook.state = { kind: 'up_to_date' };
    const { container } = render(<UpdatePill />);
    expect(container.textContent).toBe('');
  });

  it('says a failed install left the app working and offers Try again', () => {
    hook.state = { kind: 'install_failed', version: '0.2.6' };
    render(<UpdatePill />);
    const button = screen.getByRole('button', { name: /couldn't install 0\.2\.6\. the app still works\. try again/i });
    fireEvent.click(button);
    expect(hook.restart).toHaveBeenCalledTimes(1);
  });

  it('shows installing with nothing to click', () => {
    hook.state = { kind: 'installing', version: '0.2.6' };
    render(<UpdatePill />);
    expect(screen.getByText(/installing 0\.2\.6/i)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
