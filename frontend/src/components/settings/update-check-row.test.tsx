// @vitest-environment jsdom
/* Sep 8 2026: a person relaunched the app a minute after a release and saw
   nothing, because the launch check was throttled. Settings now has an
   explicit row that always checks and always says what it found. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import type { UpdateState } from '@/lib/updater-logic';

const hook = {
  state: { kind: 'idle' } as UpdateState,
  version: '0.2.3',
  checkNow: vi.fn(),
  restart: vi.fn(),
};
vi.mock('@/hooks/use-app-update', () => ({ useUpdateCheck: () => hook }));
vi.mock('@/lib/platform', () => ({ isDesktopApp: () => true }));

import { UpdateCheckRow } from './update-check-row';

afterEach(() => {
  cleanup();
  hook.state = { kind: 'idle' };
  hook.checkNow.mockReset();
  hook.restart.mockReset();
});

describe('UpdateCheckRow', () => {
  it('shows the current version and checks on click', () => {
    render(<UpdateCheckRow />);
    expect(screen.getByText('Questboard 0.2.3')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /check for updates/i }));
    expect(hook.checkNow).toHaveBeenCalledTimes(1);
  });

  it('says so when there is nothing newer', () => {
    hook.state = { kind: 'up_to_date' };
    render(<UpdateCheckRow />);
    expect(screen.getByText('You have the latest version, 0.2.3.')).toBeTruthy();
  });

  it('offers the restart once a version is downloaded', () => {
    hook.state = { kind: 'ready', version: '0.2.4' };
    render(<UpdateCheckRow />);
    fireEvent.click(screen.getByRole('button', { name: /restart to update/i }));
    expect(hook.restart).toHaveBeenCalledTimes(1);
  });

  it('offers a retry after an install that failed', () => {
    hook.state = { kind: 'install_failed', version: '0.2.6' };
    render(<UpdateCheckRow />);
    expect(screen.getByText(/couldn't install 0\.2\.6/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(hook.restart).toHaveBeenCalledTimes(1);
  });

  it('has nothing to click while the install runs', () => {
    hook.state = { kind: 'installing', version: '0.2.6' };
    render(<UpdateCheckRow />);
    expect(screen.getByText('Installing 0.2.6…')).toBeTruthy();
    expect((screen.getByRole('button', { name: /check for updates/i }) as HTMLButtonElement).disabled).toBe(true);
  });
});
