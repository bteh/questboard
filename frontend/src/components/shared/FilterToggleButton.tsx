import { Filter, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FilterToggleButtonProps {
  open: boolean;
  count: number;
  onClick: () => void;
  className?: string;
}

/**
 * Shared "Filters" toggle button used by the Search and Applications pages.
 * Shows a filter icon + label, an active-count badge when count > 0, and a
 * chevron that rotates when the panel is open. Active state uses the brand
 * tokens to match the canonical Applications toolbar treatment.
 */
export function FilterToggleButton({ open, count, onClick, className }: FilterToggleButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-all cursor-pointer focus-ring',
        open
          ? 'border-brand bg-brand-light/40 text-brand hover:bg-brand-light/60'
          : 'border-border-default bg-bg-card text-text-primary hover:border-brand/60 hover:bg-bg-subtle',
        className,
      )}
    >
      <Filter className="h-4 w-4" />
      <span>Filters</span>
      {count > 0 && (
        <span className="flex items-center justify-center h-5 min-w-5 px-1 rounded-full bg-brand text-white text-[10px] font-semibold ml-0.5">
          {count}
        </span>
      )}
      <ChevronDown className={cn('h-4 w-4 transition-transform', open && 'rotate-180')} />
    </button>
  );
}
