import { cn } from '@/lib/utils';
import {
  WORKPLACE_OPTIONS,
  type WorkplacePreference,
} from '@/lib/profile-preferences';

interface WorkplacePreferenceSelectorProps {
  value: WorkplacePreference;
  onChange: (value: WorkplacePreference) => void;
  className?: string;
}

export function WorkplacePreferenceSelector({
  value,
  onChange,
  className,
}: WorkplacePreferenceSelectorProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Workplace preference"
      className={cn('grid gap-2 sm:grid-cols-3', className)}
    >
      {WORKPLACE_OPTIONS.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={cn(
              'rounded-xl border px-3.5 py-3 text-left transition-all',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2',
              selected
                ? 'border-brand bg-brand-light/50 shadow-sm ring-1 ring-brand/20'
                : 'border-border-default bg-bg-card hover:border-brand/40 hover:bg-bg-subtle',
            )}
          >
            <p className={cn('text-sm font-medium', selected ? 'text-brand' : 'text-text-primary')}>
              {option.label}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-text-muted">
              {option.description}
            </p>
          </button>
        );
      })}
    </div>
  );
}
