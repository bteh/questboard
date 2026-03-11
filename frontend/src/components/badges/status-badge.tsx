import { ColorBadge } from './color-badge';
import { STATUS_COLORS, STATUS_LABELS } from '@/utils/constants';
import type { StatusOption } from '@/utils/constants';

interface StatusBadgeProps {
  status: StatusOption | string;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  if (!status) return null;
  const colors = STATUS_COLORS[status] || { bg: '#F1F5F9', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1' };
  return (
    <ColorBadge bg={colors.bg} text={colors.text} darkBg={colors.darkBg} darkText={colors.darkText}>
      {STATUS_LABELS[status] || status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
    </ColorBadge>
  );
}
