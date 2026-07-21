// @vitest-environment jsdom
/* The entry switch, split by surface. In the desktop app there is no
   download pitch to show, so / jumps straight to the product; in a browser a
   returning reader skips to the masthead home and a stranger gets the
   landing (no throw). */

import { afterEach, describe, expect, it } from 'vitest';
import { isRedirect } from '@tanstack/react-router';
import { Route as indexRoute } from './index';

const beforeLoad = indexRoute.options.beforeLoad as (ctx: object) => void;

function setDesktop(on: boolean) {
  if (on) (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
  else delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
}

function redirectTo(run: () => unknown): string | undefined {
  try {
    run();
  } catch (thrown) {
    if (isRedirect(thrown)) return (thrown as { options: { to?: string } }).options.to;
    throw thrown;
  }
  return undefined;
}

afterEach(() => {
  setDesktop(false);
  window.localStorage.clear();
});

describe('/ entry switch', () => {
  it('desktop first-run goes to the place picker', () => {
    setDesktop(true);
    expect(redirectTo(() => beforeLoad({}))).toBe('/start');
  });

  it('desktop returning user goes to the masthead home, never the landing', () => {
    setDesktop(true);
    window.localStorage.setItem('questboard:onboarded', '1');
    expect(redirectTo(() => beforeLoad({}))).toBe('/home');
  });

  it('a browser stranger gets the landing (no redirect)', () => {
    setDesktop(false);
    expect(redirectTo(() => beforeLoad({}))).toBeUndefined();
  });

  it('a browser returner skips the pitch and goes home', () => {
    setDesktop(false);
    window.localStorage.setItem('questboard:entered', '1');
    expect(redirectTo(() => beforeLoad({}))).toBe('/home');
  });
});
