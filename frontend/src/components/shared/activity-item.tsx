import { STATUS_DOT_COLORS, STATUS_LABELS } from '@/utils/constants';
import { formatDate } from '@/utils/format';
import type { ApplicationResponse } from '@/types/application';

interface ActivityItemProps {
  app: ApplicationResponse;
}

export function ActivityItem({ app }: ActivityItemProps) {
  const dotColor = STATUS_DOT_COLORS[app.status] || '#94A3B8';
  return (
    <div className="flex items-start gap-3 py-2">
      <div className="mt-1.5 h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: dotColor }} />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text-primary truncate">
          <span className="font-medium">{app.job_title}</span>
          <span className="text-text-tertiary"> at </span>
          <span className="font-medium">{app.company}</span>
        </p>
        <p className="text-xs text-text-muted">{STATUS_LABELS[app.status] || app.status} · {formatDate(app.date_found || app.created_at, 'relative')}</p>
      </div>
    </div>
  );
}
