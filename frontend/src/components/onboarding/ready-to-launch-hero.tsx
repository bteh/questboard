import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  FileText,
  Loader2,
  MapPin,
  Settings as SettingsIcon,
  Sparkles,
  Tag,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { ConnectAiPopover } from '@/components/onboarding/connect-ai-popover';
import { GeneratedProfileCard } from '@/components/onboarding/generated-profile-card';
import { useSearchContext } from '@/contexts/search-context';
import { useLLMStatus } from '@/hooks/use-settings';
import {
  useGenerateProfile,
  useOnboardingState,
  useSaveWorkspacePreferences,
  useStartOnboardingSearch,
} from '@/hooks/use-workspace';
import { getSearchAreaSummary } from '@/lib/search-area';
import {
  buildSearchRunSnapshot,
  buildSearchSnapshotMetadataFromPreferences,
} from '@/lib/search-preferences';
import type { SearchRunSnapshot } from '@/types/search';
import type {
  GeneratedProfile,
  WorkspacePreferences,
} from '@/types/workspace';

/**
 * "Ready to launch" state shown on the dashboard between completing the
 * onboarding wizard and starting the very first search. The wizard now
 * SAVES preferences and routes here so the user owns the moment of
 * clicking Start instead of feeling rushed past their settings.
 *
 * Visible when:
 * - workspace has saved preferences (resume uploaded or roles/keywords set)
 * - no search has ever been started (`has_started_search === false`)
 * - the search context is idle
 */
export function ReadyToLaunchHero() {
  const navigate = useNavigate();
  const { data: onboarding } = useOnboardingState();
  const { data: llm } = useLLMStatus();
  const { activate } = useSearchContext();
  const startOnboardingSearch = useStartOnboardingSearch();
  const savePreferences = useSaveWorkspacePreferences();
  const generateProfile = useGenerateProfile();

  // The user's preferred view: either show the AI-tailored card if we
  // have one, or hide it and show the manual template summary. Defaults
  // to AI when available.
  const [view, setView] = useState<'ai' | 'manual'>('ai');

  // We deliberately do NOT auto-trigger profile generation. Earlier
  // versions auto-fired the mutation in a useEffect on mount; that
  // collided with React 19 + StrictMode's double-invoke and left the
  // loading state stuck after a failed call. The new flow is explicit:
  // the user clicks "Tailor my profile with AI" and gets a clear
  // request → response cycle. Better UX (no surprise LLM calls) and
  // more predictable rendering.
  const aiAvailable = llm?.available ?? false;
  const resumeExists = onboarding?.resume.exists === true;
  const canGenerate = aiAvailable && resumeExists;

  // Read the canonical mutation state for rendering, not derived component
  // state. TanStack Query is the source of truth.
  const generatedProfile = generateProfile.data ?? null;
  const isGenerating = generateProfile.isPending;
  const generationError = generateProfile.error;

  const handleGenerate = () => {
    generateProfile.mutate(undefined, {
      onError: (err) => {
        const message = err instanceof Error ? err.message : '';
        if (
          !message.includes('400') &&
          !message.includes('503') &&
          !message.includes('No LLM') &&
          !message.includes('Upload a resume')
        ) {
          toast.error('Could not generate AI profile — using template summary instead.');
        }
      },
    });
  };

  if (!onboarding?.preferences) return null;

  const prefs = onboarding.preferences;
  const resumeFilename = onboarding.resume.exists ? onboarding.resume.filename : null;
  const searchAreaSummary = getSearchAreaSummary(
    prefs.workplace_preference,
    prefs.preferred_places,
    'onboarding',
  );

  // Merge a generated profile into the workspace preferences before
  // starting the search. The generated profile only overrides the
  // search-relevant fields (roles, keywords, etc.) — it doesn't touch
  // location preferences or compensation that the user already set
  // during the wizard.
  const buildPrefsFromGeneratedProfile = (gp: GeneratedProfile): WorkspacePreferences => {
    return {
      ...prefs,
      roles: gp.target_roles && gp.target_roles.length > 0 ? gp.target_roles : prefs.roles,
      keywords: gp.keywords.technical && gp.keywords.technical.length > 0
        ? gp.keywords.technical.slice(0, 12)
        : prefs.keywords,
      compensation: {
        ...prefs.compensation,
        min_base: gp.compensation.min_base || prefs.compensation.min_base,
        target_total_comp: gp.compensation.target_total_comp || prefs.compensation.target_total_comp,
      },
    };
  };

  const handleAcceptGenerated = () => {
    if (!generatedProfile) return;
    const merged = buildPrefsFromGeneratedProfile(generatedProfile);
    savePreferences.mutate(merged, {
      onSuccess: () => {
        toast.success(`Saved AI profile: ${generatedProfile.detected_archetype}`);
        // After saving, kick off the search with the merged prefs
        startOnboardingSearch.mutate(merged, {
          onSuccess: (result) => {
            const snapshot: SearchRunSnapshot = buildSearchRunSnapshot({
              profile: 'workspace',
              request: {
                mode: 'search_score',
                roles: merged.roles,
                locations: merged.preferred_places.map((place) => place.label),
                keywords: merged.keywords,
                companies: merged.companies,
                include_remote: merged.workplace_preference !== 'location_only',
                workplace_preference: merged.workplace_preference,
                max_days_old: merged.max_days_old,
                include_linkedin_jobs: merged.include_linkedin_jobs,
                use_ai: aiAvailable,
              },
              metadata: buildSearchSnapshotMetadataFromPreferences(merged),
            });
            activate(result.run_id, 'search_score', snapshot);
            try {
              window.localStorage.setItem('launchboard:first-run-pending', '1');
            } catch {
              // ignore
            }
            navigate({ to: '/search' });
          },
          onError: (err) =>
            toast.error(err instanceof Error ? err.message : 'Failed to start search'),
        });
      },
      onError: (err) =>
        toast.error(err instanceof Error ? err.message : 'Failed to save AI profile'),
    });
  };

  const handleStart = () => {
    startOnboardingSearch.mutate(prefs, {
      onSuccess: (result) => {
        const snapshot: SearchRunSnapshot = buildSearchRunSnapshot({
          profile: 'workspace',
          request: {
            mode: 'search_score',
            roles: prefs.roles,
            locations: prefs.preferred_places.map((place) => place.label),
            keywords: prefs.keywords,
            companies: prefs.companies,
            include_remote: prefs.workplace_preference !== 'location_only',
            workplace_preference: prefs.workplace_preference,
            max_days_old: prefs.max_days_old,
            include_linkedin_jobs: prefs.include_linkedin_jobs,
            use_ai: aiAvailable,
          },
          metadata: buildSearchSnapshotMetadataFromPreferences(prefs),
        });
        activate(result.run_id, 'search_score', snapshot);
        try {
          window.localStorage.setItem('launchboard:first-run-pending', '1');
        } catch {
          // localStorage may be disabled in some sandboxed shells; non-fatal.
        }
        toast.success(
          aiAvailable ? 'Starting your AI-ranked search…' : 'Starting your search…',
        );
        navigate({ to: '/search' });
      },
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : 'Failed to start search'),
    });
  };

  const isStarting = startOnboardingSearch.isPending;

  // Decide which view to show. Priority:
  //   1. AI-tailored card (if we have a profile AND user hasn't clicked
  //      "pick a template instead")
  //   2. Otherwise: manual summary (with a "Tailor with AI" button if
  //      AI is connected and a resume exists)
  // The loading state is rendered INSIDE the manual summary card during
  // generation so the user sees it as a contextual transition rather
  // than a full-page replacement.
  const showAiCard = view === 'ai' && generatedProfile != null;
  const showManualSummary = !showAiCard;

  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4">
      <div className="w-full max-w-2xl space-y-8">
        <div className="space-y-3 text-center">
          <h1 className="text-balance text-4xl font-semibold tracking-tight text-text-primary sm:text-5xl">
            You're ready to launch
          </h1>
          <p className="mx-auto max-w-md text-balance text-sm leading-relaxed text-text-tertiary sm:text-base">
            Review your search below. Click start when you're ready and we'll search 14+ job boards
            in the background.
          </p>
        </div>

        {/* AI-tailored profile card */}
        {showAiCard && generatedProfile && (
          <GeneratedProfileCard
            profile={generatedProfile}
            isLoading={savePreferences.isPending || startOnboardingSearch.isPending}
            onAccept={handleAcceptGenerated}
            onPickTemplate={() => setView('manual')}
          />
        )}

        {/* Setup summary — shown when AI is unavailable, generation failed,
            or the user explicitly clicked "pick a template instead" */}
        {showManualSummary && (
        <div className="space-y-3 rounded-2xl border border-border-default bg-bg-card p-5 shadow-sm">
          <SummaryRow
            icon={<FileText className="h-4 w-4 text-text-muted" />}
            label="Resume"
            value={resumeFilename ?? 'Not uploaded'}
            ok={!!resumeFilename}
          />
          <SummaryRow
            icon={<Tag className="h-4 w-4 text-text-muted" />}
            label="Target roles"
            value={prefs.roles.length > 0 ? prefs.roles.slice(0, 3).join(', ') + (prefs.roles.length > 3 ? ` +${prefs.roles.length - 3}` : '') : 'Will use resume'}
            ok={prefs.roles.length > 0 || !!resumeFilename}
          />
          <SummaryRow
            icon={<MapPin className="h-4 w-4 text-text-muted" />}
            label="Where"
            value={searchAreaSummary.shortLabel}
            ok={prefs.preferred_places.length > 0 || prefs.workplace_preference !== 'location_only'}
          />
          <SummaryRow
            icon={<Sparkles className="h-4 w-4 text-text-muted" />}
            label="AI ranking"
            value={aiAvailable ? (llm?.label ?? 'Connected') : 'Not connected (basic ranking)'}
            ok={aiAvailable}
            optional
          />
          {/* Offer to switch back to AI view if it succeeded but the user
              picked the template fallback */}
          {generatedProfile && view === 'manual' && (
            <button
              type="button"
              onClick={() => setView('ai')}
              className="mt-2 inline-flex items-center gap-1.5 text-xs text-brand transition-colors hover:text-brand-hover"
            >
              <Brain className="h-3.5 w-3.5" />
              Switch back to AI-tailored profile
            </button>
          )}
        </div>
        )}

        {/* Tailor with AI button — only show if we can call the endpoint
            (AI connected + resume uploaded), the user hasn't already
            generated a profile, and we're showing the manual summary.
            Inline loading state replaces the button while the LLM is
            mid-flight. Inline error message + retry on failure. */}
        {showManualSummary && canGenerate && !generatedProfile && (
          <div className="rounded-xl border border-brand/30 bg-brand-light/20 p-3.5">
            {isGenerating ? (
              <div className="flex items-start gap-3">
                <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-brand" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary">
                    Tailoring a profile from your resume…
                  </p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-text-tertiary">
                    Reading your background and matching it to the right job sources, keywords,
                    and weights for your specific career. Takes 5–15 seconds.
                  </p>
                </div>
              </div>
            ) : generationError ? (
              <div className="space-y-2">
                <div className="flex items-start gap-3">
                  <Brain className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-text-primary">
                      AI couldn't generate a profile
                    </p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-text-tertiary">
                      {generationError instanceof Error ? generationError.message : 'Unknown error'}
                    </p>
                  </div>
                </div>
                <Button variant="outline" size="sm" onClick={handleGenerate} className="w-full">
                  Try again
                </Button>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <Brain className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary">
                    Get an AI-tailored profile from your resume
                  </p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-text-tertiary">
                    Skips the templates entirely. Reads your resume and produces a profile specifically for
                    your career — works for any niche (AI/ML, web3, healthcare, government, climate tech, etc.).
                  </p>
                  <Button
                    size="sm"
                    onClick={handleGenerate}
                    className="mt-2"
                  >
                    Tailor my profile with AI
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Primary CTA — hidden when the AI card is showing (it has its
            own primary button) */}
        <div className="space-y-3">
          {!showAiCard && (
            <Button
              onClick={handleStart}
              disabled={isStarting}
              className="h-12 w-full text-base"
              size="lg"
            >
              {isStarting ? (
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              ) : null}
              Start your first search
              {!isStarting && <ArrowRight className="ml-2 h-5 w-5" />}
            </Button>
          )}

          <div className="flex items-center justify-center gap-4 text-xs">
            <button
              type="button"
              onClick={() => navigate({ to: '/settings', search: { tab: 'search' } })}
              className="inline-flex items-center gap-1.5 text-text-muted transition-colors hover:text-text-secondary"
            >
              <SettingsIcon className="h-3.5 w-3.5" />
              Edit search settings
            </button>
            {!aiAvailable && (
              <>
                <span className="text-border-default">·</span>
                <ConnectAiPopover side="bottom" align="center">
                  <button
                    type="button"
                    className="inline-flex items-center gap-1.5 text-text-muted transition-colors hover:text-text-secondary"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Connect AI for better ranking
                  </button>
                </ConnectAiPopover>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface SummaryRowProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  ok: boolean;
  optional?: boolean;
}

function SummaryRow({ icon, label, value, ok, optional }: SummaryRowProps) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-bg-subtle">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">{label}</p>
        <p className="truncate text-sm text-text-secondary">{value}</p>
      </div>
      {ok ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
      ) : optional ? (
        <span className="text-[10px] font-medium uppercase tracking-wide text-text-muted">Optional</span>
      ) : null}
    </div>
  );
}
