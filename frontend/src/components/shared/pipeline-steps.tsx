import { Search, BarChart3, Sparkles, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PipelineStepsProps {
  llmAvailable: boolean;
  activeStep?: number;
  sourceCount?: number;
}

// Warm earthy triad for the 3 pipeline phases: sage → amber → clay.
// Distinguishable per stage, but harmonious and on-palette (no blue/violet slop).
const STEPS = (count: number) => [
  {
    icon: Search,
    label: 'Search',
    description: count > 0 ? `${count} job boards` : 'Multiple boards',
    color: 'text-[#3F6B54] dark:text-[#7FB393]',
    bg: 'bg-[#EAF0EB] dark:bg-[#7FB393]/10',
    activeBg: 'bg-[#DCE7DF] dark:bg-[#7FB393]/20',
    dot: 'bg-[#3F6B54] dark:bg-[#7FB393]',
  },
  {
    icon: BarChart3,
    label: 'Rank',
    description: '7-dimension scoring',
    color: 'text-[#B4701C] dark:text-[#F0A24E]',
    bg: 'bg-[#FBEEDA] dark:bg-[#F0A24E]/10',
    activeBg: 'bg-[#F6E1C0] dark:bg-[#F0A24E]/20',
    dot: 'bg-[#E0872F] dark:bg-[#F0A24E]',
  },
  {
    icon: Sparkles,
    label: 'Enhance',
    description: 'Letters & research',
    color: 'text-[#A64B2A] dark:text-[#D98A6A]',
    bg: 'bg-[#F6E4DA] dark:bg-[#D98A6A]/10',
    activeBg: 'bg-[#EFD4C5] dark:bg-[#D98A6A]/20',
    dot: 'bg-[#B5623C] dark:bg-[#D98A6A]',
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
