import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  /** Optional supporting copy rendered under the title. */
  description?: string;
  /** Action region (buttons, links). Rendered below the description. */
  children?: React.ReactNode;
  /** Controls vertical padding + icon/title sizing. Defaults to `md`. */
  size?: 'sm' | 'md';
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
  size = 'md',
  className,
}: EmptyStateProps) {
  const compact = size === 'sm';
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'py-16' : 'py-24',
        className,
      )}
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light mb-5">
        <Icon className="h-7 w-7 text-brand" />
      </div>
      <h3
        className={cn(
          'font-semibold text-text-primary mb-1.5',
          compact ? 'text-base' : 'text-lg',
        )}
      >
        {title}
      </h3>
      {description && (
        <p className="text-sm text-text-tertiary max-w-md leading-relaxed">{description}</p>
      )}
      {children && <div className="mt-5">{children}</div>}
    </div>
  );
}
