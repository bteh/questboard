import { createRoute, redirect } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { LandingPage } from '@/components/landing/landing-page';
import { entryRedirectTarget } from '@/lib/entry';
import { hasOnboarded } from '@/lib/entry';
import { isDesktopApp } from '@/lib/platform';

/* The entry switch, split by surface.

   In a browser, / is the public download page: a stranger gets the landing
   (full bleed, no app chrome); anyone who has entered before goes to the
   masthead home and never sees the pitch again.

   Inside the desktop app there is no download story to tell. They already
   have it, so / jumps straight to the product: the masthead home once
   they've set up, the one-question place picker on first run.

   The flag reads are synchronous, so the redirect happens before paint. */
export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    if (isDesktopApp()) {
      throw redirect({ to: hasOnboarded() ? '/home' : '/start' });
    }
    const target = entryRedirectTarget();
    if (target) throw redirect({ to: target });
  },
  component: LandingPage,
});
