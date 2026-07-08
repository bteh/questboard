import { useState } from 'react';
import { ArrowRight, ShieldCheck, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { BrandMark } from '@/components/shared/brand-mark';
import { useWorkspace } from '@/contexts/workspace-context';

export function HostedAuthScreen() {
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
  const [email, setEmail] = useState('test-user@questboard.local');
  const [fullName, setFullName] = useState('Questboard Test User');
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
                        <BrandMark className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-text-primary tracking-tight">Questboard</p>
                        <p className="text-xs text-text-muted">Hosted onboarding, local machine</p>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <h1 className="max-w-xl text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
                        Sign in to Questboard
                      </h1>
                      <p className="max-w-xl text-sm leading-6 text-text-secondary">
                        Create a blank account or pick a sample persona below.
                      </p>
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
          <CardTitle>Sign in to Questboard</CardTitle>
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
