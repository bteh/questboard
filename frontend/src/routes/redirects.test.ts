import { describe, expect, it } from 'vitest';
import { isRedirect } from '@tanstack/react-router';
import { Route as searchRedirect } from './search';
import { Route as restockRedirect } from './restock';

/* The old /search address must forward to the board's Find work lane
   permanently. The route is nothing but a beforeLoad throw; the test pins
   the throw and where it points. */

function catchRedirect(run: () => unknown): unknown {
  try {
    run();
  } catch (thrown) {
    return thrown;
  }
  throw new Error('expected the route to throw a redirect');
}

describe('/search', () => {
  it('redirects to the board work lane, replacing the history entry', () => {
    const beforeLoad = searchRedirect.options.beforeLoad as (ctx: object) => void;
    const thrown = catchRedirect(() => beforeLoad({}));
    expect(isRedirect(thrown)).toBe(true);
    const options = (thrown as { options: { to?: string; search?: { v?: string }; replace?: boolean } }).options;
    expect(options.to).toBe('/board');
    expect(options.search?.v).toBe('work');
    expect(options.replace).toBe(true);
  });
});

describe('/restock', () => {
  it('redirects to the board work lane, replacing the history entry', () => {
    const beforeLoad = restockRedirect.options.beforeLoad as (ctx: object) => void;
    const thrown = catchRedirect(() => beforeLoad({}));
    expect(isRedirect(thrown)).toBe(true);
    const options = (thrown as { options: { to?: string; search?: { v?: string }; replace?: boolean } }).options;
    expect(options.to).toBe('/board');
    expect(options.search?.v).toBe('work');
    expect(options.replace).toBe(true);
  });
});
