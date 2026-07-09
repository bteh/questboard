import { createRoute } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { AppShell } from '@/features/shell/app-shell';
import { HostedAuthScreen } from '@/components/auth/hosted-auth-screen';
import { useWorkspace } from '@/contexts/workspace-context';
import { markEntered } from '@/lib/entry';

/* Pathless layout: every app page renders inside the trade-paper shell.
   The hosted-mode auth gate lives here, so landing-class routes under
   the root never see it. Reaching any app page counts as entering, so a
   deep link to /board on a phone never bounces through marketing later. */
export const Route = createRoute({
  getParentRoute: () => rootRoute,
  id: 'app',
  beforeLoad: () => {
    markEntered();
  },
  component: AppLayout,
});

function AppLayout() {
  const { hostedMode, isAuthenticated, isLoading } = useWorkspace();

  if (hostedMode && isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-page px-4">
        <p className="text-sm text-text-secondary">Restoring hosted session...</p>
      </div>
    );
  }

  if (hostedMode && !isAuthenticated) {
    return <HostedAuthScreen />;
  }

  return <AppShell />;
}
