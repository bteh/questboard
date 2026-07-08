import { useRef, useState } from 'react';
import type { useNavigate } from '@tanstack/react-router';
import { FileText, Loader2, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { OnboardingWizard } from '@/components/onboarding/onboarding-wizard';
import { ResumeAnalysisPanel } from '@/components/settings/resume-analysis-panel';
import { ResumeAnalysisBanner } from '@/components/shared/resume-analysis-banner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useUploadWorkspaceResume } from '@/hooks/use-workspace';
import { normalizeWorkspaceUpload, type NormalizedResumeUpload } from '@/lib/resume-analysis';
import { buildDefaultWorkspacePreferences } from '@/lib/profile-preferences';
import type { OnboardingState } from '@/types/workspace';

interface ResumeTabProps {
  onboarding: OnboardingState | undefined;
  navigate: ReturnType<typeof useNavigate>;
}

export function ResumeTab({ onboarding, navigate }: ResumeTabProps) {
  const uploadResume = useUploadWorkspaceResume();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [lastUpload, setLastUpload] = useState<NormalizedResumeUpload | null>(null);
  // Re-mounts the analysis panel with fresh chip state on every new upload.
  const [uploadCount, setUploadCount] = useState(0);
  // The guided wizard's one remaining door: it opens right here, no bounce.
  const [wizardOpen, setWizardOpen] = useState(false);

  const handleUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    uploadResume.mutate(file, {
      onSuccess: (result) => {
        const normalized = normalizeWorkspaceUpload(result);
        setLastUpload(normalized);
        setUploadCount((count) => count + 1);
        if (normalized.parseCode === 'SCANNED_PDF') {
          toast.error('Resume saved, but no text could be read from it');
        } else if (normalized.analysisStatus === 'completed') {
          toast.success('Resume uploaded and analyzed');
        } else if (normalized.analysisStatus === 'analysis_error') {
          toast.warning('Resume saved. The AI step didn’t finish, so no skills yet. Try again in a moment.');
        } else if (normalized.analysisStatus === 'failed') {
          toast.warning('Resume saved, but we couldn’t read any text from it');
        } else {
          toast.success('Resume uploaded');
        }
      },
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Upload failed'),
    });
    // Allow re-selecting the same file after a failed/scanned upload.
    event.target.value = '';
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4" />
          Resume
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-xl border border-border-default bg-bg-subtle/40 p-4">
          {onboarding?.resume.exists ? (
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10">
                <FileText className="h-5 w-5 text-red-500" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text-primary">{onboarding.resume.filename}</p>
                <p className="text-xs text-text-muted">
                  {Math.max(1, Math.round(onboarding.resume.file_size / 1024))} KB, {onboarding.resume.parse_status}
                </p>
                {onboarding.resume.parse_warning && !lastUpload && (
                  <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">{onboarding.resume.parse_warning}</p>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-text-tertiary">No resume uploaded yet. Upload one to unlock resume-matched scoring.</p>
          )}
        </div>

        {lastUpload && (
          <ResumeAnalysisBanner
            upload={lastUpload}
            action={
              lastUpload.analysisStatus === 'skipped_no_llm' ? (
                <button
                  type="button"
                  onClick={() => navigate({ to: '/settings', search: { tab: 'ai' } })}
                  className="font-medium underline underline-offset-2"
                >
                  Connect an AI provider
                </button>
              ) : lastUpload.analysisStatus === 'analysis_error' ? (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="font-medium underline underline-offset-2"
                >
                  Try again
                </button>
              ) : undefined
            }
          />
        )}

        {lastUpload?.analysisStatus === 'completed' && lastUpload.analysis && (
          <ResumeAnalysisPanel
            key={uploadCount}
            analysis={lastUpload.analysis}
            preferences={onboarding?.preferences ?? buildDefaultWorkspacePreferences()}
          />
        )}

        <Button variant="outline" onClick={() => fileInputRef.current?.click()} disabled={uploadResume.isPending}>
          {uploadResume.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
          {onboarding?.resume.exists ? 'Replace resume' : 'Upload resume PDF'}
        </Button>
        <input ref={fileInputRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={handleUpload} />

        {/* The guided setup's quiet recovery door: with the old dashboard
            heroes gone, this is where the wizard lives, opened in place. */}
        <div className="border-t border-border-default pt-3">
          <button
            type="button"
            onClick={() => setWizardOpen(true)}
            className="text-xs text-text-muted transition-colors hover:text-text-secondary"
          >
            Restart guided setup
          </button>
        </div>

        <OnboardingWizard
          open={wizardOpen}
          onComplete={() => setWizardOpen(false)}
          onDismiss={() => setWizardOpen(false)}
        />
      </CardContent>
    </Card>
  );
}
