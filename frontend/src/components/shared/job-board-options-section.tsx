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

export function JobBoardOptionsSection({
  includeLinkedInJobs,
  onIncludeLinkedInJobsChange,
  context,
  className,
}: JobBoardOptionsSectionProps) {
  const id = `include-linkedin-${context}`;
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Checkbox
        id={id}
        checked={includeLinkedInJobs}
        onCheckedChange={(checked) => onIncludeLinkedInJobsChange(!!checked)}
      />
      <Label htmlFor={id} className="cursor-pointer text-sm font-normal text-text-secondary">
        Include LinkedIn
        <span
          className="ml-1.5 text-xs text-text-muted"
          title="LinkedIn blocks automated scraping; results are unreliable."
        >
          (less reliable)
        </span>
      </Label>
    </div>
  );
}
