import { useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { ArrowRight, FileText, Loader2, Search, Shield, Sparkles, Upload } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { OnboardingWizard } from '@/components/onboarding/onboarding-wizard';
import { useOnboardingState, useStartOnboardingSearch, useUploadWorkspaceResume } from '@/hooks/use-workspace';
import { useSearchContext } from '@/contexts/search-context';
import {
  buildSearchRunSnapshot,
  buildSearchSnapshotMetadataFromPreferences,
} from '@/lib/search-preferences';
import { cn } from '@/lib/utils';
import type { SearchRunSnapshot } from '@/types/search';
import { toast } from 'sonner';

/**
 * Empty-state hero shown on the Dashboard route when a brand-new user has
 * not started any search yet. The wizard usually covers this on first run,
 * but if the user dismisses the wizard without finishing, the dashboard
 * would otherwise look like a vacant stat cockpit.
 *
 * The visual reference for this component is .aidesigner/first-run-hero.html.
 */
export function FirstRunHero() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [jobTitle, setJobTitle] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);

  const { data } = useOnboardingState();
  const uploadResume = useUploadWorkspaceResume();
  const startOnboardingSearch = useStartOnboardingSearch();
  const { activate } = useSearchContext();

  const resumeUploaded = data?.resume.exists === true;
  const isUploading = uploadResume.isPending;
  const isStartingQuickSearch = startOnboardingSearch.isPending;

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (file.type !== 'application/pdf' && !file.name.endsWith('.pdf')) {
      toast.error('Please drop a PDF file.');
      return;
    }
    uploadResume.mutate(file, {
      onSuccess: (result) => {
        toast.success(
          result.resume.parse_status === 'parsed'
            ? 'Resume uploaded — pick your search settings next'
            : 'Resume uploaded with warnings',
        );
        navigate({ to: '/search' });
      },
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : 'Upload failed');
      },
    });
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    uploadResume.mutate(file, {
      onSuccess: (result) => {
        toast.success(
          result.resume.parse_status === 'parsed'
            ? 'Resume uploaded — pick your search settings next'
            : 'Resume uploaded with warnings',
        );
        // Bounce the user into the search page so they can review the
        // resume-derived suggestions before kicking off a run.
        navigate({ to: '/search' });
      },
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : 'Upload failed');
      },
    });
  };

  const handleQuickSearch = () => {
    const trimmed = jobTitle.trim();
    if (!trimmed) {
      toast.error('Type a job title to try Launchboard.');
      return;
    }
    if (!data?.preferences) {
      toast.error('Workspace is still loading — try again in a moment.');
      return;
    }
    const preferences = {
      ...data.preferences,
      roles: [trimmed],
    };
    startOnboardingSearch.mutate(preferences, {
      onSuccess: (result) => {
        const snapshot: SearchRunSnapshot = buildSearchRunSnapshot({
          profile: 'workspace',
          request: {
            mode: 'search_score',
            roles: preferences.roles,
            locations: preferences.preferred_places.map((p) => p.label),
            keywords: preferences.keywords,
            companies: preferences.companies,
            include_remote: preferences.workplace_preference !== 'location_only',
            workplace_preference: preferences.workplace_preference,
            max_days_old: preferences.max_days_old,
            include_linkedin_jobs: preferences.include_linkedin_jobs,
            use_ai: false,
          },
          metadata: buildSearchSnapshotMetadataFromPreferences(preferences),
        });
        activate(result.run_id, 'search_score', snapshot);
        try {
          window.localStorage.setItem('launchboard:first-run-pending', '1');
        } catch {
          // localStorage may be unavailable in sandboxed shells; non-fatal.
        }
        navigate({ to: '/search' });
      },
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : 'Failed to start search');
      },
    });
  };

  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4">
      <div className="w-full max-w-2xl space-y-10">
        {/* Headline */}
        <div className="space-y-4 text-center">
          <h1 className="text-balance text-4xl font-semibold tracking-tight text-text-primary sm:text-5xl">
            Let's start your job search
          </h1>
          <p className="mx-auto max-w-lg text-balance text-sm leading-relaxed text-text-tertiary sm:text-base">
            <span>Upload your resume</span>{' '}
            <ArrowRight className="inline h-3 w-3 -mt-0.5 opacity-50" />{' '}
            <span>we suggest roles</span>{' '}
            <ArrowRight className="inline h-3 w-3 -mt-0.5 opacity-50" />{' '}
            <span>we search 14+ job boards</span>{' '}
            <ArrowRight className="inline h-3 w-3 -mt-0.5 opacity-50" />{' '}
            <span className="font-medium text-text-secondary">you see your best matches</span>
          </p>
        </div>

        {/* Primary CTA — drag-and-drop resume upload */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={cn(
            'group relative w-full rounded-2xl border-2 border-dashed bg-bg-card/60 p-10 text-center shadow-sm transition-all',
            isDragging
              ? 'border-brand bg-brand-light/30 shadow-md scale-[1.01]'
              : 'border-border-default hover:border-brand/40 hover:bg-brand-light/20 hover:shadow-md',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg-page',
            'disabled:cursor-not-allowed disabled:opacity-60',
          )}
        >
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-border-default/60 bg-bg-subtle shadow-sm transition-all group-hover:scale-[1.03] group-hover:border-brand/30 group-hover:bg-bg-card">
            {isUploading ? (
              <Loader2 className="h-6 w-6 animate-spin text-brand" />
            ) : resumeUploaded ? (
              <FileText className="h-6 w-6 text-brand" />
            ) : (
              <Upload className="h-6 w-6 text-text-muted transition-colors group-hover:text-brand" />
            )}
          </div>
          <p className="text-lg font-medium text-text-primary transition-colors group-hover:text-brand">
            {isUploading
              ? 'Uploading…'
              : resumeUploaded
                ? 'Replace your saved resume'
                : 'Drop or click to upload PDF resume'}
          </p>
          <p className="mt-1.5 text-xs text-text-muted">PDF up to 10MB</p>
        </button>

        {/* Fallback — quick keyword search */}
        <div className="space-y-3">
          <p className="text-center text-sm text-text-muted">
            or skip the resume — type a job title to try Launchboard first
          </p>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <Input
                value={jobTitle}
                onChange={(event) => setJobTitle(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') handleQuickSearch();
                }}
                placeholder="e.g. Senior Frontend Engineer"
                className="h-11 pl-9"
                disabled={isStartingQuickSearch}
              />
            </div>
            <Button
              onClick={handleQuickSearch}
              disabled={isStartingQuickSearch || !jobTitle.trim()}
              className="h-11 px-5"
            >
              {isStartingQuickSearch ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Search
                  <ArrowRight className="ml-1 h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Reassurance + guided setup link */}
        <div className="flex flex-col items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <Shield className="h-3.5 w-3.5" />
            <span>Your resume and AI keys stay on this computer. No account required.</span>
          </div>
          <button
            type="button"
            onClick={() => setWizardOpen(true)}
            className="inline-flex items-center gap-1.5 text-xs text-text-muted transition-colors hover:text-text-secondary"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Prefer a guided setup? Open the wizard
          </button>
        </div>

        {resumeUploaded && (
          <div className="text-center">
            <button
              type="button"
              onClick={() => navigate({ to: '/search' })}
              className="inline-flex items-center gap-1.5 text-sm text-text-muted transition-colors hover:text-text-secondary"
            >
              You already have <span className="font-medium text-text-secondary">{data?.resume.filename}</span> saved — open it
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={handleFileUpload}
      />

      {/* Optional guided wizard — accessible but not forced */}
      <OnboardingWizard
        open={wizardOpen}
        onComplete={() => setWizardOpen(false)}
        onDismiss={() => setWizardOpen(false)}
      />
    </div>
  );
}
