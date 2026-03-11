import { Search, BarChart3, Sparkles, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PipelineStepsProps {
  llmAvailable: boolean;
  activeStep?: number;
  sourceCount?: number;
}

const STEPS = (count: number) => [
  {
    icon: Search,
    label: 'Search',
    description: count > 0 ? `${count} job boards` : 'Multiple boards',
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-950/40',
    activeBg: 'bg-blue-100 dark:bg-blue-900/50',
    dot: 'bg-blue-500',
  },
  {
    icon: BarChart3,
    label: 'Rank',
    description: '7-dimension scoring',
    color: 'text-violet-600 dark:text-violet-400',
    bg: 'bg-violet-50 dark:bg-violet-950/40',
    activeBg: 'bg-violet-100 dark:bg-violet-900/50',
    dot: 'bg-violet-500',
  },
  {
    icon: Sparkles,
    label: 'Enhance',
    description: 'Letters & research',
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-950/40',
    activeBg: 'bg-amber-100 dark:bg-amber-900/50',
    dot: 'bg-amber-500',
  },
];

export function PipelineSteps({ llmAvailable, activeStep, sourceCount = 0 }: PipelineStepsProps) {
  return (
    <div className="flex items-center justify-center gap-2">
      {STEPS(sourceCount).map((step, i) => {
        const isActive = activeStep === i;
        const isDone = activeStep !== undefined && i < activeStep;
        const isDisabled = i === 2 && !llmAvailable;
        return (
          <div key={step.label} className="flex items-center gap-2">
            <div
              className={cn(
                'flex items-center gap-2.5 rounded-full px-4 py-2 transition-all select-none',
                isDone && 'bg-success/10',
                isActive && step.activeBg,
                !isDone && !isActive && step.bg,
                isDisabled && 'opacity-40',
              )}
            >
              <div className={cn(
                'flex h-7 w-7 items-center justify-center rounded-full',
                isDone ? 'bg-success/15' : `${step.dot}/10`,
              )}>
                <step.icon className={cn('h-3.5 w-3.5', isDone ? 'text-success' : isActive ? step.color : step.color)} />
              </div>
              <div className="flex flex-col">
                <span className={cn('text-xs font-semibold leading-tight', isDone ? 'text-success' : step.color)}>
                  {step.label}
                </span>
                <span className="text-[10px] text-text-muted leading-tight">{step.description}</span>
              </div>
            </div>
            {i < 2 && (
              <ChevronRight className="h-3.5 w-3.5 text-text-muted/30 shrink-0" />
            )}
          </div>
        );
      })}
    </div>
  );
}
