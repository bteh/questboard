import { createRoute, redirect } from '@tanstack/react-router';
import { Route as appRoute } from './app';

/* The old Applications address. The page itself lives on at /log/ledger;
   this route only carries the run and scope params across. */
export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/applications',
  validateSearch: (search: Record<string, unknown>) => ({
    run: (search.run as string) || undefined,
    scope:
      search.scope === 'all'
        ? 'all'
        : search.scope === 'new'
          ? 'new'
          : undefined,
  }),
  beforeLoad: ({ search }) => {
    throw redirect({ to: '/log/ledger', search, replace: true });
  },
});
