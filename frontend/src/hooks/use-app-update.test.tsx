// @vitest-environment jsdom
/* Owner, Oct 8 2026: "make the update pill not tucked away in privacy & data,
   but next to the search the board when there is truly an update". The pill
   already sat by the search box, but an app left open only re-checked every
   six hours, so a release published mid-session surfaced only through the
   Settings row. An open app must find a release within the hour, and coming
   back to the window must check too. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

vi.mock('@/lib/platform', () => ({ isDesktopApp: () => true }));

let lastChecked: number | null = null;
const fetchAndStageUpdate = vi.fn();

vi.mock('@/lib/updater', () => ({
  currentAppVersion: vi.fn(async () => '0.2.18'),
  fetchAndStageUpdate: (...args: unknown[]) => fetchAndStageUpdate(...args),
  installAndRestart: vi.fn(),
  readLastCheckedAt: () => lastChecked,
  writeLastCheckedAt: (t: number) => {
    lastChecked = t;
  },
}));

import { useAppUpdate } from './use-app-update';

const MINUTE = 60_000;

beforeEach(() => {
  vi.useFakeTimers();
  lastChecked = null;
  fetchAndStageUpdate.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useAppUpdate on an app left open', () => {
  it('checks once shortly after launch', () => {
    renderHook(() => useAppUpdate());
    vi.advanceTimersByTime(5_000);
    expect(fetchAndStageUpdate).toHaveBeenCalledTimes(1);
  });

  it('finds a release published mid-session within the hour', () => {
    renderHook(() => useAppUpdate());
    vi.advanceTimersByTime(5_000);
    fetchAndStageUpdate.mockClear();

    vi.advanceTimersByTime(60 * MINUTE);
    expect(fetchAndStageUpdate).toHaveBeenCalled();
  });

  it('checks when the reader comes back to the window after a while', () => {
    renderHook(() => useAppUpdate());
    vi.advanceTimersByTime(5_000);
    fetchAndStageUpdate.mockClear();

    vi.advanceTimersByTime(20 * MINUTE);
    window.dispatchEvent(new Event('focus'));
    expect(fetchAndStageUpdate).toHaveBeenCalledTimes(1);
  });

  it('does not re-check on every focus within a few minutes', () => {
    renderHook(() => useAppUpdate());
    vi.advanceTimersByTime(5_000);
    fetchAndStageUpdate.mockClear();

    vi.advanceTimersByTime(MINUTE);
    window.dispatchEvent(new Event('focus'));
    expect(fetchAndStageUpdate).not.toHaveBeenCalled();
  });
});
