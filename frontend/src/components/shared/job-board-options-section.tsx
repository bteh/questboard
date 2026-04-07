import { AlertTriangle } from 'lucide-react';

import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

type JobBoardOptionsContext = 'settings' | 'search' | 'onboarding';

interface JobBoardOptionsSectionProps {
  includeLinkedInJobs: boolean;
  onIncludeLinkedInJobsChange: (value: boolean) => void;
  context: JobBoardOptionsContext;
  className?: string;
}

const CONTEXT_COPY: Record<JobBoardOptionsContext, string> = {
  settings: 'Saved as your default search-source preference.',
  onboarding: 'Saved with your search preferences for future runs.',
  search: 'Applies only to this run unless you save it as your default.',
};

export function JobBoardOptionsSection({
  includeLinkedInJobs,
  onIncludeLinkedInJobsChange,
  context,
  className,
}: JobBoardOptionsSectionProps) {
  return (
    <div className={cn('space-y-3', className)}>
      <div className="space-y-1">
        <Label className="text-sm font-medium">Optional sources</Label>
        <p className="text-xs text-text-muted">
          Launchboard searches Indeed, Glassdoor, ZipRecruiter, Google Jobs, and direct ATS sources by default.
        </p>
      </div>

      <div className="rounded-xl border border-border-default bg-bg-subtle/40 p-4">
        <div className="flex items-start gap-3">
          <Checkbox
            id={`include-linkedin-${context}`}
            checked={includeLinkedInJobs}
            onCheckedChange={(checked) => onIncludeLinkedInJobsChange(!!checked)}
            className="mt-0.5"
          />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="space-y-1">
              <Label
                htmlFor={`include-linkedin-${context}`}
                className="cursor-pointer text-sm font-medium text-text-primary"
              >
                Include LinkedIn results
              </Label>
              <p className="text-xs leading-relaxed text-text-muted">
                Optional. LinkedIn may block automated scraping or change its site behavior at any time.
                {` ${CONTEXT_COPY[context]}`}
              </p>
            </div>
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-[11px] text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>Enable this only if you want LinkedIn included despite its scraping restrictions and potential instability.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
