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

export function AppLayout() {
  const { hostedMode, isAuthenticated, isLoading, error } = useWorkspace();

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

  /* Local bootstrap failed: without a session token every call 401s, so
     mounting the shell would just look broken. Say so instead. */
  if (!hostedMode && error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-page px-4">
        <div className="w-full max-w-md space-y-3">
          <h1 className="text-base font-semibold text-text-primary">
            Questboard could not start its local workspace.
          </h1>
          <p className="text-sm text-text-secondary">
            The window opened, but the part that stores your board did not answer. Quit and reopen
            Questboard. If that does not fix it, restart your Mac.
          </p>
          <button
            type="button"
            className="rounded-lg border border-border-default px-3 py-1.5 text-sm font-medium text-text-primary"
            onClick={() => window.location.reload()}
          >
            Try again
          </button>
          <details className="text-xs text-text-muted">
            <summary className="cursor-pointer">Error detail</summary>
            <p className="mt-1 break-words">{error}</p>
          </details>
        </div>
      </div>
    );
  }

  return <AppShell />;
}
