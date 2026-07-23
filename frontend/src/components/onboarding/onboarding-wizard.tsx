import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  Loader2,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';

import { SimpleLocationInput } from '@/components/onboarding/simple-location-input';
import { ResumeAnalysisBanner } from '@/components/shared/resume-analysis-banner';
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
import { markFirstRunPending } from '@/components/onboarding/first-run';
import { normalizeWorkspaceUpload, type NormalizedResumeUpload } from '@/lib/resume-analysis';
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
   * Fired when the user dismisses the wizard without finishing it: the X
   * button in the corner, or any of the "Skip" affordances. Defaults to
   * onComplete for callers that don't care about the distinction.
   */
  onDismiss?: () => void;
}

/**
 * Two-step first-run onboarding for the desktop app.
 *
 * Step 1, Upload Your Resume: drop target + skip path
 * Step 2, What are you looking for?: roles + locations only, then GO
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
  // Outcome of the most recent upload; drives the scanned-PDF / no-AI banner.
  const [uploadNotice, setUploadNotice] = useState<NormalizedResumeUpload | null>(null);

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
        const normalized = normalizeWorkspaceUpload(result);
        setUploadNotice(normalized);
        if (normalized.parseCode === 'SCANNED_PDF') {
          // Stay on the resume step: the banner explains how to fix the file,
          // and the skip path is still available for keyword-only searching.
          toast.error('Resume saved, but no text could be read from it');
          return;
        }
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

        // Fire a background AI suggest if AI is connected; fills companies
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
        toast.error(error instanceof Error ? error.message : 'The upload did not finish. Try again.');
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

    // Save preferences only, DO NOT auto-fire a search. The dashboard's
    // "Ready to launch" hero owns the moment of clicking Start so the user
    // never feels rushed past their settings.
    savePreferences.mutate(form, {
      onSuccess: () => {
        // The board's Find work lane consumes this flag on mount and pulls
        // the first jobs once, so the new user lands on a lane that fills in.
        markFirstRunPending();
        toast.success('Preferences saved. Start your search when ready.');
        onComplete();
        navigate({ to: '/board', search: { v: 'work' } });
      },
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : 'Could not save preferences. Try again.'),
    });
  };

  const isUploading = uploadResume.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) handleDismiss(); }}>
      <DialogContent showCloseButton={false} className="sm:max-w-xl p-0 overflow-hidden">
        {/* Close button, positioned absolutely so it doesn't fight the
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

        {/* Step indicator: minimal, two dots */}
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
              Step 1: Upload Your Resume
              Heading text "Upload Your Resume" is referenced by the
              Playwright smoke test, do not rename without updating
              frontend/scripts/run-desktop-smoke.mjs.
          ────────────────────────────────────────────────────────── */}
          {step === 'resume' && (
            <div className="space-y-6">
              <div className="text-center">
                <h2 className="text-2xl font-semibold tracking-tight text-text-primary">
                  Upload your resume
                </h2>
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
                  {data?.resume.parse_warning && !uploadNotice && (
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

              {uploadNotice && <ResumeAnalysisBanner upload={uploadNotice} />}

              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={() => setStep('search')}
                  className="flex-1"
                >
                  Skip and search by keywords
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
              Step 2: What are you looking for?
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
                    ? 'We pulled these from your resume. Change anything that looks off.'
                    : resumeUploaded
                      ? 'Add a role to focus the search. Blank searches from your resume alone.'
                      : 'Add a target role and a place to search. Fine-tune later in Settings.'}
                </p>
              </div>

              {uploadNotice && <ResumeAnalysisBanner upload={uploadNotice} className="text-left" />}

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
                    placeholder="e.g. Nurse Practitioner, then press Enter"
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

              {(aiFailed && aiAvailable) || !aiAvailable ? (
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  <Sparkles className="h-3.5 w-3.5 shrink-0" />
                  <span>
                    {aiFailed ? 'Your AI key is offline, ranking by keywords. ' : 'Ranking by keywords. '}
                    Your connected assistant can rank by resume fit.
                  </span>
                </div>
              ) : null}

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
                  No roles entered. Questboard reads them from your resume for this first run.
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
