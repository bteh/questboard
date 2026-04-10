import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  Loader2,
  Shield,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';

import { SimpleLocationInput } from '@/components/onboarding/simple-location-input';
import { TagListInput } from '@/components/shared/tag-list-input';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { useSuggestSearch } from '@/hooks/use-search';
import {
  useOnboardingState,
  useSaveWorkspacePreferences,
  useUploadWorkspaceResume,
} from '@/hooks/use-workspace';
import { useLLMStatus } from '@/hooks/use-settings';
import {
  buildDefaultWorkspacePreferences,
  createManualPlace,
  normalizePlaceList,
} from '@/lib/profile-preferences';
import { getSearchReadiness } from '@/lib/search-readiness';
import { cn } from '@/lib/utils';
import type { WorkspacePreferences } from '@/types/workspace';
import { toast } from 'sonner';

type Step = 'resume' | 'search';

const STEPS: Step[] = ['resume', 'search'];

interface OnboardingWizardProps {
  open: boolean;
  /** Fired when the user finishes the wizard by clicking Save and continue. */
  onComplete: () => void;
  /**
   * Fired when the user dismisses the wizard without finishing it — the X
   * button in the corner, or (if you want to) any of the "Skip" affordances.
   * This is how we keep non-technical users from getting trapped: closing
   * the wizard once sticks across reloads via useOnboarding's localStorage
   * flag. Defaults to onComplete for backwards compatibility with callers
   * that don't care about the distinction.
   */
  onDismiss?: () => void;
}

/**
 * Two-step first-run onboarding for the desktop app.
 *
 * Step 1 — Upload Your Resume: drop target + skip path
 * Step 2 — What are you looking for?: roles + locations only, then GO
 *
 * Everything else (AI provider, salary, posted-within window, LinkedIn,
 * companies, etc.) is intentionally NOT here. The desktop-first plan in
 * docs/desktop-first.md says optimize for download → open → upload resume →
 * run first search before anything else, so we ship the user to results
 * fast and let them tune from the in-app Search and Settings pages.
 *
 * Test IDs preserved for the Playwright smoke harness:
 *   onboarding-resume-input, onboarding-roles-input, onboarding-save-search.
 */
export function OnboardingWizard({ open, onComplete, onDismiss }: OnboardingWizardProps) {
  const handleDismiss = onDismiss ?? onComplete;
  const navigate = useNavigate();
  const { data } = useOnboardingState(open);
  const uploadResume = useUploadWorkspaceResume();
  const savePreferences = useSaveWorkspacePreferences();
  const suggestSearch = useSuggestSearch();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const serverForm = useMemo(
    () => data?.preferences ?? buildDefaultWorkspacePreferences(),
    [data?.preferences],
  );
  const [formDraft, setFormDraft] = useState<WorkspacePreferences | null>(null);
  const form = formDraft ?? serverForm;
  const setForm = useCallback(
    (next: WorkspacePreferences | ((prev: WorkspacePreferences) => WorkspacePreferences)) => {
      setFormDraft((prev) => {
        const base = prev ?? serverForm;
        return typeof next === 'function' ? next(base) : next;
      });
    },
    [serverForm],
  );

  const { data: llm } = useLLMStatus();
  const aiAvailable = llm?.available ?? false;
  const resumeUploaded = data?.resume.exists === true;
  const prefilledFromResume = form.roles.length > 0;
  const [aiFailed, setAiFailed] = useState(false);

  // Skip directly to step 2 if a resume is already on disk when the wizard
  // mounts (e.g. after a restart mid-flow). Live transitions after a fresh
  // upload happen inside `handleFileUpload`, not here.
  const [step, setStep] = useState<Step>(resumeUploaded ? 'search' : 'resume');

  // When the wizard opens with a resume already on disk but no roles
  // pre-filled (e.g. user reset, or uploaded before but didn't finish),
  // fire the AI suggest to populate roles/keywords/locations/companies.
  const suggestFiredRef = useRef(false);
  useEffect(() => {
    if (
      open &&
      resumeUploaded &&
      aiAvailable &&
      !prefilledFromResume &&
      !suggestSearch.isPending &&
      !suggestFiredRef.current
    ) {
      suggestFiredRef.current = true;
      suggestSearch.mutate('workspace', {
        onSuccess: (suggestion) => {
          if (suggestion.ai_failed) setAiFailed(true);
          setForm((prev) => {
            const suggestedPlaces =
              suggestion.locations.length > 0 && prev.preferred_places.length === 0
                ? normalizePlaceList(suggestion.locations.map(createManualPlace))
                : prev.preferred_places;
            return {
              ...prev,
              roles: prev.roles.length > 0 ? prev.roles : suggestion.roles,
              keywords: prev.keywords.length > 0 ? prev.keywords : suggestion.keywords,
              companies: prev.companies.length > 0 ? prev.companies : suggestion.companies,
              preferred_places: suggestedPlaces,
            };
          });
        },
      });
    }
  }, [open, resumeUploaded, aiAvailable, prefilledFromResume, suggestSearch, setForm]);

  const searchReadiness = getSearchReadiness({
    roles: form.roles,
    keywords: form.keywords,
    locations: form.preferred_places,
    workplacePreference: form.workplace_preference,
    allowResumeFallback: resumeUploaded,
  });

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    uploadResume.mutate(file, {
      onSuccess: (result) => {
        toast.success(
          result.resume.parse_status === 'parsed'
            ? 'Resume uploaded'
            : 'Resume uploaded with warnings',
        );
        if (result.analysis) {
          const roles = (result.analysis.suggested_target_roles as string[] | undefined)?.slice(0, 5) ?? [];
          const keywords = (result.analysis.suggested_keywords as string[] | undefined)?.slice(0, 8) ?? [];
          const title = (result.analysis.current_title as string) ?? '';
          const level = (result.analysis.seniority as string) ?? '';
          setForm((prev) => ({
            ...prev,
            roles: roles.length > 0 ? roles : prev.roles,
            keywords: keywords.length > 0 ? keywords : prev.keywords,
            current_title: title || prev.current_title,
            current_level: level || prev.current_level,
          }));
        }
        setStep('search');

        // Fire a background AI suggest if AI is connected — fills companies
        // and reinforces roles/keywords without blocking the user.
        if (llm?.available) {
          suggestSearch.mutate('workspace', {
            onSuccess: (suggestion) => {
              if (suggestion.ai_failed) setAiFailed(true);
              setForm((prev) => {
                // Convert location strings from the LLM into PlaceSelection
                // objects so the location chips render immediately.
                const suggestedPlaces =
                  suggestion.locations.length > 0 && prev.preferred_places.length === 0
                    ? normalizePlaceList(suggestion.locations.map(createManualPlace))
                    : prev.preferred_places;

                return {
                  ...prev,
                  roles: prev.roles.length > 0 ? prev.roles : suggestion.roles,
                  keywords: prev.keywords.length > 0 ? prev.keywords : suggestion.keywords,
                  companies: prev.companies.length > 0 ? prev.companies : suggestion.companies,
                  preferred_places: suggestedPlaces,
                };
              });
            },
          });
        }
      },
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : 'Upload failed');
      },
    });
  };

  const handleSave = () => {
    if (searchReadiness.missingSearchTerms) {
      toast.error('Add at least one target role, or upload a resume.');
      return;
    }
    if (searchReadiness.missingLocations) {
      toast.error('Add a preferred location, or turn remote back on.');
      return;
    }

    // Save preferences only — DO NOT auto-fire a search. The dashboard's
    // "Ready to launch" hero owns the moment of clicking Start so the user
    // never feels rushed past their settings.
    savePreferences.mutate(form, {
      onSuccess: () => {
        try {
          window.localStorage.setItem('launchboard:onboarding-complete', '1');
        } catch {
          // localStorage may be disabled in some sandboxed shells; non-fatal.
        }
        toast.success('Preferences saved. Review and start your search when ready.');
        onComplete();
        navigate({ to: '/' });
      },
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : 'Failed to save preferences'),
    });
  };

  const isUploading = uploadResume.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) handleDismiss(); }}>
      <DialogContent showCloseButton={false} className="sm:max-w-xl p-0 overflow-hidden">
        {/* Close button — positioned absolutely so it doesn't fight the
            step indicator for layout space. Dismissing via this button
            persists to localStorage so the wizard stays closed on reload. */}
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Close onboarding"
          className="absolute right-3 top-3 z-10 flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-bg-subtle hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg-card"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Step indicator — minimal, two dots */}
        <div className="flex justify-center gap-1.5 pt-5">
          {STEPS.map((value) => (
            <div
              key={value}
              className={cn(
                'h-1.5 rounded-full transition-all',
                step === value ? 'w-8 bg-brand' : 'w-2 bg-border-default',
              )}
            />
          ))}
        </div>

        <div className="px-6 pb-6 pt-4">
          {/* ──────────────────────────────────────────────────────────
              Step 1 — Upload Your Resume
              Heading text "Upload Your Resume" is referenced by the
              Playwright smoke test, do not rename without updating
              frontend/scripts/run-desktop-smoke.mjs.
          ────────────────────────────────────────────────────────── */}
          {step === 'resume' && (
            <div className="space-y-6">
              <div className="space-y-3 text-center">
                <h2 className="text-2xl font-semibold tracking-tight text-text-primary">
                  Upload Your Resume
                </h2>
                <p className="mx-auto max-w-md text-sm leading-relaxed text-text-tertiary">
                  Upload your resume{' '}
                  <ArrowRight className="inline h-3 w-3 -mt-0.5 opacity-50" /> we suggest roles{' '}
                  <ArrowRight className="inline h-3 w-3 -mt-0.5 opacity-50" /> we search 14+ job boards{' '}
                  <ArrowRight className="inline h-3 w-3 -mt-0.5 opacity-50" />{' '}
                  <span className="font-medium text-text-secondary">you see your best matches</span>.
                </p>
              </div>

              {resumeUploaded ? (
                <div className="rounded-xl border border-success/20 bg-success/5 p-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10">
                      <FileText className="h-5 w-5 text-red-500" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-text-primary">{data?.resume.filename}</p>
                      <p className="text-xs text-text-muted">
                        {data?.resume.file_size
                          ? `${Math.max(1, Math.round(data.resume.file_size / 1024))} KB`
                          : 'PDF'}
                      </p>
                    </div>
                    <CheckCircle2 className="h-5 w-5 text-success" />
                  </div>
                  {data?.resume.parse_warning && (
                    <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">
                      {data.resume.parse_warning}
                    </p>
                  )}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                  className={cn(
                    'group relative w-full rounded-2xl border border-dashed border-border-default bg-bg-card/50 p-10 text-center transition-all',
                    'hover:border-brand/40 hover:bg-brand-light/20 hover:shadow-sm',
                    'disabled:cursor-not-allowed disabled:opacity-60',
                  )}
                >
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-border-default/60 bg-bg-subtle shadow-sm transition-all group-hover:border-brand/30 group-hover:bg-bg-card group-hover:scale-[1.03]">
                    {isUploading ? (
                      <Loader2 className="h-6 w-6 animate-spin text-brand" />
                    ) : (
                      <Upload className="h-6 w-6 text-text-muted transition-colors group-hover:text-brand" />
                    )}
                  </div>
                  <p className="text-base font-medium text-text-primary group-hover:text-brand transition-colors">
                    {isUploading ? 'Uploading…' : 'Drop or click to upload PDF resume'}
                  </p>
                  <p className="mt-1 text-xs text-text-muted">PDF up to 10MB</p>
                </button>
              )}

              <div className="flex items-center justify-center gap-2 text-xs text-text-muted">
                <Shield className="h-3.5 w-3.5" />
                <span>Your resume and AI keys stay on this computer. No account required.</span>
              </div>

              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={() => setStep('search')}
                  className="flex-1"
                >
                  Skip — search by keywords
                </Button>
                <Button
                  onClick={() => setStep('search')}
                  disabled={!resumeUploaded || isUploading}
                  className="flex-1"
                >
                  Continue <ArrowRight className="ml-1 h-4 w-4" />
                </Button>
              </div>
            </div>
          )}

          {/* ──────────────────────────────────────────────────────────
              Step 2 — What are you looking for?
              Heading text "What are you looking for?" is referenced by
              the Playwright smoke test, do not rename without updating
              frontend/scripts/run-desktop-smoke.mjs.
          ────────────────────────────────────────────────────────── */}
          {step === 'search' && (
            <div className="space-y-5">
              <div className="space-y-2 text-center">
                <h2 className="text-2xl font-semibold tracking-tight text-text-primary">
                  What are you looking for?
                </h2>
                <p className="mx-auto max-w-md text-sm leading-relaxed text-text-tertiary">
                  {prefilledFromResume
                    ? 'We pulled these from your resume. Tweak anything below, then start your first search.'
                    : resumeUploaded
                      ? 'Your resume is uploaded. Add a role to focus the search, or skip and let us read it.'
                      : "Tell us a target role and where. You can fine-tune everything later in Settings."}
                </p>
              </div>

              <div className="space-y-4 text-left">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-text-primary">Target roles</label>
                    {prefilledFromResume && form.roles.length > 0 && (
                      <span className="rounded-full bg-brand-light px-2 py-0.5 text-[10px] font-medium text-brand">
                        From resume
                      </span>
                    )}
                  </div>
                  <TagListInput
                    value={form.roles}
                    onChange={(roles) => setForm((prev) => ({ ...prev, roles }))}
                    placeholder="e.g. Nurse Practitioner — press Enter to add"
                    helperText="Type a role and press Enter."
                    emptyText="No roles added yet."
                    inputProps={{ 'data-testid': 'onboarding-roles-input' }}
                  />
                </div>

                <SimpleLocationInput
                  preferredPlaces={form.preferred_places}
                  onPreferredPlacesChange={(preferred_places) =>
                    setForm((prev) => ({ ...prev, preferred_places }))
                  }
                  workplacePreference={form.workplace_preference}
                  onWorkplacePreferenceChange={(workplace_preference) =>
                    setForm((prev) => ({ ...prev, workplace_preference }))
                  }
                />
              </div>

              {aiFailed && aiAvailable && (
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
                  <div className="flex items-start gap-2.5">
                    <Sparkles className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-medium text-text-secondary">
                        AI couldn't analyze your resume
                      </p>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-text-muted">
                        Your AI provider is configured but not responding. Check your API key in{' '}
                        <button
                          type="button"
                          onClick={() => { handleDismiss(); navigate({ to: '/settings', search: { tab: 'ai' } }); }}
                          className="font-medium text-brand hover:underline"
                        >
                          Settings → AI
                        </button>
                        . You can still search — results will use basic keyword matching instead of
                        AI-powered 7-dimension scoring.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {!aiAvailable && (
                <div className="rounded-xl border border-border-default bg-bg-subtle/50 p-3">
                  <div className="flex items-start gap-2.5">
                    <Sparkles className="h-4 w-4 text-text-muted shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-medium text-text-secondary">
                        Searching now without AI
                      </p>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-text-muted">
                        You'll get keyword-based ranking. Connect AI later from the sidebar to
                        unlock resume-fit scoring and tailored drafts — takes about 30 seconds with a free Gemini key.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep('resume')} className="flex-1">
                  Back
                </Button>
                <Button
                  data-testid="onboarding-save-search"
                  onClick={handleSave}
                  disabled={savePreferences.isPending}
                  className="flex-1"
                >
                  {savePreferences.isPending ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <ArrowRight className="mr-1 h-4 w-4" />
                  )}
                  Save and continue
                </Button>
              </div>
              {resumeUploaded && form.roles.length === 0 && form.keywords.length === 0 && (
                <p className="text-center text-[11px] text-text-muted">
                  No roles entered. Launchboard will derive them from your resume for this first run.
                </p>
              )}
            </div>
          )}
        </div>

        <input
          ref={fileInputRef}
          data-testid="onboarding-resume-input"
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={handleFileUpload}
        />
      </DialogContent>
    </Dialog>
  );
}
