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
import { OnboardingWizard } from '@/components/onboarding/onboarding-wizard';
import { useOnboarding } from '@/hooks/use-onboarding';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { ArrowRight, Briefcase, Menu, ShieldCheck, Sparkles, Upload, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

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
  const { isLoading, error, isAuthenticated, hostedMode } = useWorkspace();
  const { shouldShow, dismiss } = useOnboarding();
  const [dismissed, setDismissed] = useState(false);

  if (isLoading) return null;
  if (error) return null;
  if (hostedMode && !isAuthenticated) return null;
  if (!shouldShow || dismissed) return null;

  return (
    <OnboardingWizard
      open
      onComplete={() => {
        dismiss();
        setDismissed(true);
      }}
    />
  );
}

function HostedAuthScreen() {
  const {
    error,
    isLoading,
    personas,
    devHostedAuth,
    signInWithTestAccount,
    signInWithGoogle,
    sendMagicLink,
    signInAsPersona,
    refresh,
  } = useWorkspace();
  const [email, setEmail] = useState('test-user@launchboard.local');
  const [fullName, setFullName] = useState('Launchboard Test User');
  const [emailSent, setEmailSent] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [showSampleUsers, setShowSampleUsers] = useState(false);

  async function handleMagicLink() {
    setAuthError(null);
    setEmailSent(false);
    try {
      await sendMagicLink(email);
      setEmailSent(true);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Failed to send magic link');
    }
  }

  async function handlePersonaSignIn(personaId: string) {
    setAuthError(null);
    try {
      await signInAsPersona(personaId);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Failed to start persona session');
    }
  }

  async function handleTestAccount() {
    setAuthError(null);
    try {
      await signInWithTestAccount(email, fullName, true);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Failed to start test account');
    }
  }

  if (devHostedAuth) {
    return (
      <div className="relative min-h-screen overflow-hidden bg-bg-page">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute left-[-8rem] top-[-8rem] h-64 w-64 rounded-full bg-brand-light blur-3xl opacity-80" />
          <div className="absolute right-[-6rem] top-24 h-56 w-56 rounded-full bg-bg-subtle blur-3xl opacity-90" />
          <div className="absolute bottom-[-5rem] left-1/3 h-48 w-48 rounded-full bg-brand-light blur-3xl opacity-60" />
        </div>

        <div className="relative mx-auto flex min-h-screen max-w-6xl items-center px-4 py-10 sm:px-6 lg:px-8">
          <div className="grid w-full gap-6 lg:grid-cols-[1.05fr_0.95fr]">
            <Card className="border-border-default/80 bg-bg-card/95 backdrop-blur">
              <CardContent className="flex h-full flex-col justify-between gap-8 px-6 py-6 sm:px-8 sm:py-8">
                <div className="space-y-6">
                  <div className="inline-flex items-center gap-2 rounded-full border border-border-default bg-bg-subtle px-3 py-1 text-xs font-medium text-text-secondary">
                    <ShieldCheck className="h-3.5 w-3.5 text-brand" />
                    Local hosted sandbox
                  </div>

                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand shadow-sm">
                        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" className="text-white">
                          <path d="M4 12V4l4 2v6l-4-2z" fill="currentColor" opacity="0.7" />
                          <path d="M8 6l4-2v8l-4 2V6z" fill="currentColor" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-text-primary tracking-tight">Launchboard</p>
                        <p className="text-xs text-text-muted">Hosted onboarding, local machine</p>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h1 className="max-w-xl text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
                        Test the real hosted flow before you ship it
                      </h1>
                      <p className="max-w-xl text-sm leading-6 text-text-secondary sm:text-base">
                        Create a blank account, upload a resume, and walk through Launchboard the same way a hosted user would.
                        Sample users are still available, but they are optional.
                      </p>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    {[
                      {
                        icon: Upload,
                        title: 'Upload-first',
                        description: 'Start empty and verify the real resume onboarding path.',
                      },
                      {
                        icon: Briefcase,
                        title: 'Hosted semantics',
                        description: 'Bearer auth, isolated workspaces, durable jobs, and worker-backed runs.',
                      },
                      {
                        icon: Sparkles,
                        title: 'QA ready',
                        description: 'Optional seeded users let you compare different industries and search goals.',
                      },
                    ].map(({ icon: Icon, title, description }) => (
                      <div key={title} className="rounded-2xl border border-border-default bg-bg-subtle/70 p-4">
                        <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl bg-brand-light">
                          <Icon className="h-4 w-4 text-brand" />
                        </div>
                        <p className="text-sm font-medium text-text-primary">{title}</p>
                        <p className="mt-1 text-xs leading-5 text-text-tertiary">{description}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-border-default bg-bg-subtle/60 p-4">
                  <p className="text-xs font-medium uppercase tracking-[0.14em] text-text-muted">What this is for</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl bg-bg-card px-4 py-3">
                      <p className="text-sm font-medium text-text-primary">Primary path</p>
                      <p className="mt-1 text-sm text-text-secondary">Create a test account and upload your own resume.</p>
                    </div>
                    <div className="rounded-xl bg-bg-card px-4 py-3">
                      <p className="text-sm font-medium text-text-primary">Secondary path</p>
                      <p className="mt-1 text-sm text-text-secondary">Switch to seeded personas when you need richer QA scenarios.</p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-border-default/80 bg-bg-card/95 backdrop-blur">
              <CardHeader className="space-y-3 border-b border-border-default pb-5">
                <div className="flex items-center gap-2">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-light">
                    <ArrowRight className="h-4 w-4 text-brand" />
                  </div>
                  <div>
                    <CardTitle>Create a test account</CardTitle>
                    <CardDescription>Blank workspace, real onboarding, local-only auth.</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-6 pt-6">
                <div className="grid gap-3">
                  <div className="rounded-xl border border-border-default bg-bg-subtle px-4 py-3">
                    <p className="text-sm font-medium text-text-primary">1. Start with a clean user</p>
                    <p className="mt-1 text-sm text-text-secondary">No seeded resume or preferences unless you choose sample users below.</p>
                  </div>
                  <div className="rounded-xl border border-border-default bg-bg-subtle px-4 py-3">
                    <p className="text-sm font-medium text-text-primary">2. Upload a resume</p>
                    <p className="mt-1 text-sm text-text-secondary">Verify parsing, AI suggestions, search setup, and application flow end to end.</p>
                  </div>
                </div>

                <div className="grid gap-4">
                  <div className="space-y-2">
                    <label className="text-xs font-medium uppercase tracking-[0.12em] text-text-muted">Full name</label>
                    <Input
                      placeholder="Jane Applicant"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-xs font-medium uppercase tracking-[0.12em] text-text-muted">Email</label>
                    <Input
                      type="email"
                      placeholder="jane@example.com"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                    />
                  </div>
                </div>

                <p className="text-xs text-text-muted">
                  These are editable sandbox defaults. Continuing here resets this test account to a blank workspace.
                </p>

                <Button
                  className="h-10 w-full justify-between px-4"
                  disabled={!email.trim() || !fullName.trim() || isLoading}
                  onClick={() => void handleTestAccount()}
                >
                  <span>Continue with blank test account</span>
                  <ArrowRight className="h-4 w-4" />
                </Button>

                <div className="rounded-2xl border border-dashed border-border-default bg-bg-subtle/60 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-brand" />
                        <p className="text-sm font-medium text-text-primary">Sample users</p>
                      </div>
                      <p className="text-sm text-text-secondary">
                        Optional QA fixtures with preloaded resumes, industries, and search intent.
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setShowSampleUsers((value) => !value)}>
                      {showSampleUsers ? 'Hide' : 'Show'}
                    </Button>
                  </div>

                  {showSampleUsers && (
                    <div className="mt-4 grid gap-3">
                      {personas.map((persona) => (
                        <div
                          key={persona.id}
                          className="rounded-xl border border-border-default bg-bg-card px-4 py-4"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="space-y-2">
                              <div>
                                <p className="text-sm font-semibold text-text-primary">{persona.full_name}</p>
                                <p className="text-sm text-text-secondary">{persona.headline}</p>
                              </div>
                              <div className="grid gap-1 text-xs leading-5 text-text-tertiary">
                                <p>{persona.job_search_focus}</p>
                                <p><span className="font-medium text-text-primary">Resume:</span> {persona.resume_filename}</p>
                              </div>
                            </div>
                            <Button
                              size="sm"
                              className="shrink-0"
                              disabled={isLoading}
                              onClick={() => void handlePersonaSignIn(persona.id)}
                            >
                              Use
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-xl bg-bg-subtle px-4 py-3 text-xs leading-5 text-text-muted">
                  This screen only appears when the local sandbox is started with dev hosted auth enabled.
                </div>

                {(authError || error) && (
                  <div className="space-y-2 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3">
                    <p className="text-sm text-destructive">{authError || error}</p>
                    <Button variant="ghost" className="w-full" onClick={() => void refresh()}>
                      Retry sandbox bootstrap
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-page px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in to Launchboard</CardTitle>
          <CardDescription>
            Hosted beta access uses Google sign-in, with email magic links as fallback.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button className="w-full" onClick={() => void signInWithGoogle()}>
            Continue with Google
          </Button>
          <div className="space-y-2">
            <Input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <Button
              variant="outline"
              className="w-full"
              disabled={!email || isLoading}
              onClick={() => void handleMagicLink()}
            >
              Send magic link
            </Button>
          </div>
          {emailSent && <p className="text-sm text-text-secondary">Magic link sent. Check your inbox.</p>}
          {(authError || error) && (
            <div className="space-y-2">
              <p className="text-sm text-destructive">{authError || error}</p>
              <Button variant="ghost" className="w-full" onClick={() => void refresh()}>
                Retry session check
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AppShell() {
  const { hostedMode, isAuthenticated, isLoading, workspaceId } = useWorkspace();
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

  return (
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
      <OnboardingGate key={workspaceId ?? 'anonymous-workspace'} />
      <Toaster />
    </TooltipProvider>
  );
}

function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <WorkspaceProvider>
          <ProfileProvider>
            <SearchProvider>
              <AppShell />
            </SearchProvider>
          </ProfileProvider>
        </WorkspaceProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
