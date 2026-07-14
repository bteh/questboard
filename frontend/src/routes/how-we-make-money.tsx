import { createRoute } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import { MoneyPage } from '@/features/money/money-page';

/* Who pays Questboard and who never does, at a stable address. The door
   in is the drawer. */
export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/how-we-make-money',
  component: MoneyPage,
});
