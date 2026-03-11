import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  children?: React.ReactNode;
}

export function EmptyState({ icon: Icon, title, description, children }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light mb-5">
        <Icon className="h-7 w-7 text-brand" />
      </div>
      <h3 className="text-lg font-semibold text-text-primary mb-1.5">{title}</h3>
      <p className="text-sm text-text-tertiary max-w-sm leading-relaxed">{description}</p>
      {children && <div className="mt-5">{children}</div>}
    </div>
  );
}
