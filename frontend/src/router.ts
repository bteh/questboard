import { createRouter } from '@tanstack/react-router';
import { Route as rootRoute } from './routes/__root';
import { Route as appRoute } from './routes/app';
import { Route as indexRoute } from './routes/index';
import { Route as searchRoute } from './routes/search';
import { Route as applicationsRoute } from './routes/applications';
import { Route as analyticsRoute } from './routes/analytics';
import { Route as settingsRoute } from './routes/settings';
import { Route as designRoute } from './routes/design';
import { Route as boardRoute } from './routes/board';

/* App pages live under the pathless 'app' layout (the trade-paper shell
   plus the hosted auth gate). Design stays bare under the root. */
const routeTree = rootRoute.addChildren([
  appRoute.addChildren([
    indexRoute,
    searchRoute,
    applicationsRoute,
    analyticsRoute,
    settingsRoute,
    boardRoute,
  ]),
  designRoute,
]);

export const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
