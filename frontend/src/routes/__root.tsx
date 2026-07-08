import { createRootRoute, Outlet } from '@tanstack/react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@/lib/query-client';
import { ProfileProvider } from '@/contexts/profile-context';
import { SearchProvider } from '@/contexts/search-context';
import { ThemeProvider } from '@/contexts/theme-context';
import { WorkspaceProvider } from '@/contexts/workspace-context';

export const Route = createRootRoute({
  component: RootLayout,
});

/* Providers only. The trade-paper shell lives on the pathless 'app'
   layout route; landing-class routes render bare under this root. */
function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <WorkspaceProvider>
          <ProfileProvider>
            <SearchProvider>
              <Outlet />
            </SearchProvider>
          </ProfileProvider>
        </WorkspaceProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
