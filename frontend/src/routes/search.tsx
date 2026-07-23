import { createRoute, redirect } from '@tanstack/react-router';
import { Route as appRoute } from './app';

/* The old Search address. Pulling jobs now lives on the board's Find work
   lane, so this route only forwards the reader there. */
export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/search',
  beforeLoad: () => {
    throw redirect({ to: '/board', search: { v: 'work' }, replace: true });
  },
});
