import { useProfile } from '@/contexts/profile-context';
import { useWorkspace } from '@/contexts/workspace-context';

interface PageHeaderProps {
  title: string;
  description?: string;
  children?: React.ReactNode;
}

export function PageHeader({ title, description, children }: PageHeaderProps) {
  const { profile } = useProfile();
  const { hostedMode } = useWorkspace();

  return (
    <div className="flex items-start justify-between pb-6">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-text-tertiary">{description}</p>}
        {!hostedMode && profile !== 'default' && (
          <p className="mt-0.5 text-xs text-text-muted">Profile: {profile}</p>
        )}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
