import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FilterChipItem {
  key: string;
  label: string;
  display: string;
}

interface FilterChipsProps {
  items: FilterChipItem[];
  /**
   * Removes a single chip by key. When omitted, chips render without an X
   * button (read-only summary) — used by pages whose filters aren't
   * individually removable.
   */
  onRemove?: (key: string) => void;
  /** When provided and items exist, renders a subtle "Clear all" text button. */
  onClearAll?: () => void;
  className?: string;
}

/**
 * Shared removable active-filter chips used by the Search and Applications
 * pages. Each chip shows `label: display`. When onRemove is given, chips are
 * clickable buttons with an X affordance; otherwise they render as static
 * summary chips.
 */
export function FilterChips({ items, onRemove, onClearAll, className }: FilterChipsProps) {
  if (items.length === 0) return null;

  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {items.map((f) =>
        onRemove ? (
          <button
            key={f.key}
            type="button"
            onClick={() => onRemove(f.key)}
            className="group inline-flex items-center gap-1 rounded-md bg-bg-muted hover:bg-danger/10 border border-transparent hover:border-danger/30 px-2 py-0.5 text-xs font-medium text-text-secondary hover:text-danger transition-all"
          >
            <span className="text-text-muted group-hover:text-red-400">{f.label}:</span>
            {f.display}
            <X className="h-3 w-3 ml-0.5 opacity-40 group-hover:opacity-100 transition-opacity" />
          </button>
        ) : (
          <span
            key={f.key}
            className="inline-flex items-center gap-1 rounded-md bg-bg-muted border border-transparent px-2 py-0.5 text-xs font-medium text-text-secondary"
          >
            {f.label && <span className="text-text-muted">{f.label}:</span>}
            {f.display}
          </span>
        ),
      )}
      {onClearAll && (
        <button
          type="button"
          onClick={onClearAll}
          className="text-xs text-text-muted hover:text-brand font-medium ml-1 transition-colors"
        >
          Clear all
        </button>
      )}
    </div>
  );
}
