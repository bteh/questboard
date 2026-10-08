import { describe, expect, it } from 'vitest';

import {
  CHECK_INTERVAL_MS,
  RECHECK_AFTER_MS,
  checkStatusText,
  downloadPercent,
  shouldCheck,
  updateActionText,
  updateBannerLabel,
  updateBannerText,
} from './updater-logic';
import type { UpdateState } from './updater-logic';

describe('shouldCheck', () => {
  it('checks on a machine that has never checked', () => {
    expect(shouldCheck(null, 1_000)).toBe(true);
  });

  it('does not re-check inside the throttle window', () => {
    const now = 10 * CHECK_INTERVAL_MS;
    expect(shouldCheck(now - 60_000, now)).toBe(false);
  });

  it('lets the half-hour timer through, so an open app finds a release within the hour', () => {
    expect(RECHECK_AFTER_MS).toBeLessThanOrEqual(CHECK_INTERVAL_MS);
    expect(CHECK_INTERVAL_MS).toBeLessThanOrEqual(60 * 60 * 1000);
    const now = 10 * CHECK_INTERVAL_MS;
    expect(shouldCheck(now - CHECK_INTERVAL_MS, now)).toBe(true);
  });

  it('never checks while an update is in flight or waiting on a restart', () => {
    const busy: UpdateState[] = [
      { kind: 'checking' },
      { kind: 'downloading', percent: 10 },
      { kind: 'ready', version: '0.3.0' },
      { kind: 'installing', version: '0.3.0' },
      { kind: 'install_failed', version: '0.3.0' },
      { kind: 'installed', version: '0.3.0' },
    ];
    for (const state of busy) expect(shouldCheck(null, 1_000, state)).toBe(false);
  });

  it('checks again after a failed or empty check', () => {
    expect(shouldCheck(null, 1_000, { kind: 'failed' })).toBe(true);
    expect(shouldCheck(null, 1_000, { kind: 'up_to_date' })).toBe(true);
  });

  it('checks once after a long sleep, not once per missed interval', () => {
    const now = 10 * CHECK_INTERVAL_MS;
    const aWeekAgo = now - 7 * 24 * 60 * 60 * 1000;
    expect(shouldCheck(aWeekAgo, now)).toBe(true);
  });
});

describe('updateBannerText', () => {
  it('says nothing on a fresh install with no update', () => {
    expect(updateBannerText({ kind: 'idle' })).toBeNull();
  });

  it('stays silent while downloading', () => {
    expect(updateBannerText({ kind: 'downloading', percent: 42 })).toBeNull();
  });

  it('never shows a failed check to the user', () => {
    // A failed check means no endpoint, no network, or a half-published
    // release. The user did not ask and cannot act, so it stays quiet.
    expect(updateBannerText({ kind: 'failed' })).toBeNull();
  });

  it('keeps the ready pill short, with Restart as the action', () => {
    const ready: UpdateState = { kind: 'ready', version: '0.3.0' };
    expect(updateBannerText(ready)).toBe('Update ready');
    expect(updateActionText(ready)).toBe('Restart');
  });

  it('keeps the version in the full label', () => {
    expect(updateBannerLabel({ kind: 'ready', version: '0.3.0' })).toBe(
      'Version 0.3.0 is ready. Restart to update.',
    );
  });
});

describe('downloadPercent', () => {
  it('reports zero when the server sends no content length', () => {
    expect(downloadPercent(5_000, null)).toBe(0);
  });

  it('never exceeds 100 when the payload runs long', () => {
    expect(downloadPercent(120, 100)).toBe(100);
  });

  it('rounds to a whole percent', () => {
    expect(downloadPercent(333, 1000)).toBe(33);
  });
});

describe('checkStatusText (the explicit Settings row)', () => {
  it('says plainly when there is nothing to do, which the pill never does', () => {
    expect(updateBannerText({ kind: 'up_to_date' })).toBeNull();
    expect(checkStatusText({ kind: 'up_to_date' }, '0.2.3')).toBe('You have the latest version, 0.2.3.');
  });

  it('names the downloaded version and the restart', () => {
    expect(checkStatusText({ kind: 'ready', version: '0.2.4' }, '0.2.3')).toMatch(/0\.2\.4.*Restart/);
  });

  it('turns a failed check into something a person can act on', () => {
    expect(checkStatusText({ kind: 'failed' }, '0.2.3')).toMatch(/connection/i);
  });
});
