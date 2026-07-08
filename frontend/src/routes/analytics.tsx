import { createRoute, redirect } from '@tanstack/react-router';
import { Route as appRoute } from './app';

/* The old Analytics address; the charts live on at /log/numbers. */
export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/analytics',
  beforeLoad: () => {
    throw redirect({ to: '/log/numbers', replace: true });
  },
});
