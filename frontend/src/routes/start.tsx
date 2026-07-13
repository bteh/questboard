import { createRoute, redirect } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { StartPage } from '@/components/onboarding/start-page';
import { hasOnboarded } from '@/lib/entry';

/* The one-question first run, bare under the root (no app shell, so
   arriving here does not count as entering until the reader finishes).
   Anyone who has already set their place skips straight to the board. */
export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/start',
  beforeLoad: () => {
    if (hasOnboarded()) throw redirect({ to: '/board' });
  },
  component: StartPage,
});
