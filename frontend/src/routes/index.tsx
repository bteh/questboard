import { createRoute, redirect } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { LandingPage } from '@/components/landing/landing-page';
import { entryRedirectTarget } from '@/lib/entry';

/* The entry switch. A stranger gets the landing, full bleed, no app
   chrome; anyone who has entered before lands on the masthead home and
   never sees the pitch again. The flag read is synchronous, so the
   redirect happens before first paint. */
export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    const target = entryRedirectTarget();
    if (target) throw redirect({ to: target });
  },
  component: LandingPage,
});
