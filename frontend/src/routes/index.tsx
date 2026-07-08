import { createRoute, redirect } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { LandingPage } from '@/components/landing/landing-page';
import { hasEntered } from '@/lib/entry';

/* The entry switch. A stranger gets the landing, full bleed, no app
   chrome; anyone who has entered before skips the pitch entirely. The
   flag read is synchronous, so the redirect happens before first paint.
   NB: PR 3 flips the redirect target to /home once the masthead home
   exists; until then returners land on the board itself. */
export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    if (hasEntered()) throw redirect({ to: '/board' });
  },
  component: LandingPage,
});
