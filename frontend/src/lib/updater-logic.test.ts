import { describe, expect, it } from 'vitest';

import {
  CHECK_INTERVAL_MS,
  downloadPercent,
  shouldCheck,
  updateBannerText,
} from './updater-logic';

describe('shouldCheck', () => {
  it('checks on a machine that has never checked', () => {
    expect(shouldCheck(null, 1_000)).toBe(true);
  });

  it('does not re-check inside the interval', () => {
    const now = 10 * CHECK_INTERVAL_MS;
    expect(shouldCheck(now - 60_000, now)).toBe(false);
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

  it('names the version once it is downloaded and ready', () => {
    expect(updateBannerText({ kind: 'ready', version: '0.3.0' })).toBe(
      'Version 0.3.0 is ready.',
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
