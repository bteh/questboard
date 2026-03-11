import { useState } from 'react';
import { CheckCircle2, AlertTriangle, ChevronDown } from 'lucide-react';

interface StrengthsGapsProps {
  strengths: string[];
  gaps: string[];
}

const MAX_VISIBLE = 4;

function PillList({
  items,
  variant,
}: {
  items: string[];
  variant: 'strength' | 'gap';
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? items : items.slice(0, MAX_VISIBLE);
  const remaining = items.length - MAX_VISIBLE;

  const pillClass =
    variant === 'strength'
      ? 'bg-success/10 text-success border-success/20'
      : 'bg-warning/10 text-warning border-warning/20';

  return (
    <div className="space-y-2">
      {visible.map((item, i) => (
        <div
          key={i}
          className={`rounded-lg border px-3 py-2 text-xs leading-relaxed ${pillClass}`}
        >
          {item}
        </div>
      ))}
      {!expanded && remaining > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
        >
          <ChevronDown className="h-3 w-3" />
          {remaining} more
        </button>
      )}
    </div>
  );
}

export function StrengthsGaps({ strengths, gaps }: StrengthsGapsProps) {
  if (!strengths?.length && !gaps?.length) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {strengths?.length > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5 text-success" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-success">
              Strengths
            </span>
            <span className="text-[10px] text-text-muted">({strengths.length})</span>
          </div>
          <PillList items={strengths} variant="strength" />
        </div>
      )}
      {gaps?.length > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5 text-warning" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-warning">
              Room to Grow
            </span>
            <span className="text-[10px] text-text-muted">({gaps.length})</span>
          </div>
          <PillList items={gaps} variant="gap" />
        </div>
      )}
    </div>
  );
}
