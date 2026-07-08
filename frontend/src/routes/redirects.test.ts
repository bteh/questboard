import { describe, expect, it } from 'vitest';
import { isRedirect } from '@tanstack/react-router';
import { Route as searchRedirect } from './search';

/* The old /search address must forward to /restock permanently. The route
   is nothing but a beforeLoad throw; the test pins the throw and where it
   points. */

function catchRedirect(run: () => unknown): unknown {
  try {
    run();
  } catch (thrown) {
    return thrown;
  }
  throw new Error('expected the route to throw a redirect');
}

describe('/search', () => {
  it('redirects to /restock, replacing the history entry', () => {
    const beforeLoad = searchRedirect.options.beforeLoad as (ctx: object) => void;
    const thrown = catchRedirect(() => beforeLoad({}));
    expect(isRedirect(thrown)).toBe(true);
    const options = (thrown as { options: { to?: string; replace?: boolean } }).options;
    expect(options.to).toBe('/restock');
    expect(options.replace).toBe(true);
  });
});
