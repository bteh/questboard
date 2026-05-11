import { useMemo, useState } from 'react';
import { ChevronDown, Filter, X } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { FunnelStage, FunnelSummary as FunnelSummaryData } from '@/types/search';

interface FunnelSummaryProps {
  data: FunnelSummaryData;
  onDismiss?: () => void;
  className?: string;
}

function formatCount(n: number): string {
  return n.toLocaleString();
}

function StageDeltaLine({ stage }: { stage: FunnelStage }) {
  if (!stage.active) {
    return <span className="italic text-[var(--lb-text-muted)]">skipped</span>;
  }
  const droppedPct = stage.count_in > 0 ? (stage.dropped / stage.count_in) * 100 : 0;
  if (stage.dropped <= 0) {
    return <span className="text-[var(--lb-text-muted)]">no change</span>;
  }
  return (
    <span className="text-[var(--lb-text-tertiary)]">
      <span className="text-[var(--lb-danger)]">−{formatCount(stage.dropped)}</span>
      {droppedPct >= 1 && <> · {droppedPct.toFixed(0)}%</>}
    </span>
  );
}

function StageCell({ stage }: { stage: FunnelStage }) {
  const skipped = !stage.active;
  return (
    <div
      className={cn(
        'flex flex-1 basis-0 flex-col justify-between rounded-md border p-3 min-w-[7.5rem]',
        skipped
          ? 'border-dashed border-[var(--lb-border-default)] bg-transparent'
          : 'border-[var(--lb-border-default)] bg-[var(--lb-bg-card)]',
      )}
    >
      <div
        className={cn(
          'text-[11px] font-medium leading-tight break-words min-h-[2.2rem]',
          skipped ? 'text-[var(--lb-text-muted)]' : 'text-[var(--lb-text-tertiary)]',
        )}
      >
        {stage.label}
      </div>
      <div
        className={cn(
          'mt-2 text-xl font-semibold tabular-nums leading-none',
          skipped ? 'text-[var(--lb-text-muted)]' : 'text-[var(--lb-text-primary)]',
        )}
      >
        {formatCount(stage.count_out)}
      </div>
      <div className="mt-1.5 text-[11px] tabular-nums">
        <StageDeltaLine stage={stage} />
      </div>
    </div>
  );
}

export function FunnelSummary({ data, onDismiss, className }: FunnelSummaryProps) {
  const [expanded, setExpanded] = useState(true);

  const { rawCount, finalCount, totalDropped, droppedPct, stages } = useMemo(() => {
    const stages = data.stages ?? [];
    const rawCount = stages.length > 0 ? stages[0].count_in : data.raw_count;
    const finalCount = stages.length > 0 ? stages[stages.length - 1].count_out : data.final_count;
    const totalDropped = Math.max(rawCount - finalCount, 0);
    const droppedPct = rawCount > 0 ? (totalDropped / rawCount) * 100 : 0;
    return { rawCount, finalCount, totalDropped, droppedPct, stages };
  }, [data]);

  if (!stages.length) return null;

  return (
    <Card
      className={cn(
        'border-[var(--lb-border-default)] bg-[var(--lb-bg-subtle)] p-4',
        className,
      )}
      role="region"
      aria-label="Search funnel summary"
    >
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-controls="funnel-summary-stages"
          className="group flex flex-1 items-center gap-2.5 text-left -m-1 p-1 rounded outline-none focus-visible:ring-2 focus-visible:ring-[var(--lb-brand-ring)]"
        >
          <Filter className="h-4 w-4 shrink-0 text-[var(--lb-text-tertiary)]" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline flex-wrap gap-x-2">
              <span className="text-sm font-semibold text-[var(--lb-text-primary)]">
                Search funnel
              </span>
              <span className="text-xs text-[var(--lb-text-tertiary)]">
                {formatCount(rawCount)} found
                {' → '}
                <span className="font-semibold text-[var(--lb-text-primary)]">
                  {formatCount(finalCount)} kept
                </span>
                {totalDropped > 0 && (
                  <>
                    {' '}
                    <span className="text-[var(--lb-text-muted)]">
                      ({droppedPct.toFixed(0)}% filtered out)
                    </span>
                  </>
                )}
              </span>
            </div>
          </div>
          <ChevronDown
            className={cn(
              'h-4 w-4 shrink-0 text-[var(--lb-text-tertiary)] transition-transform',
              !expanded && '-rotate-90',
            )}
            aria-hidden
          />
        </button>
        {onDismiss && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDismiss}
            aria-label="Dismiss search funnel"
            className="-mr-1 -mt-1 h-7 w-7 p-0"
          >
            <X className="h-4 w-4" aria-hidden />
          </Button>
        )}
      </div>

      {expanded && (
        <div
          id="funnel-summary-stages"
          className="mt-3 flex w-full items-stretch gap-2 overflow-x-auto pb-1"
        >
          <div className="flex flex-1 basis-0 flex-col justify-between rounded-md border border-[var(--lb-border-default)] bg-[var(--lb-bg-card)] p-3 min-w-[7.5rem]">
            <div className="text-[11px] font-medium leading-tight text-[var(--lb-text-tertiary)] min-h-[2.2rem]">
              Raw results
            </div>
            <div className="mt-2 text-xl font-semibold tabular-nums leading-none text-[var(--lb-text-primary)]">
              {formatCount(rawCount)}
            </div>
            <div className="mt-1.5 text-[11px] text-[var(--lb-text-muted)]">found</div>
          </div>
          {stages.map((stage) => (
            <StageCell key={stage.key} stage={stage} />
          ))}
        </div>
      )}
    </Card>
  );
}

export default FunnelSummary;
