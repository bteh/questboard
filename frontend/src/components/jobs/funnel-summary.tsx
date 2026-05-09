import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Filter, X } from 'lucide-react';
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

function StageCell({ stage, isLast }: { stage: FunnelStage; isLast: boolean }) {
  const skipped = !stage.active;
  const dropped = stage.dropped;
  const droppedPct = stage.count_in > 0 ? (dropped / stage.count_in) * 100 : 0;

  return (
    <div className="flex items-stretch min-w-0 flex-1">
      <div
        className={cn(
          'flex flex-1 flex-col gap-1 rounded-md border px-3 py-2.5 min-w-0',
          skipped
            ? 'border-dashed border-[var(--lb-border-default)] bg-transparent'
            : 'border-[var(--lb-border-default)] bg-[var(--lb-bg-card)]',
        )}
      >
        <div
          className={cn(
            'truncate text-[11px] font-medium uppercase tracking-wide',
            skipped ? 'text-[var(--lb-text-muted)]' : 'text-[var(--lb-text-tertiary)]',
          )}
          title={stage.label}
        >
          {stage.label}
        </div>
        <div
          className={cn(
            'text-lg font-semibold tabular-nums',
            skipped ? 'text-[var(--lb-text-muted)]' : 'text-[var(--lb-text-primary)]',
          )}
        >
          {formatCount(stage.count_out)}
        </div>
        <div className="text-[11px] tabular-nums">
          {skipped ? (
            <span className="text-[var(--lb-text-muted)]">skipped</span>
          ) : dropped > 0 ? (
            <span className="text-[var(--lb-danger)]">
              −{formatCount(dropped)}
              {droppedPct >= 1 && (
                <span className="text-[var(--lb-text-tertiary)]"> ({droppedPct.toFixed(0)}%)</span>
              )}
            </span>
          ) : (
            <span className="text-[var(--lb-text-tertiary)]">—</span>
          )}
        </div>
      </div>
      {!isLast && (
        <ChevronRight
          aria-hidden
          className="mx-1 h-4 w-4 shrink-0 self-center text-[var(--lb-text-muted)]"
        />
      )}
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
          className="mt-3 flex w-full items-stretch gap-0 overflow-x-auto pb-1"
        >
          <div className="flex flex-1 items-stretch gap-0 min-w-0">
            <div className="flex flex-1 flex-col gap-1 rounded-md border border-[var(--lb-border-default)] bg-[var(--lb-bg-card)] px-3 py-2.5 min-w-[5.5rem]">
              <div className="text-[11px] font-medium uppercase tracking-wide text-[var(--lb-text-tertiary)]">
                Raw
              </div>
              <div className="text-lg font-semibold tabular-nums text-[var(--lb-text-primary)]">
                {formatCount(rawCount)}
              </div>
              <div className="text-[11px] text-[var(--lb-text-tertiary)]">found</div>
            </div>
            <ChevronRight
              aria-hidden
              className="mx-1 h-4 w-4 shrink-0 self-center text-[var(--lb-text-muted)]"
            />
            {stages.map((stage, idx) => (
              <StageCell
                key={stage.key}
                stage={stage}
                isLast={idx === stages.length - 1}
              />
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

export default FunnelSummary;
