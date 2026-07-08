import { createRoute } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { LandingPage } from '@/components/landing/landing-page';

/* The stable marketing URL: always the landing, for entered users too
   (their CTA reads "Back to the board"). Never sets the flag on mount;
   only a CTA click counts as entering. */
export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/welcome',
  component: LandingPage,
});
