import { createRoute, redirect } from '@tanstack/react-router';
import { Route as appRoute } from './app';

/* The old Restock address. Pulling jobs now lives on the board's Find work
   lane, so this route only forwards the reader there. Kept as a redirect so
   old bookmarks and the back button never dead-end. */
export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/restock',
  beforeLoad: () => {
    throw redirect({ to: '/board', search: { v: 'work' }, replace: true });
  },
});
