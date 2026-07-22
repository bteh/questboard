import { createRouter } from '@tanstack/react-router';
import { Route as rootRoute } from './routes/__root';
import { Route as appRoute } from './routes/app';
import { Route as indexRoute } from './routes/index';
import { Route as welcomeRoute } from './routes/welcome';
import { Route as startRoute } from './routes/start';
import { Route as searchRedirect } from './routes/search';
import { Route as restockRoute } from './routes/restock';
import { Route as logRoute } from './routes/log';
import { Route as logLedgerRoute } from './routes/log-ledger';
import { Route as logNumbersRoute } from './routes/log-numbers';
import { Route as applicationsRedirect } from './routes/applications';
import { Route as analyticsRedirect } from './routes/analytics';
import { Route as settingsRoute } from './routes/settings';
import { Route as designRoute } from './routes/design';
import { Route as boardRoute } from './routes/board';
import { Route as homeRoute } from './routes/home';
import { Route as healthRoute } from './routes/health';

/* App pages live under the pathless 'app' layout (the trade-paper shell
   plus the hosted auth gate). The entry switch at /, the landing at
   /welcome, and the design sheet render bare under the root. The old
   /applications, /analytics, and /search addresses redirect to their
   new homes. */
const routeTree = rootRoute.addChildren([
  appRoute.addChildren([
    homeRoute,
    restockRoute,
    searchRedirect,
    logRoute,
    logLedgerRoute,
    logNumbersRoute,
    applicationsRedirect,
    analyticsRedirect,
    settingsRoute,
    boardRoute,
    healthRoute,
  ]),
  indexRoute,
  welcomeRoute,
  startRoute,
  designRoute,
]);

export const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
