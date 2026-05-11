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
              'rounded-lg border px-3 py-2 text-sm font-medium text-center transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2',
              selected
                ? 'border-brand bg-brand-light/50 text-brand'
                : 'border-border-default bg-bg-card text-text-secondary hover:border-brand/40 hover:bg-bg-subtle',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
