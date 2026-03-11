import { createRouter } from '@tanstack/react-router';
import { Route as rootRoute } from './routes/__root';
import { Route as indexRoute } from './routes/index';
import { Route as searchRoute } from './routes/search';
import { Route as applicationsRoute } from './routes/applications';
import { Route as analyticsRoute } from './routes/analytics';
import { Route as settingsRoute } from './routes/settings';

const routeTree = rootRoute.addChildren([
  indexRoute,
  searchRoute,
  applicationsRoute,
  analyticsRoute,
  settingsRoute,
]);

export const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
