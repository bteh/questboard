import { AlertTriangle, ListChecks, RefreshCw, ScanLine } from 'lucide-react';

import type { NormalizedResumeUpload } from '@/lib/resume-analysis';
import { cn } from '@/lib/utils';

interface ResumeAnalysisBannerProps {
  upload: NormalizedResumeUpload;
  /** Optional CTA (e.g. a link to the AI provider settings tab). */
  action?: React.ReactNode;
  className?: string;
}

/**
 * Status banner for a resume upload outcome. Renders nothing when the
 * analysis completed. The extracted-data panel is the success state.
 *
 * Shared between the Settings resume tab and the onboarding wizard so the
 * user sees the same explanation in both places.
 */
export function ResumeAnalysisBanner({ upload, action, className }: ResumeAnalysisBannerProps) {
  if (upload.analysisStatus === 'completed') return null;

  if (upload.parseCode === 'SCANNED_PDF') {
    return (
      <div
        role="alert"
        className={cn(
          'flex items-start gap-2.5 rounded-lg border border-red-300 bg-red-50 p-3 text-xs leading-relaxed text-red-900 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200',
          className,
        )}
      >
        <ScanLine className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-medium">
            This PDF looks scanned (no selectable text). Export a text-based PDF or upload a DOCX.
          </p>
          <p className="text-red-800/90 dark:text-red-300/90">
            Your file was saved, but nothing can be read from it. Scoring and skill extraction
            need selectable text.
          </p>
          {action}
        </div>
      </div>
    );
  }

  if (upload.analysisStatus === 'skipped_no_llm') {
    return (
      <div
        role="status"
        className={cn(
          'flex items-start gap-2.5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200',
          className,
        )}
      >
        <ListChecks className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1 space-y-1">
          {upload.derivedRoles.length > 0 ? (
            <>
              <p className="font-medium">Resume saved. We set your target roles from it.</p>
              <p className="text-amber-800/90 dark:text-amber-300/90">
                {upload.derivedRoles.slice(0, 5).join(', ')}
                {upload.derivedRoles.length > 5 ? ', and more' : ''}. The board can find matching work
                now. Edit these anytime, or a connected assistant can refine them.
              </p>
            </>
          ) : (
            <>
              <p className="font-medium">Resume saved. Now tell Questboard the roles you want.</p>
              <p className="text-amber-800/90 dark:text-amber-300/90">
                Add your target roles and the board finds matching work. No AI needed. If you&apos;ve
                connected an assistant like Claude or Codex, it can read your resume and fill them in.
              </p>
            </>
          )}
          {action}
        </div>
      </div>
    );
  }

  if (upload.analysisStatus === 'analysis_error') {
    return (
      <div
        role="status"
        className={cn(
          'flex items-start gap-2.5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200',
          className,
        )}
      >
        <RefreshCw className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-medium">Your resume was saved and we read it fine.</p>
          <p className="text-amber-800/90 dark:text-amber-300/90">
            The step that pulls out your skills didn&apos;t finish this time. Try again in a moment.
          </p>
          {action}
        </div>
      </div>
    );
  }

  // analysisStatus === 'failed' means no text could be read from the file.
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2.5 rounded-lg border border-red-300 bg-red-50 p-3 text-xs leading-relaxed text-red-900 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">Resume saved, but we couldn&apos;t read any text from it.</p>
        <p className="text-red-800/90 dark:text-red-300/90">
          {upload.parseWarning ||
            'Scoring and skill extraction need selectable text. Upload a text-based PDF or a DOCX.'}
        </p>
        {action}
      </div>
    </div>
  );
}
