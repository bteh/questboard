import { createRoute, redirect } from '@tanstack/react-router';
import { Route as appRoute } from './app';

/* The old Search address. The page itself lives on at /restock, whole;
   this route only forwards the reader. */
export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/search',
  beforeLoad: () => {
    throw redirect({ to: '/restock', replace: true });
  },
});
