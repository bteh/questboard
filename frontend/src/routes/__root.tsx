import { useState, useEffect } from 'react';
import { createRootRoute, Outlet, useRouter, useMatches, Link } from '@tanstack/react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';
import { queryClient } from '@/lib/query-client';
import { ProfileProvider } from '@/contexts/profile-context';
import { SearchProvider } from '@/contexts/search-context';
import { ThemeProvider } from '@/contexts/theme-context';
import { WorkspaceProvider, useWorkspace } from '@/contexts/workspace-context';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { Sidebar } from '@/components/layout/sidebar';
import { OnboardingWizard, useOnboarding } from '@/components/onboarding/onboarding-wizard';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';

export const Route = createRootRoute({
  component: RootLayout,
});

function MobileHeader({ onMenuOpen }: { onMenuOpen: () => void }) {
  return (
    <div className="flex items-center gap-3 border-b border-border-default bg-bg-card px-4 py-2.5 lg:hidden">
      <Button variant="ghost" size="sm" onClick={onMenuOpen} aria-label="Open navigation menu">
        <Menu className="h-5 w-5" />
      </Button>
      <Link to="/" className="flex items-center gap-2 cursor-pointer">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand shadow-sm">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-white">
            <path d="M4 12V4l4 2v6l-4-2z" fill="currentColor" opacity="0.7" />
            <path d="M8 6l4-2v8l-4 2V6z" fill="currentColor" />
          </svg>
        </div>
        <span className="text-sm font-semibold text-text-primary tracking-tight">Launchboard</span>
      </Link>
    </div>
  );
}

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/search': 'Search',
  '/applications': 'Applications',
  '/analytics': 'Analytics',
  '/settings': 'Settings',
};

function OnboardingGate() {
  const { isLoading, error } = useWorkspace();
  const { shouldShow, dismiss } = useOnboarding();
  const [open, setOpen] = useState(true);

  if (isLoading) return null;
  if (error) return null;
  if (!shouldShow || !open) return null;

  return (
    <OnboardingWizard
      open
      onComplete={() => {
        dismiss();
        setOpen(false);
      }}
    />
  );
}

function RootLayout() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const router = useRouter();
  const matches = useMatches();

  // Update document title on route change
  useEffect(() => {
    const path = matches[matches.length - 1]?.fullPath || '/';
    const title = PAGE_TITLES[path] || 'Launchboard';
    document.title = `${title} — Launchboard`;
  }, [matches]);

  // Close mobile menu on route change
  useEffect(() => {
    const unsub = router.subscribe('onBeforeNavigate', () => {
      setMobileMenuOpen(false);
    });
    return unsub;
  }, [router]);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
      <WorkspaceProvider>
      <ProfileProvider>
        <SearchProvider>
        <TooltipProvider>
          <div className="flex h-screen overflow-hidden bg-bg-page">
            {/* Desktop sidebar */}
            <div className="hidden lg:block">
              <Sidebar />
            </div>

            {/* Mobile sheet sidebar */}
            <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
              <SheetContent side="left" showCloseButton={false} className="w-64 p-0">
                <Sidebar />
              </SheetContent>
            </Sheet>

            <div className="flex flex-1 flex-col overflow-hidden">
              <MobileHeader onMenuOpen={() => setMobileMenuOpen(true)} />
              <main className="flex-1 overflow-y-auto">
                <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
                  <ErrorBoundary>
                    <Outlet />
                  </ErrorBoundary>
                </div>
              </main>
            </div>
          </div>
          <OnboardingGate />
          <Toaster />
        </TooltipProvider>
        </SearchProvider>
      </ProfileProvider>
      </WorkspaceProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
