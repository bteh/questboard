import { useRef } from 'react';
import type { useNavigate } from '@tanstack/react-router';
import { FileText, Loader2, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useUploadWorkspaceResume } from '@/hooks/use-workspace';
import type { OnboardingState } from '@/types/workspace';

interface ResumeTabProps {
  onboarding: OnboardingState | undefined;
  navigate: ReturnType<typeof useNavigate>;
  markOnboardingIncomplete: () => void;
}

export function ResumeTab({ onboarding, navigate, markOnboardingIncomplete }: ResumeTabProps) {
  const uploadResume = useUploadWorkspaceResume();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleRestartOnboarding = () => {
    markOnboardingIncomplete();
    toast.success('Onboarding will re-open on the next page load.');
    // Bounce to dashboard so the gate has a chance to re-render the wizard.
    navigate({ to: '/' });
  };

  const handleUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    uploadResume.mutate(file, {
      onSuccess: (result) => {
        toast.success(result.resume.parse_status === 'parsed' ? 'Resume uploaded' : 'Resume uploaded with warnings');
      },
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Upload failed'),
    });
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
                  {Math.max(1, Math.round(onboarding.resume.file_size / 1024))} KB · {onboarding.resume.parse_status}
                </p>
                {onboarding.resume.parse_warning && (
                  <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">{onboarding.resume.parse_warning}</p>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-text-tertiary">No resume uploaded yet. Upload one to unlock resume-matched scoring.</p>
          )}
        </div>

        <Button variant="outline" onClick={() => fileInputRef.current?.click()} disabled={uploadResume.isPending}>
          {uploadResume.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
          {onboarding?.resume.exists ? 'Replace resume' : 'Upload resume PDF'}
        </Button>
        <input ref={fileInputRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={handleUpload} />

        {/* First-run helpers — small, unobtrusive recovery affordance for
            users who dismissed the wizard and want to see it again. */}
        <div className="border-t border-border-default pt-3">
          <button
            type="button"
            onClick={handleRestartOnboarding}
            className="text-xs text-text-muted transition-colors hover:text-text-secondary"
          >
            Restart the first-run walkthrough
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
