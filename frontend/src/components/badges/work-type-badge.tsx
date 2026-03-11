import { Wifi, Building2, MapPin } from 'lucide-react';
import { ColorBadge } from './color-badge';

const WORK_TYPE_STYLES: Record<string, { bg: string; text: string; darkBg: string; darkText: string; icon: typeof Wifi; label: string }> = {
  remote:  { bg: '#E0E7FF', text: '#3730A3', darkBg: '#312E81', darkText: '#A5B4FC', icon: Wifi,      label: 'Remote' },
  hybrid:  { bg: '#FEF3C7', text: '#92400E', darkBg: '#78350F', darkText: '#FDE68A', icon: Building2, label: 'Hybrid' },
  onsite:  { bg: '#F1F5F9', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1', icon: MapPin,    label: 'Onsite' },
};

interface WorkTypeBadgeProps {
  workType: string;
  isRemote?: boolean;
}

export function WorkTypeBadge({ workType, isRemote }: WorkTypeBadgeProps) {
  const key = workType || (isRemote ? 'remote' : '');
  const style = WORK_TYPE_STYLES[key];
  if (!style) return null;

  const Icon = style.icon;
  return (
    <ColorBadge bg={style.bg} text={style.text} darkBg={style.darkBg} darkText={style.darkText}>
      <Icon className="h-3 w-3" />
      {style.label}
    </ColorBadge>
  );
}
