import { createRoute } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { AppShell } from '@/components/shell/app-shell';
import { HostedAuthScreen } from '@/components/auth/hosted-auth-screen';
import { useWorkspace } from '@/contexts/workspace-context';

/* Pathless layout: every app page renders inside the trade-paper shell.
   The hosted-mode auth gate lives here, so landing-class routes under
   the root never see it. */
export const Route = createRoute({
  getParentRoute: () => rootRoute,
  id: 'app',
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
